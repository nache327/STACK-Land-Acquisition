"""
Full setup for Orem, UT and Lindon, UT.

Run from backend/ directory:
    python scripts/setup_orem_lindon.py
"""
from __future__ import annotations

import asyncio
import logging
import re
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL  = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"

UGRC_PARCELS = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Utah/FeatureServer/0"
UTCO_GIS     = "https://maps.utahcounty.gov/arcgis/rest/services/Assessor/CommercialAppraiser/MapServer"

CITY_CONFIGS = [
    {
        "name": "Orem",
        "existing_jur_id": "47fb1539-2aff-4b1c-8e8b-58ff6a6f08c7",
        "parcel_city": "Orem",
        "zoning_layer": 28,
        "label_field": "ZONE_OR_LABEL",
        "desc_field": "ZONE_OR_DESC",
    },
    {
        "name": "Lindon",
        "existing_jur_id": None,
        "parcel_city": "Lindon",
        "zoning_layer": 26,
        "label_field": "ZONE_LI_LABEL",
        "desc_field": "ZONE_LI_DESC",
    },
]


def classify_orem(label: str, desc: str) -> PerUseClassification:
    u = label.strip().upper()
    d = (desc or "").strip().upper()

    if u in ("M1", "M2", "CM") or d == "INDUSTRIAL":
        return storage_cls("permitted", 0.80, f"Orem industrial: {label}")
    if u in ("BP", "C1", "C2", "C3", "HS", "IO", "PO", "UX"):
        return storage_cls("conditional", 0.70, f"Orem commercial: {label}")
    if d == "COMMERCIAL" or d == "PLANNED DEVELOPMENT":
        return storage_cls("conditional", 0.68, f"Orem commercial (desc): {label}")
    if d == "MIXED USE":
        return storage_cls("prohibited", 0.70, f"Orem mixed use — residential-oriented: {label}")
    if u in ("AGO", "HR"):
        return storage_cls("conditional", 0.60, f"Orem overlay: {label}")
    if u in ("ASH", "HO", "OS5", "PF", "SH") or d == "RESIDENTIAL":
        return storage_cls("prohibited", 0.78, f"Orem civic/residential: {label}")
    if re.match(r'^R\d', u) or u in ("PRD", "PRD(UX)"):
        return storage_cls("prohibited", 0.80, f"Orem residential: {label}")
    logger.warning("[Orem] Unknown code '%s' (%s) — prohibited (conservative default)", label, desc)
    return storage_cls("prohibited", 0.45, f"Orem unknown zone code '{label}' — conservative default")


def classify_lindon(label: str, desc: str) -> PerUseClassification:
    u = label.strip().upper()

    if u in ("HI", "LI", "LI-W", "RB"):
        return storage_cls("permitted", 0.80, f"Lindon industrial: {label}")
    if u == "CG-S":
        return storage_cls("permitted", 0.85, "Lindon commercial storage zone")
    if u in ("PC-1", "PC-2"):
        return storage_cls("prohibited", 0.75, f"Lindon planned community — residential: {label}")
    if u == "RC":
        return storage_cls("prohibited", 0.75, "Lindon rural community — residential")
    if u in ("CF", "CG", "CG-A", "CG-A8", "LVC", "MC", "RBO", "SPOD", "AFPD"):
        return storage_cls("conditional", 0.70, f"Lindon commercial: {label}")
    if u in ("RMU-E", "RMU-W"):
        return storage_cls("prohibited", 0.72, f"Lindon residential mixed use: {label}")
    if u in ("PF", "PF-HSO", "PRD", "SHFO"):
        return storage_cls("prohibited", 0.78, f"Lindon public/residential: {label}")
    if re.match(r'^R[13]', u) or re.match(r'^R1-', u):
        return storage_cls("prohibited", 0.80, f"Lindon residential: {label}")
    logger.warning("[Lindon] Unknown code '%s' (%s) — prohibited (conservative default)", label, desc)
    return storage_cls("prohibited", 0.45, f"Lindon unknown zone code '{label}' — conservative default")


CLASSIFIERS = {"Orem": classify_orem, "Lindon": classify_lindon}


def ensure_jurisdiction(name: str, existing_id: str | None) -> str:
    if existing_id:
        return existing_id
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("SELECT id FROM jurisdictions WHERE name=%s AND state='UT'", (name,))
    row = cur.fetchone()
    if row:
        jur_id = str(row[0])
    else:
        jur_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO jurisdictions (id, name, state, county) VALUES (%s,%s,'UT','Utah')",
            (jur_id, name),
        )
        conn.commit()
        logger.info("[%s] Created jurisdiction: %s", name, jur_id)
    conn.close()
    return jur_id


def download_ugrc_parcels(parcel_city: str, name: str) -> list[dict]:
    logger.info("[%s] Downloading UGRC parcels …", name)
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{UGRC_PARCELS}/query", params={
            "where": f"PARCEL_CITY='{parcel_city}'",
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
    logger.info("[%s] Total UGRC parcels: %d", name, len(all_features))
    return all_features


def insert_parcels(features: list[dict], jur_id: str, name: str) -> int:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("DELETE FROM parcels WHERE jurisdiction_id=%s", (jur_id,))

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
            jur_id, str(apn),
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
    logger.info("[%s] Inserted %d parcels", name, inserted)
    return inserted


def download_zoning(layer_id: int, label_field: str, desc_field: str, name: str) -> gpd.GeoDataFrame:
    logger.info("[%s] Downloading zoning (layer %d) …", name, layer_id)
    all_features: list = []
    offset = 0
    while True:
        r = requests.get(f"{UTCO_GIS}/{layer_id}/query", params={
            "where": "1=1",
            "outFields": f"{label_field},{desc_field}",
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
    gdf = gdf.dropna(subset=[label_field])
    gdf = gdf[gdf[label_field].astype(str).str.strip() != ""]
    logger.info("[%s] %d zoning districts", name, len(gdf))
    return gdf


def load_centroids(jur_id: str) -> gpd.GeoDataFrame:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ST_X(centroid::geometry), ST_Y(centroid::geometry) "
        "FROM parcels WHERE jurisdiction_id=%s", (jur_id,),
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


async def build_matrix(jur_id: str, name: str, zone_map: dict[str, tuple[str, PerUseClassification]]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id=:jid"), {"jid": jur_id}
        )
        for zone_code, (desc, cls) in zone_map.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name,
                     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                     classification_source, confidence, notes)
                VALUES (:jid,:zc,:zn,:ss,:mw,:li,:lgc,'rule',:conf,:notes)
            """), {
                "jid": jur_id, "zc": zone_code, "zn": desc or zone_code,
                "ss": cls.self_storage, "mw": cls.mini_warehouse,
                "li": cls.light_industrial, "lgc": cls.luxury_garage_condo,
                "conf": cls.confidence, "notes": cls.notes,
            })
    await engine.dispose()
    logger.info("[%s] Inserted %d zone_use_matrix rows", name, len(zone_map))


async def process_city(cfg: dict) -> None:
    name = cfg["name"]
    logger.info("===== %s =====", name)
    jur_id = ensure_jurisdiction(name, cfg["existing_jur_id"])
    classifier = CLASSIFIERS[name]

    features = download_ugrc_parcels(cfg["parcel_city"], name)
    insert_parcels(features, jur_id, name)

    zoning_gdf = download_zoning(cfg["zoning_layer"], cfg["label_field"], cfg["desc_field"], name)
    parcels_gdf = load_centroids(jur_id)
    logger.info("[%s] %d parcel centroids loaded", name, len(parcels_gdf))

    joined = gpd.sjoin(
        parcels_gdf,
        zoning_gdf[[cfg["label_field"], cfg["desc_field"], "geometry"]],
        how="left", predicate="within",
    )
    matched = joined.dropna(subset=[cfg["label_field"]])
    logger.info("[%s] Matched %d / %d parcels", name, len(matched), len(parcels_gdf))

    pairs = list(zip(matched["id"].tolist(), matched[cfg["label_field"]].tolist()))
    if pairs:
        updated = await update_zoning_codes(pairs)
        logger.info("[%s] Updated zoning_code on %d parcels", name, updated)

    zone_map: dict[str, tuple[str, PerUseClassification]] = {}
    for _, row in zoning_gdf.iterrows():
        label = str(row[cfg["label_field"]]).strip()
        desc  = str(row.get(cfg["desc_field"], "") or "")
        if label and label not in zone_map:
            zone_map[label] = (desc, classifier(label, desc))

    counts: dict[str, int] = {}
    for _, (_, c) in zone_map.items():
        counts[c.self_storage] = counts.get(c.self_storage, 0) + 1
    logger.info("[%s] Zone distribution: %s", name, counts)
    for zc, (desc, cls) in sorted(zone_map.items()):
        logger.info("  %-22s %-38s → %s", zc, desc, cls.self_storage)

    await build_matrix(jur_id, name, zone_map)

    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(p.id), COUNT(z.zone_code),
               ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id),0),1)
        FROM parcels p
        LEFT JOIN zone_use_matrix z
            ON z.jurisdiction_id=p.jurisdiction_id AND z.zone_code=p.zoning_code
        WHERE p.jurisdiction_id=%s
    """, (jur_id,))
    row = cur.fetchone()
    conn.close()
    logger.info("[%s] Final match rate: %d/%d = %s%%", name, row[1], row[0], row[2])


async def main() -> None:
    for cfg in CITY_CONFIGS:
        await process_city(cfg)


if __name__ == "__main__":
    asyncio.run(main())
