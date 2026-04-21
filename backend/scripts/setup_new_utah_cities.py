"""
Setup script for 7 new Utah cities:
  - Salt Lake City, UT
  - Holladay, UT
  - Murray, UT
  - West Valley City, UT
  - Saratoga Springs, UT
  - Springville, UT
  - Spanish Fork, UT

Steps per city:
  1. Create jurisdiction record (if not exists)
  2. Download UGRC parcels
  3. Download zoning districts
  4. Spatial join zoning → parcels
  5. Build zone_use_matrix

Run from backend/ directory:
    python scripts/setup_new_utah_cities.py
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))

import geopandas as gpd
import psycopg2
import psycopg2.extras
import requests
from shapely.geometry import Point, shape
from shapely import make_valid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.zone_classifier import PerUseClassification, storage_cls

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DB_URL  = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"

UGRC_BASE = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services"


# ---------------------------------------------------------------------------
# City configuration
# ---------------------------------------------------------------------------

class CityConfig(NamedTuple):
    name: str
    state: str
    ugrc_service: str       # e.g. "Parcels_SaltLake"
    parcel_city: str        # filter value for PARCEL_CITY field
    zoning_url: str         # ArcGIS REST layer endpoint
    zone_field: str         # field containing zone code
    classifier: object      # callable(code: str) -> PerUseClassification


# ---------------------------------------------------------------------------
# Classifier functions
# ---------------------------------------------------------------------------

def classify_slc(code: str) -> PerUseClassification:
    u = (code or "").strip().upper()
    if re.match(r'^M-', u) or u in ("M1", "M2", "BP"):
        return storage_cls("permitted", 0.80, f"SLC industrial: {code}")
    if re.match(r'^C', u) or re.match(r'^D-', u) or u in ("TSA", "TSA-T", "TSA-UC", "TSA-SP"):
        return storage_cls("conditional", 0.70, f"SLC commercial: {code}")
    if re.match(r'^MU', u):
        return storage_cls("prohibited", 0.70, f"SLC mixed use — residential-oriented: {code}")
    if re.match(r'^R', u) or re.match(r'^OS', u) or u in ("AG", "EI", "UI", "FB-UN1", "FB-UN2", "FB-SC", "FB-SE"):
        return storage_cls("prohibited", 0.78, f"SLC residential/civic: {code}")
    logger.warning("[SLC] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"SLC unknown zone code '{code}' — conservative default")


def classify_holladay(code: str) -> PerUseClassification:
    u = (code or "").strip().upper()
    if re.match(r'^I-', u) or re.match(r'^M-', u):
        return storage_cls("permitted", 0.80, f"Holladay industrial: {code}")
    if re.match(r'^C-', u):
        return storage_cls("conditional", 0.70, f"Holladay commercial: {code}")
    if u == "MU":
        return storage_cls("prohibited", 0.70, "Holladay mixed use — residential-oriented")
    logger.warning("[Holladay] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Holladay unknown zone code '{code}' — conservative default")


def classify_murray(code: str) -> PerUseClassification:
    u = (code or "").strip().upper()
    if re.match(r'^I-', u) or re.match(r'^M-', u):
        return storage_cls("permitted", 0.80, f"Murray industrial: {code}")
    if re.match(r'^C', u) or u in ("B-1", "B-2", "M-1", "M-2"):
        return storage_cls("conditional", 0.70, f"Murray commercial: {code}")
    if u == "MU":
        return storage_cls("prohibited", 0.70, "Murray mixed use — residential-oriented")
    if re.match(r'^R', u) or re.match(r'^A-', u):
        return storage_cls("prohibited", 0.78, f"Murray residential/agricultural: {code}")
    logger.warning("[Murray] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Murray unknown zone code '{code}' — conservative default")


def classify_wvc(code: str) -> PerUseClassification:
    u = (code or "").strip().upper()
    if re.match(r'^M-', u) or re.match(r'^I-', u) or u in ("M1", "M2", "I1", "I2", "BP"):
        return storage_cls("permitted", 0.80, f"WVC industrial: {code}")
    if re.match(r'^C-', u) or re.match(r'^B-', u) or u in ("CC", "CG", "CN"):
        return storage_cls("conditional", 0.70, f"WVC commercial: {code}")
    if u == "MU":
        return storage_cls("prohibited", 0.70, "WVC mixed use — residential-oriented")
    if re.match(r'^R', u) or re.match(r'^A', u):
        return storage_cls("prohibited", 0.78, f"WVC residential/agricultural: {code}")
    logger.warning("[WVC] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"WVC unknown zone code '{code}' — conservative default")


def classify_saratoga_springs(code: str) -> PerUseClassification:
    u = (code or "").strip().upper()
    if re.match(r'^I-', u) or re.match(r'^M-', u) or u == "BP":
        return storage_cls("permitted", 0.80, f"Saratoga Springs industrial: {code}")
    if re.match(r'^C-', u):
        return storage_cls("conditional", 0.70, f"Saratoga Springs commercial: {code}")
    if re.match(r'^MU', u):
        return storage_cls("prohibited", 0.70, f"Saratoga Springs mixed use — residential-oriented: {code}")
    if re.match(r'^R', u) or re.match(r'^A', u) or re.match(r'^RA', u):
        return storage_cls("prohibited", 0.78, f"Saratoga Springs residential/agricultural: {code}")
    logger.warning("[Saratoga Springs] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Saratoga Springs unknown zone code '{code}' — conservative default")


def classify_springville(code: str) -> PerUseClassification:
    u = (code or "").strip().upper()
    if re.match(r'^M-', u) or re.match(r'^I-', u):
        return storage_cls("permitted", 0.80, f"Springville industrial: {code}")
    if re.match(r'^C-', u) or re.match(r'^B-', u) or u in ("CC", "CG"):
        return storage_cls("conditional", 0.70, f"Springville commercial: {code}")
    if u == "MU":
        return storage_cls("prohibited", 0.70, "Springville mixed use — residential-oriented")
    if re.match(r'^R', u) or re.match(r'^A', u):
        return storage_cls("prohibited", 0.78, f"Springville residential/agricultural: {code}")
    logger.warning("[Springville] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Springville unknown zone code '{code}' — conservative default")


def classify_spanish_fork(code: str) -> PerUseClassification:
    u = (code or "").strip().upper()
    if re.match(r'^M-', u) or re.match(r'^I-', u) or u == "BP":
        return storage_cls("permitted", 0.80, f"Spanish Fork industrial: {code}")
    if re.match(r'^C-', u) or re.match(r'^B-', u) or u in ("CC", "CG", "TC"):
        return storage_cls("conditional", 0.70, f"Spanish Fork commercial: {code}")
    if u == "MU":
        return storage_cls("prohibited", 0.70, "Spanish Fork mixed use — residential-oriented")
    if re.match(r'^R', u) or re.match(r'^A', u):
        return storage_cls("prohibited", 0.78, f"Spanish Fork residential/agricultural: {code}")
    logger.warning("[Spanish Fork] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Spanish Fork unknown zone code '{code}' — conservative default")


CITIES: list[CityConfig] = [
    CityConfig(
        name="Salt Lake City",
        state="UT",
        ugrc_service="Parcels_SaltLake",
        parcel_city="Salt Lake City",
        zoning_url="https://maps.slc.gov/server/rest/services/Viewers/Zoning/MapServer/0",
        zone_field="ZONING",
        classifier=classify_slc,
    ),
    CityConfig(
        name="Holladay",
        state="UT",
        ugrc_service="Parcels_SaltLake",
        parcel_city="Holladay",
        zoning_url="https://services6.arcgis.com/mGvwEqK9FI5j4ecF/arcgis/rest/services/Holladay_Zoning_Map_WFL1/FeatureServer/0",
        zone_field="ZONE",
        classifier=classify_holladay,
    ),
    CityConfig(
        name="Murray",
        state="UT",
        ugrc_service="Parcels_SaltLake",
        parcel_city="Murray",
        zoning_url="https://murraycemetery.org/web/rest/services/Public_Base_Layers/MapServer/8",
        zone_field="ZoningClass",
        classifier=classify_murray,
    ),
    CityConfig(
        name="West Valley City",
        state="UT",
        ugrc_service="Parcels_SaltLake",
        parcel_city="West Valley City",
        zoning_url="https://gisserver.wvc-ut.gov/server/rest/services/CityWebsite/ZoningSymbols_ZoningCityWebsite/MapServer/0",
        zone_field="ZONE_CODE",
        classifier=classify_wvc,
    ),
    CityConfig(
        name="Saratoga Springs",
        state="UT",
        ugrc_service="Parcels_Utah",
        parcel_city="Saratoga Springs",
        zoning_url="https://maps.utahcounty.gov/arcgis/rest/services/Assessor/CommercialAppraiser/MapServer/34",
        zone_field="ZONE_SR_LABEL",
        classifier=classify_saratoga_springs,
    ),
    CityConfig(
        name="Springville",
        state="UT",
        ugrc_service="Parcels_Utah",
        parcel_city="Springville",
        zoning_url="https://maps.utahcounty.gov/arcgis/rest/services/Assessor/CommercialAppraiser/MapServer/36",
        zone_field="ZONE_SP_LABEL",
        classifier=classify_springville,
    ),
    CityConfig(
        name="Spanish Fork",
        state="UT",
        ugrc_service="Parcels_Utah",
        parcel_city="Spanish Fork",
        zoning_url="https://maps.utahcounty.gov/arcgis/rest/services/Assessor/CommercialAppraiser/MapServer/35",
        zone_field="ZONE_SF_LABEL",
        classifier=classify_spanish_fork,
    ),
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_or_create_jurisdiction(city: CityConfig) -> str:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM jurisdictions WHERE name = %s AND state = %s",
        (city.name, city.state),
    )
    row = cur.fetchone()
    if row:
        jur_id = str(row[0])
        logger.info("[%s] Existing jurisdiction %s", city.name, jur_id)
    else:
        jur_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO jurisdictions (id, name, state) VALUES (%s, %s, %s)",
            (jur_id, city.name, city.state),
        )
        conn.commit()
        logger.info("[%s] Created jurisdiction %s", city.name, jur_id)
    conn.close()
    return jur_id


# ---------------------------------------------------------------------------
# Parcel download
# ---------------------------------------------------------------------------

def download_parcels(city: CityConfig) -> list[dict]:
    url = f"{UGRC_BASE}/{city.ugrc_service}/FeatureServer/0"
    logger.info("[%s] Downloading parcels from UGRC …", city.name)
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{url}/query", params={
            "where": f"PARCEL_CITY='{city.parcel_city}'",
            "outFields": "PARCEL_ID,PARCEL_ADD,CoParcel_URL,Shape__Area",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 2000,
        }, timeout=90)
        r.raise_for_status()
        feats = r.json().get("features", [])
        all_features.extend(feats)
        logger.info("  [%s] fetched %d (offset %d)", city.name, len(feats), offset)
        if len(feats) < 2000:
            break
        offset += len(feats)
    logger.info("[%s] Total parcels: %d", city.name, len(all_features))
    return all_features


def insert_parcels(city: CityConfig, jur_id: str, features: list[dict]) -> int:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("DELETE FROM parcels WHERE jurisdiction_id = %s", (jur_id,))
    logger.info("[%s] Inserting %d parcels …", city.name, len(features))

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
            jur_id, str(apn),
            str(address).strip() if address else None,
            acres, county_link,
            f"SRID=4326;{geom.wkt}",
            f"SRID=4326;{geom.centroid.wkt}",
        ))

        if len(batch) >= 500:
            psycopg2.extras.execute_batch(cur, """
                INSERT INTO parcels
                    (jurisdiction_id, apn, address, acres, county_link, geom, centroid)
                VALUES (%s,%s,%s,%s,%s, ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s))
                ON CONFLICT DO NOTHING
            """, batch)
            inserted += len(batch)
            logger.info("  [%s] inserted %d …", city.name, inserted)
            batch = []

    if batch:
        psycopg2.extras.execute_batch(cur, """
            INSERT INTO parcels
                (jurisdiction_id, apn, address, acres, county_link, geom, centroid)
            VALUES (%s,%s,%s,%s,%s, ST_GeomFromEWKT(%s), ST_GeomFromEWKT(%s))
            ON CONFLICT DO NOTHING
        """, batch)
        inserted += len(batch)

    conn.commit()
    conn.close()
    logger.info("[%s] Inserted %d parcels", city.name, inserted)
    return inserted


# ---------------------------------------------------------------------------
# Zoning download + spatial join
# ---------------------------------------------------------------------------

def download_zoning(city: CityConfig) -> gpd.GeoDataFrame:
    logger.info("[%s] Downloading zoning districts …", city.name)
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{city.zoning_url}/query", params={
            "where": "1=1",
            "outFields": city.zone_field,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": 1000,
        }, timeout=90)
        r.raise_for_status()
        feats = r.json().get("features", [])
        all_features.extend(feats)
        logger.info("  [%s] zoning fetched %d (offset %d)", city.name, len(feats), offset)
        if len(feats) < 1000:
            break
        offset += len(feats)

    if not all_features:
        raise RuntimeError(f"[{city.name}] No zoning features returned")

    gdf = gpd.GeoDataFrame.from_features(all_features, crs="EPSG:4326")
    # Normalize zone field name (GeoJSON may lowercase it)
    zone_col = city.zone_field
    if zone_col not in gdf.columns:
        zone_col = zone_col.lower()
    if zone_col not in gdf.columns:
        # Try case-insensitive match
        for col in gdf.columns:
            if col.lower() == city.zone_field.lower():
                zone_col = col
                break
    gdf = gdf.rename(columns={zone_col: "ZONE"})
    gdf = gdf.dropna(subset=["ZONE"])
    gdf = gdf[gdf["ZONE"].astype(str).str.strip() != ""]
    logger.info("[%s] %d zoning districts", city.name, len(gdf))
    return gdf


def load_centroids(jur_id: str) -> gpd.GeoDataFrame:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ST_X(centroid::geometry), ST_Y(centroid::geometry) "
        "FROM parcels WHERE jurisdiction_id = %s",
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
            result = await conn.execute(text(
                f"UPDATE parcels AS p SET zoning_code=v.zone "
                f"FROM (VALUES {values}) AS v(id,zone) WHERE p.id=v.id"
            ))
            updated += result.rowcount
    await engine.dispose()
    return updated


async def build_matrix(city: CityConfig, jur_id: str, zone_map: dict[str, PerUseClassification]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": jur_id},
        )
        for zone_code, cls in zone_map.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name,
                     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                     classification_source, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, :mw, :li, :lgc, 'rule', :conf, :notes)
            """), {
                "jid": jur_id,
                "zc": zone_code,
                "zn": zone_code,
                "ss": cls.self_storage, "mw": cls.mini_warehouse,
                "li": cls.light_industrial, "lgc": cls.luxury_garage_condo,
                "conf": cls.confidence, "notes": cls.notes,
            })
    await engine.dispose()
    logger.info("[%s] Inserted %d zone_use_matrix rows", city.name, len(zone_map))


# ---------------------------------------------------------------------------
# Per-city setup
# ---------------------------------------------------------------------------

async def setup_city(city: CityConfig) -> None:
    logger.info("=" * 60)
    logger.info("Setting up %s, %s", city.name, city.state)
    logger.info("=" * 60)

    jur_id = get_or_create_jurisdiction(city)

    # 1. Parcels
    try:
        features = download_parcels(city)
        if features:
            insert_parcels(city, jur_id, features)
        else:
            logger.warning("[%s] No parcels found — skipping", city.name)
            return
    except Exception as e:
        logger.error("[%s] Parcel download failed: %s", city.name, e)
        return

    # 2. Zoning
    try:
        zoning_gdf = download_zoning(city)
    except Exception as e:
        logger.error("[%s] Zoning download failed: %s", city.name, e)
        return

    # 3. Spatial join
    parcels_gdf = load_centroids(jur_id)
    logger.info("[%s] %d parcel centroids loaded", city.name, len(parcels_gdf))

    joined = gpd.sjoin(
        parcels_gdf,
        zoning_gdf[["ZONE", "geometry"]],
        how="left",
        predicate="within",
    )
    matched = joined.dropna(subset=["ZONE"])
    logger.info("[%s] Matched %d / %d parcels", city.name, len(matched), len(parcels_gdf))

    pairs = list(zip(matched["id"].tolist(), matched["ZONE"].tolist()))
    if pairs:
        updated = await update_zoning_codes(pairs)
        logger.info("[%s] Updated zoning_code on %d parcels", city.name, updated)

    # 4. Zone matrix
    zone_map: dict[str, PerUseClassification] = {}
    for _, row in zoning_gdf.iterrows():
        code = str(row["ZONE"]).strip()
        if code and code not in zone_map:
            zone_map[code] = city.classifier(code)

    counts: dict[str, int] = {}
    for cls in zone_map.values():
        counts[cls.self_storage] = counts.get(cls.self_storage, 0) + 1
    logger.info("[%s] Zone distribution: %s", city.name, counts)
    for zc, cls in sorted(zone_map.items()):
        logger.info("  %-25s → %s", zc, cls.self_storage)

    await build_matrix(city, jur_id, zone_map)

    # 5. Match rate
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(p.id), COUNT(z.zone_code),
               ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id), 0), 1)
        FROM parcels p
        LEFT JOIN zone_use_matrix z
            ON z.jurisdiction_id = p.jurisdiction_id
           AND z.zone_code = p.zoning_code
        WHERE p.jurisdiction_id = %s
    """, (jur_id,))
    row = cur.fetchone()
    conn.close()
    logger.info("[%s] Final match rate: %d/%d = %s%%", city.name, row[1], row[0], row[2])


async def main() -> None:
    for city in CITIES:
        try:
            await setup_city(city)
        except Exception as e:
            logger.error("[%s] FAILED: %s", city.name, e)
            import traceback
            traceback.print_exc()

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
