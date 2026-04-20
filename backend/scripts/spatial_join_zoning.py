"""
Spatial join: download Sandy City zoning districts and assign zoning_code
to every parcel whose centroid falls within a district polygon.

Run from backend/ directory:
    python scripts/spatial_join_zoning.py

Requires: geopandas, shapely, sqlalchemy, asyncpg
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
import requests
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"

SANDY_JUR_ID = "0cf50881-fdf3-4149-8c9f-6db758c4a08f"

ZONING_SERVICE = "https://gis.sandy.utah.gov/arcgis/rest/services/Common/Zoning/MapServer/0"


def download_zoning_districts() -> gpd.GeoDataFrame:
    """Download all zoning district polygons from Sandy's MapServer."""
    logger.info("Downloading Sandy zoning districts …")
    params = {
        "where": "1=1",
        "outFields": "ZONE,Zone_Code,NAME",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    # Page through results
    all_features = []
    offset = 0
    while True:
        params["resultOffset"] = offset
        params["resultRecordCount"] = 1000
        r = requests.get(f"{ZONING_SERVICE}/query", params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])
        all_features.extend(features)
        logger.info("  Fetched %d features (offset %d)", len(features), offset)
        if len(features) < 1000:
            break
        offset += len(features)

    if not all_features:
        raise RuntimeError("No zoning features returned from Sandy GIS")

    import json
    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
    logger.info("Downloaded %d zoning districts", len(gdf))
    return gdf


def download_parcel_centroids() -> gpd.GeoDataFrame:
    """Download parcel id + centroid from Supabase using psycopg2 directly."""
    import psycopg2
    # Use sync connection for simplicity
    conn_str = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"
    logger.info("Loading parcel centroids from DB …")
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, ST_X(centroid::geometry) AS lon, ST_Y(centroid::geometry) AS lat
        FROM parcels
        WHERE jurisdiction_id = %s
        """,
        (SANDY_JUR_ID,),
    )
    rows = cur.fetchall()
    conn.close()
    logger.info("Loaded %d parcel centroids", len(rows))

    ids = [r[0] for r in rows]
    geometry = [Point(r[1], r[2]) for r in rows]
    gdf = gpd.GeoDataFrame({"id": ids}, geometry=geometry, crs="EPSG:4326")
    return gdf


async def update_zoning_codes(id_zone_pairs: list[tuple]) -> int:
    """Batch-update zoning_code for matched parcels."""
    engine = create_async_engine(DB_URL)
    updated = 0
    BATCH = 500
    async with engine.begin() as conn:
        for i in range(0, len(id_zone_pairs), BATCH):
            batch = id_zone_pairs[i : i + BATCH]
            # Build VALUES list
            values = ", ".join(f"({pid}, '{zone}')" for pid, zone in batch)
            sql = f"""
                UPDATE parcels AS p
                SET zoning_code = v.zone
                FROM (VALUES {values}) AS v(id, zone)
                WHERE p.id = v.id
            """
            result = await conn.execute(text(sql))
            updated += result.rowcount
            logger.info("Updated batch %d/%d — %d total", i // BATCH + 1, -(-len(id_zone_pairs) // BATCH), updated)
    return updated


async def main() -> None:
    # 1. Download zoning districts
    zones_gdf = download_zoning_districts()

    # 2. Download parcel centroids
    parcels_gdf = download_parcel_centroids()

    # 3. Spatial join: find which zone polygon each parcel centroid falls in
    logger.info("Running spatial join …")
    joined = gpd.sjoin(parcels_gdf, zones_gdf[["ZONE", "geometry"]], how="left", predicate="within")
    matched = joined.dropna(subset=["ZONE"])
    logger.info("Matched %d / %d parcels to a zone", len(matched), len(parcels_gdf))

    # 4. Update DB
    pairs = list(zip(matched["id"].tolist(), matched["ZONE"].tolist()))
    if not pairs:
        logger.error("No matches — check CRS or geometry alignment")
        return

    updated = await update_zoning_codes(pairs)
    logger.info("=== DONE: %d parcels updated with zoning codes ===", updated)


if __name__ == "__main__":
    asyncio.run(main())
