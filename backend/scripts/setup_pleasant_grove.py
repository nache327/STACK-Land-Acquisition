"""
Full setup for Pleasant Grove, UT:
  1. Download UGRC Utah County parcels → insert into DB
  2. Spatial join to Utah County CommercialAppraiser zoning layer 55
  3. Build zone_use_matrix from ZONE_PG_LABEL + ZONE_PG_DESC

Run from backend/ directory:
    python scripts/setup_pleasant_grove.py
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL  = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"

PG_JUR_ID = "ea4648de-5e6b-4a83-adca-eb47f947841d"

UGRC_PARCELS = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Utah/FeatureServer/0"
ZONING_URL   = "https://maps.utahcounty.gov/arcgis/rest/services/Assessor/CommercialAppraiser/MapServer/55"


def classify_pleasant_grove(label: str, desc: str) -> str:
    if not label or label.strip() == "None":
        return "conditional"  # overlay-only districts

    u = label.strip().upper()
    d = (desc or "").strip().upper()

    # Industrial / Manufacturing — permitted
    if u in ("MD", "BMP"):
        return "permitted"

    # Commercial zones — conditional
    if u in ("C", "C-G", "C-N", "C-S1", "C-S2", "I", "RCO"):
        return "conditional"

    # Agricultural — conditional
    if u == "A-1":
        return "conditional"

    # Mixed use / overlay commercial zones — conditional
    if u in ("BMU", "GMU", "DMUO", "GBPO", "MU", "VGMU", "T"):
        return "conditional"

    # Professional Office — conditional (storage usually CUP)
    if u == "P-O":
        return "conditional"

    # Residential agriculture overlay — conditional (agricultural base)
    if u == "RAO":
        return "conditional"

    # Residential — prohibited
    if re.match(r'^R[-\s1]', u) or u in ("R-R", "MH", "SHO", "RM-7"):
        return "prohibited"
    if "RESIDENTIAL" in d and "COMMERCIAL" not in d:
        return "prohibited"

    # Senior / student housing
    if "SENIOR" in d or "STUDENT" in d:
        return "prohibited"

    logger.warning("[Pleasant Grove] Unknown code '%s' (%s) → conditional", label, desc)
    return "conditional"


# ── Parcel download & insert ──────────────────────────────────────────────────

def download_ugrc_parcels() -> list[dict]:
    logger.info("[Pleasant Grove] Downloading UGRC Utah County parcels …")
    # Check available fields first
    r0 = requests.get(f"{UGRC_PARCELS}", params={"f": "json"}, timeout=30)
    fields = [f["name"] for f in r0.json().get("fields", [])]
    logger.info("  Available fields: %s", fields)

    want = ["PARCEL_ID", "PARCEL_ADD", "CoParcel_URL", "Shape__Area"]
    out_fields = ",".join(f for f in want if f in fields)

    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{UGRC_PARCELS}/query", params={
            "where": "PARCEL_CITY='Pleasant Grove'",
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 2000,
        }, timeout=60)
        r.raise_for_status()
        feats = r.json().get("features", [])
        if not feats and r.json().get("error"):
            logger.error("  API error: %s", r.json()["error"])
            break
        all_features.extend(feats)
        logger.info("  fetched %d (offset %d)", len(feats), offset)
        if len(feats) < 2000:
            break
        offset += len(feats)
    logger.info("[Pleasant Grove] Total UGRC parcels: %d", len(all_features))
    return all_features


def insert_parcels(features: list[dict]) -> int:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("DELETE FROM parcels WHERE jurisdiction_id = %s", (PG_JUR_ID,))
    logger.info("[Pleasant Grove] Deleted old parcels, inserting %d new …", len(features))

    inserted = 0
    batch = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        geom_json = feat.get("geometry")
        if not geom_json:
            continue

        apn = None
        for k in ("PARCEL_ID", "parcel_id"):
            if props.get(k):
                apn = props[k]
                break
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

        address = props.get("PARCEL_ADD") or props.get("parcel_add")
        sqm = props.get("Shape__Area") or props.get("shape__area")
        try:
            acres = round(float(sqm) / 4046.856, 4) if sqm else None
        except (ValueError, TypeError):
            acres = None
        county_link = props.get("CoParcel_URL") or props.get("coparcel_url")

        batch.append((
            PG_JUR_ID,
            str(apn),
            str(address).strip() if address else None,
            acres,
            county_link,
            f"SRID=4326;{geom.wkt}",
            f"SRID=4326;{geom.centroid.wkt}",
        ))

        if len(batch) >= 500:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO parcels (jurisdiction_id, apn, address, acres, county_link, geom, centroid)
                VALUES (%s,%s,%s,%s,%s, ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s))
                ON CONFLICT DO NOTHING
            """, batch)
            inserted += len(batch)
            logger.info("  inserted %d …", inserted)
            batch = []

    if batch:
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO parcels (jurisdiction_id, apn, address, acres, county_link, geom, centroid)
            VALUES (%s,%s,%s,%s,%s, ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s))
            ON CONFLICT DO NOTHING
        """, batch)
        inserted += len(batch)

    conn.commit()
    conn.close()
    logger.info("[Pleasant Grove] Inserted %d parcels", inserted)
    return inserted


# ── Zoning download + spatial join ────────────────────────────────────────────

def download_zoning() -> gpd.GeoDataFrame:
    logger.info("[Pleasant Grove] Downloading zoning districts …")
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{ZONING_URL}/query", params={
            "where": "1=1",
            "outFields": "ZONE_PG_LABEL,ZONE_PG_DESC",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 1000,
        }, timeout=60)
        r.raise_for_status()
        feats = r.json().get("features", [])
        all_features.extend(feats)
        logger.info("  fetched %d (offset %d)", len(feats), offset)
        if len(feats) < 1000:
            break
        offset += len(feats)
    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
    gdf = gdf.dropna(subset=["ZONE_PG_LABEL"])
    gdf = gdf[gdf["ZONE_PG_LABEL"].astype(str).str.strip().str.upper() != "NONE"]
    logger.info("[Pleasant Grove] %d zoning districts", len(gdf))
    return gdf


def load_centroids() -> gpd.GeoDataFrame:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ST_X(centroid::geometry), ST_Y(centroid::geometry) "
        "FROM parcels WHERE jurisdiction_id = %s",
        (PG_JUR_ID,),
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
            batch = pairs[i:i + 500]
            values = ", ".join(f"({pid}, $${zc}$$)" for pid, zc in batch)
            result = await conn.execute(text(
                f"UPDATE parcels AS p SET zoning_code=v.zone "
                f"FROM (VALUES {values}) AS v(id,zone) WHERE p.id=v.id"
            ))
            updated += result.rowcount
    await engine.dispose()
    return updated


async def build_matrix(zone_map: dict[str, tuple[str, str]]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": PG_JUR_ID},
        )
        for zone_code, (desc, perm) in zone_map.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name, self_storage, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, 0.8, :notes)
            """), {
                "jid": PG_JUR_ID,
                "zc": zone_code,
                "zn": desc or zone_code,
                "ss": perm,
                "notes": "Pleasant Grove Utah County zoning classification",
            })
    await engine.dispose()
    logger.info("[Pleasant Grove] Inserted %d zone_use_matrix rows", len(zone_map))


async def main() -> None:
    # 1. Parcels
    features = download_ugrc_parcels()
    insert_parcels(features)

    # 2. Zoning spatial join
    zoning_gdf = download_zoning()
    parcels_gdf = load_centroids()
    logger.info("[Pleasant Grove] %d parcel centroids loaded", len(parcels_gdf))

    joined = gpd.sjoin(parcels_gdf, zoning_gdf[["ZONE_PG_LABEL", "ZONE_PG_DESC", "geometry"]], how="left", predicate="within")
    matched = joined.dropna(subset=["ZONE_PG_LABEL"])
    logger.info("[Pleasant Grove] Matched %d / %d parcels", len(matched), len(parcels_gdf))

    pairs = list(zip(matched["id"].tolist(), matched["ZONE_PG_LABEL"].tolist()))
    if pairs:
        updated = await update_zoning_codes(pairs)
        logger.info("[Pleasant Grove] Updated zoning_code on %d parcels", updated)

    # 3. zone_use_matrix from distinct (label, desc) pairs
    zone_map: dict[str, tuple[str, str]] = {}
    for _, row in zoning_gdf.iterrows():
        label = str(row["ZONE_PG_LABEL"]).strip()
        desc = str(row.get("ZONE_PG_DESC", "") or "")
        if label and label not in zone_map:
            perm = classify_pleasant_grove(label, desc)
            zone_map[label] = (desc, perm)

    counts: dict[str, int] = {}
    for _, (_, p) in zone_map.items():
        counts[p] = counts.get(p, 0) + 1
    logger.info("[Pleasant Grove] Zone distribution: %s", counts)
    for zc, (desc, perm) in sorted(zone_map.items()):
        logger.info("  %-20s %-45s → %s", zc, desc, perm)

    await build_matrix(zone_map)

    # Final match rate
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(p.id), COUNT(z.zone_code),
               ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id),0),1)
        FROM parcels p
        LEFT JOIN zone_use_matrix z
            ON z.jurisdiction_id=p.jurisdiction_id AND z.zone_code=p.zoning_code
        WHERE p.jurisdiction_id = %s
    """, (PG_JUR_ID,))
    row = cur.fetchone()
    conn.close()
    logger.info("[Pleasant Grove] Final match rate: %d/%d = %s%%", row[1], row[0], row[2])


if __name__ == "__main__":
    asyncio.run(main())
