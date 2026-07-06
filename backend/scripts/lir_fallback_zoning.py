"""
Fallback zoning assignment using AGRC county LIR parcel PROP_CLASS.

For cities without accessible public zoning district services, spatial-join
parcel centroids to county LIR parcel polygons and store PROP_CLASS as a
pseudo zoning_code, then populate zone_use_matrix with appropriate
self-storage classifications.

Cities handled:
  - Draper       (NULL parcels only — 9,261 gaps)
  - Farmington   (all parcels — 0% coverage)
  - West Haven   (all parcels — 0% coverage)
  - Ogden        (all parcels — 0% coverage)

Run from backend/ directory:
    python scripts/lir_fallback_zoning.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
import psycopg2
import requests
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts._db import get_dsn, get_sync_dsn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL = get_dsn()
DB_SYNC = get_sync_dsn()

LIR_SALT_LAKE = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_SaltLake_LIR/FeatureServer/0"
LIR_DAVIS     = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Davis_LIR/FeatureServer/0"
LIR_WEBER     = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Weber_LIR/FeatureServer/0"

# PROP_CLASS → self_storage classification
PROP_CLASS_MAP: dict[str, str] = {
    "Residential":                                  "prohibited",
    "Commercial - Apartment & Condo":               "prohibited",
    "Tax Exempt":                                   "prohibited",
    "Tax Exempt - Government":                      "prohibited",
    "Tax Exempt - Charitable Organization or Religious": "prohibited",
    "Greenbelt":                                    "prohibited",
    "Commercial":                                   "conditional",
    "Commercial - Retail":                          "conditional",
    "Commercial - Office Space":                    "conditional",
    "Mixed Use":                                    "conditional",
    "Centrally Assessed":                           "conditional",
    "Vacant":                                       "conditional",
    "Vacant - Agricultural":                        "conditional",
    "Vacant - Commercial":                          "conditional",
    "Undeveloped":                                  "conditional",
    "Commercial - Industrial":                      "permitted",
    "Industrial":                                   "permitted",
}

CITY_CONFIGS = [
    {
        "name": "Draper",
        "jur_id": "6e618f70-ae79-4d2d-8548-fda3ea21823a",
        "lir_url": LIR_SALT_LAKE,
        "city_name": "Draper",
        "null_only": True,   # Only fill parcels with no zoning_code
    },
    {
        "name": "Farmington",
        "jur_id": "f90d021b-98fe-47b0-ad31-bf8c1b2dd23f",
        "lir_url": LIR_DAVIS,
        "city_name": "Farmington",
        "null_only": False,
    },
    {
        "name": "West Haven",
        "jur_id": "60506efb-2485-4198-ad01-9419941cc78d",
        "lir_url": LIR_WEBER,
        "city_name": "West Haven",
        "null_only": False,
    },
    {
        "name": "Ogden",
        "jur_id": "fe0f482f-da80-4673-b83b-556b0cca7ba4",
        "lir_url": LIR_WEBER,
        "city_name": "Ogden",
        "null_only": False,
    },
]


def download_lir(lir_url: str, city_name: str) -> gpd.GeoDataFrame:
    """Download LIR parcel polygons with PROP_CLASS for a city."""
    all_features: list = []
    offset = 0
    where = f"PARCEL_CITY='{city_name}'"
    while True:
        r = requests.get(f"{lir_url}/query", params={
            "where": where,
            "outFields": "PROP_CLASS",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 2000,
        }, timeout=60)
        r.raise_for_status()
        feats = r.json().get("features", [])
        all_features.extend(feats)
        logger.info("  [%s] fetched %d LIR parcels (offset %d)", city_name, len(feats), offset)
        if len(feats) < 2000:
            break
        offset += len(feats)

    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
    gdf = gdf.dropna(subset=["PROP_CLASS"])
    gdf = gdf[gdf["PROP_CLASS"].astype(str).str.strip() != ""]
    logger.info("[%s] %d LIR polygons with PROP_CLASS", city_name, len(gdf))
    return gdf


def load_parcels(jur_id: str, null_only: bool) -> gpd.GeoDataFrame:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    if null_only:
        cur.execute(
            "SELECT id, ST_X(centroid::geometry), ST_Y(centroid::geometry) "
            "FROM parcels WHERE jurisdiction_id=%s AND zoning_code IS NULL",
            (jur_id,),
        )
    else:
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


async def update_parcels(pairs: list[tuple]) -> int:
    engine = create_async_engine(DB_URL)
    updated = 0
    async with engine.begin() as conn:
        for i in range(0, len(pairs), 500):
            batch = pairs[i:i + 500]
            values = ", ".join(f"({pid}, $${pc}$$)" for pid, pc in batch)
            result = await conn.execute(
                text(f"UPDATE parcels AS p SET zoning_code=v.zone "
                     f"FROM (VALUES {values}) AS v(id,zone) WHERE p.id=v.id")
            )
            updated += result.rowcount
    await engine.dispose()
    return updated


async def upsert_matrix(jur_id: str, prop_classes: set[str]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        for pc in prop_classes:
            perm = PROP_CLASS_MAP.get(pc, "conditional")
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name, self_storage, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, 0.6, :n)
                ON CONFLICT (jurisdiction_id, zone_code) DO NOTHING
            """), {
                "jid": jur_id, "zc": pc, "zn": pc, "ss": perm,
                "n": "AGRC LIR PROP_CLASS fallback classification",
            })
    await engine.dispose()


async def process_city(cfg: dict) -> None:
    name = cfg["name"]
    logger.info("===== %s =====", name)

    try:
        lir_gdf = download_lir(cfg["lir_url"], cfg["city_name"])
    except Exception as e:
        logger.error("[%s] LIR download failed: %s", name, e)
        return

    parcels_gdf = load_parcels(cfg["jur_id"], cfg["null_only"])
    logger.info("[%s] %d target parcel centroids", name, len(parcels_gdf))
    if parcels_gdf.empty:
        logger.warning("[%s] No target parcels", name)
        return

    joined = gpd.sjoin(parcels_gdf, lir_gdf[["PROP_CLASS", "geometry"]], how="left", predicate="within")
    matched = joined.dropna(subset=["PROP_CLASS"])
    logger.info("[%s] Matched %d / %d parcels", name, len(matched), len(parcels_gdf))

    pairs = list(zip(matched["id"].tolist(), matched["PROP_CLASS"].tolist()))
    if not pairs:
        logger.warning("[%s] No matches — check coverage", name)
        return

    updated = await update_parcels(pairs)
    logger.info("[%s] Updated %d parcels", name, updated)

    prop_classes = set(matched["PROP_CLASS"].tolist())
    await upsert_matrix(cfg["jur_id"], prop_classes)
    logger.info("[%s] Matrix entries upserted for: %s", name, prop_classes)


async def main() -> None:
    for cfg in CITY_CONFIGS:
        await process_city(cfg)

    # Final match rates
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT j.name,
               COUNT(p.id) AS total,
               COUNT(z.zone_code) AS matched,
               ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id), 0), 1) AS pct
        FROM jurisdictions j
        JOIN parcels p ON p.jurisdiction_id = j.id
        LEFT JOIN zone_use_matrix z ON z.jurisdiction_id = j.id AND z.zone_code = p.zoning_code
        WHERE j.name IN ('Draper City, UT', 'Farmington', 'West Haven', 'Ogden')
        GROUP BY j.name ORDER BY pct DESC
    """)
    logger.info("Final match rates:")
    for row in cur.fetchall():
        logger.info("  %-25s %6d/%d = %s%%", row[0], row[2], row[1], row[3])
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
