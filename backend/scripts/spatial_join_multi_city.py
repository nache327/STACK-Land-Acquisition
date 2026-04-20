"""
Spatial join zoning districts for multiple Utah cities.
Downloads zoning polygons from each city's ArcGIS service, spatially joins
them to parcel centroids, and updates zoning_code in the DB.

Run from backend/ directory:
    python scripts/spatial_join_multi_city.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
import psycopg2
import requests
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"


class CityConfig(NamedTuple):
    name: str
    jur_id: str
    service_url: str       # full URL to the layer endpoint (no trailing slash)
    zone_field: str        # field name that holds the zone code


CITIES: list[CityConfig] = [
    CityConfig(
        name="West Jordan",
        jur_id="f6273f2b-0911-440d-b639-fa80090f7f54",
        service_url="https://services1.arcgis.com/yznraL2FyB2Sm732/arcgis/rest/services/Landuse_And_Zoning/FeatureServer/0",
        zone_field="ZONE_NAME",
    ),
    CityConfig(
        name="Herriman",
        jur_id="8c489a6c-fdec-4d4d-98c1-3157d0233a8b",
        service_url="https://services2.arcgis.com/XBmqwOHlPh25M7aJ/arcgis/rest/services/HerrimanCityZoning/FeatureServer/0",
        zone_field="ZONE_",
    ),
    CityConfig(
        name="Hurricane",
        jur_id="648f20ae-ff2d-4876-b936-d67c20488eec",
        service_url="https://agisprodvm.washco.utah.gov/arcgis/rest/services/Zoning/MapServer/5",
        zone_field="ZONINGCODE",
    ),
    CityConfig(
        name="Washington",
        jur_id="cad6d22f-7447-4a26-8385-587e93f7f340",
        service_url="https://agisprodvm.washco.utah.gov/arcgis/rest/services/Zoning/MapServer/16",
        zone_field="ZONINGCODE",
    ),
    CityConfig(
        name="Kaysville",
        jur_id="0a9e2fb0-031a-4905-a07f-b645dadc5827",
        service_url="https://webmaps.kaysvillecity.com/arcgis/rest/services/Base/Zoning/MapServer/1",
        zone_field="NAME1_",
    ),
    # Farmington UT skipped — no public GIS service found (wrong-Farmington issue)
    CityConfig(
        name="American Fork",
        jur_id="d3757bf8-b4f1-4142-bece-8c774c863955",
        service_url="https://maps.afcity.org/arcgis/rest/services/Planning/Zoning/MapServer/0",
        zone_field="ZONECLASS",
    ),
    CityConfig(
        name="Bluffdale",
        jur_id="cb5017c6-a845-4ffd-91a3-7dc26e2e5ce9",
        service_url="https://services3.arcgis.com/ojBMkFlpg5ujUNtB/arcgis/rest/services/Zoning/FeatureServer/0",
        zone_field="Layer",
    ),
    CityConfig(
        name="Eagle Mountain",
        jur_id="1f0d6f93-8e5c-462b-88ed-9d6a9e107bc1",
        service_url="https://services1.arcgis.com/OZXOaoaD8hmdOtqR/arcgis/rest/services/General_Zoning_view/FeatureServer/0",
        zone_field="ThirdLevel",
    ),
    CityConfig(
        name="Cottonwood Heights",
        jur_id="b320fac8-d8ef-4325-8722-022036169218",
        service_url="https://gis.chcity.org/server/rest/services/CityData/Zoning_SD/MapServer/0",
        zone_field="Zoning",
    ),
    CityConfig(
        name="Draper",
        jur_id="6e618f70-ae79-4d2d-8548-fda3ea21823a",
        service_url="https://services2.arcgis.com/nAPVXppTJAHM40Se/arcgis/rest/services/Zoning/FeatureServer/5",
        zone_field="ZONING",
    ),
    CityConfig(
        name="Millcreek",
        jur_id="0fd008ca-1a7e-41d6-9995-c59c6fe8a8d9",
        service_url="https://services9.arcgis.com/XRrSFvEwSsReIxuA/arcgis/rest/services/Millcreek_Base_Zones_Aug_2022/FeatureServer/0",
        zone_field="ZONE_",
    ),
    CityConfig(
        name="Midvale",
        jur_id="5f366dff-dde9-471c-8fb2-58894796535d",
        service_url="https://gis.midvalecity.org:6443/arcgis/rest/services/Planning_and_Zoning/Zoning_District_and_Overlay_Service/MapServer/1",
        zone_field="Zone_Name",
    ),
]


def download_zoning_districts(city: CityConfig) -> gpd.GeoDataFrame:
    logger.info("[%s] Downloading zoning districts …", city.name)
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{city.service_url}/query", params={
            "where": "1=1",
            "outFields": city.zone_field,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 1000,
        }, timeout=60)
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])
        all_features.extend(features)
        logger.info("  [%s] fetched %d (offset %d)", city.name, len(features), offset)
        if len(features) < 1000:
            break
        offset += len(features)

    if not all_features:
        raise RuntimeError(f"No zoning features returned for {city.name}")

    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
    # Normalise: rename city-specific zone field to a common 'ZONE' column
    if city.zone_field in gdf.columns:
        gdf = gdf.rename(columns={city.zone_field: "ZONE"})
    else:
        # field may become lowercase in geojson
        lc = city.zone_field.lower()
        if lc in gdf.columns:
            gdf = gdf.rename(columns={lc: "ZONE"})
    gdf = gdf.dropna(subset=["ZONE"])
    gdf = gdf[gdf["ZONE"].astype(str).str.strip() != ""]
    logger.info("[%s] %d zoning districts", city.name, len(gdf))
    return gdf


def load_parcel_centroids(jur_id: str) -> gpd.GeoDataFrame:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ST_X(centroid::geometry) AS lon, ST_Y(centroid::geometry) AS lat "
        "FROM parcels WHERE jurisdiction_id = %s",
        (jur_id,),
    )
    rows = cur.fetchall()
    conn.close()
    ids = [r[0] for r in rows]
    geometry = [Point(r[1], r[2]) for r in rows]
    return gpd.GeoDataFrame({"id": ids}, geometry=geometry, crs="EPSG:4326")


async def update_zoning_codes(id_zone_pairs: list[tuple]) -> int:
    engine = create_async_engine(DB_URL)
    updated = 0
    BATCH = 500
    async with engine.begin() as conn:
        for i in range(0, len(id_zone_pairs), BATCH):
            batch = id_zone_pairs[i: i + BATCH]
            values = ", ".join(f"({pid}, $${zone}$$)" for pid, zone in batch)
            sql = f"""
                UPDATE parcels AS p
                SET zoning_code = v.zone
                FROM (VALUES {values}) AS v(id, zone)
                WHERE p.id = v.id
            """
            result = await conn.execute(text(sql))
            updated += result.rowcount
    return updated


async def process_city(city: CityConfig) -> None:
    logger.info("===== %s =====", city.name)
    try:
        zones_gdf = download_zoning_districts(city)
    except Exception as e:
        logger.error("[%s] Download failed: %s", city.name, e)
        return

    parcels_gdf = load_parcel_centroids(city.jur_id)
    logger.info("[%s] %d parcel centroids loaded", city.name, len(parcels_gdf))

    if parcels_gdf.empty:
        logger.warning("[%s] No parcels found — skipping", city.name)
        return

    joined = gpd.sjoin(parcels_gdf, zones_gdf[["ZONE", "geometry"]], how="left", predicate="within")
    matched = joined.dropna(subset=["ZONE"])
    logger.info("[%s] matched %d / %d parcels", city.name, len(matched), len(parcels_gdf))

    pairs = list(zip(matched["id"].tolist(), matched["ZONE"].tolist()))
    if not pairs:
        logger.warning("[%s] No spatial matches — check CRS or coverage", city.name)
        return

    updated = await update_zoning_codes(pairs)
    logger.info("[%s] DONE — %d parcels updated", city.name, updated)


async def main() -> None:
    for city in CITIES:
        await process_city(city)
    logger.info("All cities complete.")


if __name__ == "__main__":
    asyncio.run(main())
