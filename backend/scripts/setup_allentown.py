"""
Allentown, PA full setup:
  1. Update jurisdiction record (name, correct GIS endpoints)
  2. Clear old (Emmaus) parcels and re-ingest from gisportal.allentownpa.gov
  3. Download CityZoning districts → assign ZONINGCODE to parcels via spatial join
  4. Build zone_use_matrix with rule-based classification
     (ordinance PDF parse happens automatically when the next job is submitted)

Run from backend/ directory:
    python scripts/setup_allentown.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
import psycopg2
import psycopg2.extras
import requests
from shapely.geometry import Point
from shapely import make_valid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.zone_classifier import PerUseClassification, storage_cls
from scripts._db import get_dsn, get_sync_dsn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_URL = get_dsn()
DB_SYNC = get_sync_dsn()

PARCEL_ENDPOINT = (
    "https://gisportal.allentownpa.gov/server/rest/services/City_Landuse/FeatureServer/0"
)
ZONING_ENDPOINT = (
    "https://gisportal.allentownpa.gov/server/rest/services/CityZoning/FeatureServer/0"
)
ORDINANCE_URL = (
    "https://www.allentownpa.gov/Portals/0/files/Departments"
    "/PlanningZoning/Zoning%20Ordinance.pdf"
)

JUR_NAME  = "Allentown, PA"
JUR_STATE = "PA"
JUR_COUNTY = "Lehigh"


# ─── Zone classifier ──────────────────────────────────────────────────────────
# Based on Allentown's ZONE Allentown ordinance (effective 2026-01-01).
# The PDF parse will refine these on first job run.

def classify_allentown(code: str) -> PerUseClassification:
    u = code.strip().upper()

    # Industrial — clearly permitted for storage + light industrial
    if u in ("IG", "I3"):
        return storage_cls("permitted", 0.82, f"Allentown industrial: {code}")
    if u == "I2":
        return storage_cls("permitted", 0.80, f"Allentown light industrial: {code}")
    if u == "BLI":
        return storage_cls("permitted", 0.75, f"Allentown Business Light Industrial: {code}")

    # Business/Industrial Waterfront — conditional (mixed use with industrial component)
    if u == "B/IWD":
        return storage_cls("conditional", 0.65, f"Allentown Business/Industrial Waterfront: {code}")

    # Business zones — conditional (ordinance typically requires CUP for storage)
    if u in ("B5", "B4"):
        return storage_cls("conditional", 0.68, f"Allentown highway/regional commercial: {code}")
    if u in ("B3", "B2"):
        return storage_cls("conditional", 0.65, f"Allentown neighborhood commercial: {code}")
    if u == "B1R":
        return storage_cls("conditional", 0.60, f"Allentown transitional business-residential: {code}")

    # Residential — prohibited
    if u in ("RL", "RLC", "RM", "RML", "RMH", "RH"):
        return storage_cls("prohibited", 0.85, f"Allentown residential: {code}")
    if u == "RMP":
        return storage_cls("prohibited", 0.72, f"Allentown residential mixed-purpose: {code}")

    # Public/Institutional — prohibited
    if u == "P":
        return storage_cls("prohibited", 0.80, f"Allentown public/institutional: {code}")

    logger.warning("Unknown Allentown zone code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Allentown unknown zone '{code}' — conservative default")


# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_or_create_jurisdiction() -> str:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()

    # Try exact name first
    cur.execute("SELECT id, name FROM jurisdictions WHERE name=%s AND state=%s", (JUR_NAME, JUR_STATE))
    row = cur.fetchone()
    if row:
        jur_id = str(row[0])
        logger.info("Found jurisdiction: %s (%s)", row[1], jur_id)
    else:
        # Try partial match (in case old record used "Allentown" without ", PA")
        cur.execute(
            "SELECT id, name FROM jurisdictions WHERE name ILIKE %s AND state=%s",
            ("%Allentown%", JUR_STATE),
        )
        row = cur.fetchone()
        if row:
            jur_id = str(row[0])
            old_name = row[1]
            cur.execute(
                "UPDATE jurisdictions SET name=%s WHERE id=%s",
                (JUR_NAME, jur_id),
            )
            conn.commit()
            logger.info("Renamed jurisdiction '%s' → '%s' (%s)", old_name, JUR_NAME, jur_id)
        else:
            jur_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO jurisdictions (id, name, state, county) VALUES (%s,%s,%s,%s)",
                (jur_id, JUR_NAME, JUR_STATE, JUR_COUNTY),
            )
            conn.commit()
            logger.info("Created new jurisdiction: %s (%s)", JUR_NAME, jur_id)

    # Always update endpoints to the correct values
    cur.execute(
        """UPDATE jurisdictions
           SET parcel_endpoint=%s,
               zoning_endpoint=%s,
               ordinance_url=%s,
               county=%s
           WHERE id=%s""",
        (PARCEL_ENDPOINT, ZONING_ENDPOINT, ORDINANCE_URL, JUR_COUNTY, jur_id),
    )
    conn.commit()
    conn.close()
    logger.info("Updated endpoints for jurisdiction %s", jur_id)
    return jur_id


def download_parcels() -> list[dict]:
    logger.info("Downloading Allentown parcels from City_Landuse …")
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(
            f"{PARCEL_ENDPOINT}/query",
            params={
                "where": "1=1",
                "outFields": "WARDACCTNO,PROPERTYADDR,Shape__Area",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": 1000,
            },
            timeout=60,
        )
        r.raise_for_status()
        feats = r.json().get("features", [])
        all_features.extend(feats)
        logger.info("  fetched %d (offset %d)", len(feats), offset)
        if len(feats) < 1000:
            break
        offset += len(feats)
    logger.info("Total Allentown parcels: %d", len(all_features))
    return all_features


def insert_parcels(features: list[dict], jur_id: str) -> int:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("DELETE FROM parcels WHERE jurisdiction_id=%s", (jur_id,))
    conn.commit()
    logger.info("Cleared old parcels for %s", jur_id)

    inserted = 0
    batch = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        geom_json = feat.get("geometry")
        if not geom_json:
            continue
        apn = props.get("WARDACCTNO")
        if not apn:
            continue
        try:
            from shapely.geometry import shape
            geom = shape(geom_json)
            if geom.is_empty:
                continue
            if not geom.is_valid:
                geom = make_valid(geom)
            if geom.is_empty:
                continue
        except Exception:
            continue
        address = props.get("PROPERTYADDR")
        sqm = props.get("Shape__Area")
        try:
            acres = round(float(sqm) / 4046.856, 4) if sqm else None
        except (ValueError, TypeError):
            acres = None
        batch.append((
            jur_id,
            str(apn),
            str(address).strip() if address else None,
            acres,
            f"SRID=4326;{geom.wkt}",
            f"SRID=4326;{geom.centroid.wkt}",
        ))
        if len(batch) >= 500:
            psycopg2.extras.execute_batch(
                cur,
                """INSERT INTO parcels
                       (jurisdiction_id, apn, address, acres, geom, centroid)
                   VALUES (%s,%s,%s,%s, ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s))
                   ON CONFLICT DO NOTHING""",
                batch,
            )
            inserted += len(batch)
            logger.info("  inserted %d …", inserted)
            batch = []
    if batch:
        psycopg2.extras.execute_batch(
            cur,
            """INSERT INTO parcels
                   (jurisdiction_id, apn, address, acres, geom, centroid)
               VALUES (%s,%s,%s,%s, ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s))
               ON CONFLICT DO NOTHING""",
            batch,
        )
        inserted += len(batch)
    conn.commit()
    conn.close()
    logger.info("Inserted %d Allentown parcels", inserted)
    return inserted


def download_zoning() -> gpd.GeoDataFrame:
    logger.info("Downloading CityZoning districts …")
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(
            f"{ZONING_ENDPOINT}/query",
            params={
                "where": "1=1",
                "outFields": "ZONINGCODE",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": 1000,
            },
            timeout=60,
        )
        r.raise_for_status()
        feats = r.json().get("features", [])
        all_features.extend(feats)
        logger.info("  fetched %d zoning polygons (offset %d)", len(feats), offset)
        if len(feats) < 1000:
            break
        offset += len(feats)
    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
    gdf = gdf.dropna(subset=["ZONINGCODE"])
    gdf = gdf[gdf["ZONINGCODE"].astype(str).str.strip() != ""]
    logger.info("%d zoning polygons loaded", len(gdf))
    return gdf


def load_centroids(jur_id: str) -> gpd.GeoDataFrame:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ST_X(centroid::geometry), ST_Y(centroid::geometry) "
        "FROM parcels WHERE jurisdiction_id=%s",
        (jur_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return gpd.GeoDataFrame(
        {"id": [r[0] for r in rows]},
        geometry=[Point(r[1], r[2]) for r in rows],
        crs="EPSG:4326",
    )


async def update_zoning_codes(pairs: list[tuple]) -> int:
    engine = create_async_engine(DB_URL)
    updated = 0
    async with engine.begin() as conn:
        for i in range(0, len(pairs), 500):
            batch = pairs[i : i + 500]
            values = ", ".join(f"({pid}, $${zc}$$)" for pid, zc in batch)
            result = await conn.execute(
                text(
                    f"UPDATE parcels AS p SET zoning_code=v.zone "
                    f"FROM (VALUES {values}) AS v(id,zone) WHERE p.id=v.id"
                )
            )
            updated += result.rowcount
    await engine.dispose()
    return updated


async def build_matrix(jur_id: str, zone_map: dict[str, PerUseClassification]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id=:jid"), {"jid": jur_id}
        )
        for zone_code, cls in zone_map.items():
            await conn.execute(
                text("""
                    INSERT INTO zone_use_matrix
                        (jurisdiction_id, zone_code, zone_name,
                         self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                         classification_source, confidence, notes)
                    VALUES (:jid,:zc,:zn,:ss,:mw,:li,:lgc,'rule',:conf,:notes)
                """),
                {
                    "jid": jur_id,
                    "zc": zone_code,
                    "zn": zone_code,
                    "ss": cls.self_storage,
                    "mw": cls.mini_warehouse,
                    "li": cls.light_industrial,
                    "lgc": cls.luxury_garage_condo,
                    "conf": cls.confidence,
                    "notes": cls.notes,
                },
            )
    await engine.dispose()
    logger.info("Inserted %d zone_use_matrix rows", len(zone_map))


async def main() -> None:
    jur_id = get_or_create_jurisdiction()

    # 1. Download + insert parcels
    features = download_parcels()
    insert_parcels(features, jur_id)

    # 2. Download zoning polygons + spatial join
    zoning_gdf = download_zoning()
    parcels_gdf = load_centroids(jur_id)
    logger.info("%d parcel centroids loaded", len(parcels_gdf))

    joined = gpd.sjoin(
        parcels_gdf,
        zoning_gdf[["ZONINGCODE", "geometry"]],
        how="left",
        predicate="within",
    )
    matched = joined.dropna(subset=["ZONINGCODE"])
    logger.info("Matched %d / %d parcels to zoning", len(matched), len(parcels_gdf))

    pairs = list(zip(matched["id"].tolist(), matched["ZONINGCODE"].tolist()))
    if pairs:
        updated = await update_zoning_codes(pairs)
        logger.info("Updated zoning_code on %d parcels", updated)

    # 3. Build zone matrix from distinct ZONINGCODE values
    zone_map: dict[str, PerUseClassification] = {}
    for code in sorted(zoning_gdf["ZONINGCODE"].unique()):
        code = str(code).strip()
        if code:
            zone_map[code] = classify_allentown(code)

    for zc, cls in sorted(zone_map.items()):
        logger.info("  %-10s → %s (conf %.2f)", zc, cls.self_storage, cls.confidence)

    await build_matrix(jur_id, zone_map)

    # 4. Summary
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        """SELECT COUNT(p.id), COUNT(z.zone_code),
                  ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id),0),1)
           FROM parcels p
           LEFT JOIN zone_use_matrix z
               ON z.jurisdiction_id=p.jurisdiction_id AND z.zone_code=p.zoning_code
           WHERE p.jurisdiction_id=%s""",
        (jur_id,),
    )
    row = cur.fetchone()
    conn.close()
    logger.info(
        "Final match rate: %d/%d = %s%% of parcels have a classified zone",
        row[1], row[0], row[2],
    )
    logger.info("Done. Run a job for 'Allentown, PA' to trigger ordinance PDF parse.")


if __name__ == "__main__":
    asyncio.run(main())
