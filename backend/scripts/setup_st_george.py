"""
Full setup for St. George, UT:
  1. Download UGRC Washington County parcels → insert into DB
  2. Download Washington County GIS zoning (layer 11) → spatial join → update zoning_code
  3. Build zone_use_matrix from ZONINGCODE + GEN_ZONE

Run from backend/ directory:
    python scripts/setup_st_george.py
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
from scripts._db import get_dsn, get_sync_dsn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL = get_dsn()
DB_SYNC = get_sync_dsn()

SG_JUR_ID = "86792c7c-76dd-45f8-a382-409097147a8f"

UGRC_PARCELS = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Washington/FeatureServer/0"
ZONING_URL   = "https://agisprodvm.washco.utah.gov/arcgis/rest/services/Zoning/MapServer/11"

# GEN_ZONE → self_storage permission string (used by classify_st_george)
GEN_ZONE_MAP = {
    "Agriculture":              "conditional",
    "Airport/Services":         "conditional",
    "Commercial":               "conditional",
    "Industrial/Manufacturing": "permitted",
    "Mining/Grazing":           "conditional",
    "Mixed Use":                "prohibited",
    "Open Space/Parks":         "prohibited",
    "Professional/Office":      "conditional",
    "Recreation/Resort":        "prohibited",
    "Residential":              "prohibited",
}

# Specific ZONINGCODE overrides (take precedence over GEN_ZONE)
ZONE_OVERRIDE = {
    "M-1":    "permitted",
    "M-2":    "permitted",
    "M-C":    "permitted",
    "AVI":    "permitted",
    "PD-MNF": "permitted",
    "OS":     "prohibited",
    "M&G":    "conditional",
    "RESORT_OVERLAY": "prohibited",
    "PD-SH":  "prohibited",
    "PD-MH":  "prohibited",
    "MH-6":   "prohibited",
    "M-H":    "prohibited",
}


def classify_st_george(zone_code: str, gen_zone: str | None) -> PerUseClassification:
    perm = ZONE_OVERRIDE.get(zone_code)
    if perm is None and gen_zone:
        perm = GEN_ZONE_MAP.get(gen_zone)
    if perm is None:
        u = zone_code.strip().upper()
        if re.match(r'^R[-\s]', u) or u in ("RCC", "PD-R", "PD"):
            perm = "prohibited"
        elif re.match(r'^A-', u):
            perm = "conditional"
        elif re.match(r'^C-', u) or re.match(r'^PD-C', u) or re.match(r'^PD-AP', u):
            perm = "conditional"
        else:
            logger.warning("[St. George] Unknown code '%s' (gen_zone=%s) — prohibited (conservative default)", zone_code, gen_zone)
            perm = "prohibited"
    return storage_cls(perm, 0.72, f"St. George: {zone_code}/{gen_zone}")


# ── Step 1: Download UGRC parcels ──────────────────────────────────────────────

def download_ugrc_parcels() -> list[dict]:
    logger.info("[St. George] Downloading UGRC parcels …")
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{UGRC_PARCELS}/query", params={
            "where": "PARCEL_CITY='St. George'",
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
    logger.info("[St. George] Total UGRC parcels: %d", len(all_features))
    return all_features


def insert_parcels(features: list[dict]) -> int:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()

    # Delete existing
    cur.execute("DELETE FROM parcels WHERE jurisdiction_id = %s", (SG_JUR_ID,))
    logger.info("[St. George] Deleted old parcels, inserting %d new …", len(features))

    inserted = 0
    batch = []
    for feat in features:
        props = feat.get("properties", {})
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
            geom_wkt = geom.wkt
            centroid_wkt = geom.centroid.wkt
        except Exception:
            continue

        address = props.get("PARCEL_ADD") or props.get("parcel_add")
        # Washington County uses Shape__Area (sq meters) — convert to acres
        sqm = props.get("Shape__Area") or props.get("shape__area")
        try:
            acres = round(float(sqm) / 4046.856, 4) if sqm is not None else None
        except (ValueError, TypeError):
            acres = None
        county_link = props.get("CoParcel_URL") or props.get("coparcel_url")

        batch.append((
            SG_JUR_ID,
            str(apn),
            str(address).strip() if address else None,
            acres,
            county_link,
            f"SRID=4326;{geom_wkt}",
            f"SRID=4326;{centroid_wkt}",
        ))

        if len(batch) >= 500:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO parcels (jurisdiction_id, apn, address, acres, county_link, geom, centroid)
                VALUES (%s, %s, %s, %s, %s,
                    ST_GeomFromEWKT(%s),
                    ST_GeomFromEWKT(%s))
                ON CONFLICT DO NOTHING
            """, batch)
            inserted += len(batch)
            logger.info("  inserted %d …", inserted)
            batch = []

    if batch:
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO parcels (jurisdiction_id, apn, address, acres, county_link, geom, centroid)
            VALUES (%s, %s, %s, %s, %s,
                ST_GeomFromEWKT(%s),
                ST_GeomFromEWKT(%s))
            ON CONFLICT DO NOTHING
        """, batch)
        inserted += len(batch)

    conn.commit()
    conn.close()
    logger.info("[St. George] Inserted %d parcels", inserted)
    return inserted


# ── Step 2: Download zoning + spatial join ─────────────────────────────────────

def download_zoning() -> gpd.GeoDataFrame:
    logger.info("[St. George] Downloading zoning districts …")
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{ZONING_URL}/query", params={
            "where": "1=1",
            "outFields": "ZONINGCODE,GEN_ZONE,DESCRIPTION",
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
    gdf = gdf.dropna(subset=["ZONINGCODE"])
    gdf = gdf[gdf["ZONINGCODE"].astype(str).str.strip() != ""]
    logger.info("[St. George] %d zoning districts", len(gdf))
    return gdf


def load_centroids() -> gpd.GeoDataFrame:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ST_X(centroid::geometry), ST_Y(centroid::geometry) "
        "FROM parcels WHERE jurisdiction_id = %s",
        (SG_JUR_ID,),
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


# ── Step 3: Build zone_use_matrix ──────────────────────────────────────────────

async def build_matrix(zone_map: dict[str, tuple[str, PerUseClassification]]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": SG_JUR_ID},
        )
        for zone_code, (gen_zone, cls) in zone_map.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name,
                     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                     classification_source, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, :mw, :li, :lgc, 'rule', :conf, :notes)
            """), {
                "jid": SG_JUR_ID,
                "zc": zone_code,
                "zn": gen_zone or zone_code,
                "ss": cls.self_storage, "mw": cls.mini_warehouse,
                "li": cls.light_industrial, "lgc": cls.luxury_garage_condo,
                "conf": cls.confidence, "notes": cls.notes,
            })
    await engine.dispose()
    logger.info("[St. George] Inserted %d zone_use_matrix rows", len(zone_map))


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    # 1. Parcels
    features = download_ugrc_parcels()
    insert_parcels(features)

    # 2. Zoning spatial join
    zoning_gdf = download_zoning()
    parcels_gdf = load_centroids()
    logger.info("[St. George] %d parcel centroids loaded", len(parcels_gdf))

    joined = gpd.sjoin(parcels_gdf, zoning_gdf[["ZONINGCODE", "GEN_ZONE", "geometry"]], how="left", predicate="within")
    matched = joined.dropna(subset=["ZONINGCODE"])
    logger.info("[St. George] Matched %d / %d parcels", len(matched), len(parcels_gdf))

    pairs = list(zip(matched["id"].tolist(), matched["ZONINGCODE"].tolist()))
    if pairs:
        updated = await update_zoning_codes(pairs)
        logger.info("[St. George] Updated zoning_code on %d parcels", updated)

    # 3. Build zone_use_matrix from distinct (ZONINGCODE, GEN_ZONE) pairs
    zone_map: dict[str, tuple[str, PerUseClassification]] = {}
    for _, row in zoning_gdf.iterrows():
        zc = str(row["ZONINGCODE"]).strip()
        gz = str(row.get("GEN_ZONE", "") or "")
        if zc and zc not in zone_map:
            cls = classify_st_george(zc, gz or None)
            zone_map[zc] = (gz, cls)

    counts: dict[str, int] = {}
    for _, (_, c) in zone_map.items():
        counts[c.self_storage] = counts.get(c.self_storage, 0) + 1
    logger.info("[St. George] Zone classification distribution: %s", counts)
    for zc, (gz, cls) in sorted(zone_map.items()):
        logger.info("  %-20s %-28s → %s", zc, gz, cls.self_storage)

    await build_matrix(zone_map)

    # Final match rate
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(p.id), COUNT(z.zone_code),
               ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id), 0), 1)
        FROM parcels p
        LEFT JOIN zone_use_matrix z
            ON z.jurisdiction_id = p.jurisdiction_id AND z.zone_code = p.zoning_code
        WHERE p.jurisdiction_id = %s
    """, (SG_JUR_ID,))
    row = cur.fetchone()
    conn.close()
    logger.info("[St. George] Final match rate: %d/%d = %s%%", row[1], row[0], row[2])


if __name__ == "__main__":
    asyncio.run(main())
