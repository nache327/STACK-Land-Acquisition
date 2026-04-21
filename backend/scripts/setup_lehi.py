"""
Full setup for Lehi, UT:
  1. Download UGRC Utah County parcels → insert into DB
  2. Spatial join to Utah County CommercialAppraiser zoning layer 25
  3. Build zone_use_matrix from ZONE_LE_LABEL + ZONE_LE_DESC

Run from backend/ directory:
    python scripts/setup_lehi.py
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

from app.services.zone_classifier import PerUseClassification, storage_cls

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL  = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"

LEHI_JUR_ID = "038e93cf-4457-4f74-825d-d78f241e4724"
UGRC_PARCELS = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Utah/FeatureServer/0"
ZONING_URL   = "https://maps.utahcounty.gov/arcgis/rest/services/Assessor/CommercialAppraiser/MapServer/25"


def classify_lehi(label: str, desc: str) -> PerUseClassification:
    u = (label or "").strip().upper()

    if u in ("LI", "T-M", "H/I", "BP"):
        return storage_cls("permitted", 0.80, f"Lehi industrial: {label}")
    if u in ("C", "C-H", "C-I", "CR", "HC", "NC", "TOD"):
        return storage_cls("conditional", 0.70, f"Lehi commercial: {label}")
    if u == "MU":
        return storage_cls("prohibited", 0.70, "Lehi mixed use — residential-oriented")
    # Residential/rural — storage not permitted
    if u in ("PC", "TH-5"):
        return storage_cls("prohibited", 0.78, f"Lehi residential planned/townhouse: {label}")
    if u in ("RC", "RA-1") or re.match(r'^A[-\d]', u) or u == "A":
        return storage_cls("prohibited", 0.78, f"Lehi agricultural/rural: {label}")
    if u == "PF":
        return storage_cls("prohibited", 0.78, "Lehi public facility")
    if re.match(r'^R-', u) or re.match(r'^R\d', u):
        return storage_cls("prohibited", 0.80, f"Lehi residential: {label}")
    logger.warning("[Lehi] Unknown code '%s' (%s) — prohibited (conservative default)", label, desc)
    return storage_cls("prohibited", 0.45, f"Lehi unknown zone code '{label}' — conservative default")


def download_ugrc_parcels() -> list[dict]:
    logger.info("[Lehi] Downloading UGRC Utah County parcels …")
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{UGRC_PARCELS}/query", params={
            "where": "PARCEL_CITY='Lehi'",
            "outFields": "PARCEL_ID,PARCEL_ADD,CoParcel_URL,Shape__Area",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 2000,
        }, timeout=60)
        r.raise_for_status()
        feats = r.json().get("features", [])
        all_features.extend(feats)
        logger.info("  fetched %d (offset %d)", len(feats), offset)
        if len(feats) < 2000:
            break
        offset += len(feats)
    logger.info("[Lehi] Total UGRC parcels: %d", len(all_features))
    return all_features


def insert_parcels(features: list[dict]) -> int:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("DELETE FROM parcels WHERE jurisdiction_id = %s", (LEHI_JUR_ID,))
    logger.info("[Lehi] Deleted old parcels, inserting %d new …", len(features))

    inserted = 0
    batch = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        geom_json = feat.get("geometry")
        if not geom_json:
            continue
        apn = props.get("PARCEL_ID") or props.get("parcel_id")
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
            LEHI_JUR_ID, str(apn),
            str(address).strip() if address else None,
            acres, county_link,
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
    logger.info("[Lehi] Inserted %d parcels", inserted)
    return inserted


def download_zoning() -> gpd.GeoDataFrame:
    logger.info("[Lehi] Downloading zoning districts …")
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{ZONING_URL}/query", params={
            "where": "1=1",
            "outFields": "ZONE_LE_LABEL,ZONE_LE_DESC",
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
    gdf = gdf.dropna(subset=["ZONE_LE_LABEL"])
    gdf = gdf[gdf["ZONE_LE_LABEL"].astype(str).str.strip() != ""]
    logger.info("[Lehi] %d zoning districts", len(gdf))
    return gdf


def load_centroids() -> gpd.GeoDataFrame:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ST_X(centroid::geometry), ST_Y(centroid::geometry) "
        "FROM parcels WHERE jurisdiction_id = %s", (LEHI_JUR_ID,),
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


async def build_matrix(zone_map: dict[str, tuple[str, PerUseClassification]]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": LEHI_JUR_ID},
        )
        for zone_code, (desc, cls) in zone_map.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name,
                     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                     classification_source, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, :mw, :li, :lgc, 'rule', :conf, :notes)
            """), {
                "jid": LEHI_JUR_ID, "zc": zone_code, "zn": desc or zone_code,
                "ss": cls.self_storage, "mw": cls.mini_warehouse,
                "li": cls.light_industrial, "lgc": cls.luxury_garage_condo,
                "conf": cls.confidence, "notes": cls.notes,
            })
    await engine.dispose()
    logger.info("[Lehi] Inserted %d zone_use_matrix rows", len(zone_map))


async def main() -> None:
    features = download_ugrc_parcels()
    insert_parcels(features)

    zoning_gdf = download_zoning()
    parcels_gdf = load_centroids()
    logger.info("[Lehi] %d parcel centroids loaded", len(parcels_gdf))

    joined = gpd.sjoin(parcels_gdf, zoning_gdf[["ZONE_LE_LABEL", "ZONE_LE_DESC", "geometry"]], how="left", predicate="within")
    matched = joined.dropna(subset=["ZONE_LE_LABEL"])
    logger.info("[Lehi] Matched %d / %d parcels", len(matched), len(parcels_gdf))

    pairs = list(zip(matched["id"].tolist(), matched["ZONE_LE_LABEL"].tolist()))
    if pairs:
        updated = await update_zoning_codes(pairs)
        logger.info("[Lehi] Updated zoning_code on %d parcels", updated)

    zone_map: dict[str, tuple[str, str]] = {}
    for _, row in zoning_gdf.iterrows():
        label = str(row["ZONE_LE_LABEL"]).strip()
        desc = str(row.get("ZONE_LE_DESC", "") or "")
        if label and label not in zone_map:
            zone_map[label] = (desc, classify_lehi(label, desc))

    counts: dict[str, int] = {}
    for _, (_, c) in zone_map.items():
        counts[c.self_storage] = counts.get(c.self_storage, 0) + 1
    logger.info("[Lehi] Zone distribution: %s", counts)
    for zc, (desc, cls) in sorted(zone_map.items()):
        logger.info("  %-20s %-40s → %s", zc, desc, cls.self_storage)

    await build_matrix(zone_map)

    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(p.id), COUNT(z.zone_code),
               ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id),0),1)
        FROM parcels p
        LEFT JOIN zone_use_matrix z
            ON z.jurisdiction_id=p.jurisdiction_id AND z.zone_code=p.zoning_code
        WHERE p.jurisdiction_id = %s
    """, (LEHI_JUR_ID,))
    row = cur.fetchone()
    conn.close()
    logger.info("[Lehi] Final match rate: %d/%d = %s%%", row[1], row[0], row[2])


if __name__ == "__main__":
    asyncio.run(main())
