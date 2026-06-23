"""Phase 7H.x — Mecklenburg NC / South Charlotte Class B prep adapter.

PREP — DO NOT FIRE from this PR.

Pattern: PR #334 Winnetka single-file adapter + NC OneMap parcel ingest
shape from King/Contra Costa. South Charlotte is not a municipality in the
source data; it is a wealth-pocket / sub-neighborhood inside the City of
Charlotte. This script therefore treats South Charlotte as its own product
jurisdiction, while preserving the real zoning authority and matrix join key:

  - jurisdiction.name       = "South Charlotte, NC"
  - parcels.city            = "Charlotte"
  - zoning raw authority    = "City of Charlotte"
  - raw muni/subarea stamp  = "South Charlotte"

Sources from docs/MECKLENBURG_NC_ACQUISITION_SPEC.md:

  NC OneMap parcels:
    https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/1
    Mecklenburg county filter: stcntyfips = '37119'
    Charlotte city limiter   : scity = 'CHARLOTTE'

  City of Charlotte zoning:
    https://gis.charlottenc.gov/arcgis/rest/services/PLN/Zoning/MapServer/0
    Code field: ZoneDes (5,664/5,664 nonblank in diagnostic probe)

AOI discipline:
  The diagnostic spec's rough South Charlotte envelope is included only for
  dry-run rehearsal. Real fire refuses unless an approved AOI GeoJSON is
  supplied via --aoi-geojson, or the operator explicitly passes
  --use-rough-preview-aoi. That prevents a whole-Charlotte or rough-envelope
  accidental production claim.

Idempotency:
  A fire/dry-run wraps jurisdiction registration, existing South Charlotte
  parcel/zoning cleanup, parcel COPY-upsert, zoning INSERT, spatial backfill,
  and bbox update in one transaction. Re-running is safe for this dedicated
  South Charlotte jurisdiction and --dry-run rolls the entire rehearsal back.

Coordination with Wake:
  Every NC OneMap parcel query includes stcntyfips = '37119'. Wake should use
  its own county FIPS filter, so the shared statewide source is read-only and
  parallel-safe.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely import make_valid
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union
from shapely.wkb import dumps as wkb_dumps

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("mecklenburg_nc_south_charlotte")

PARCEL_LAYER_URL = (
    "https://services.nconemap.gov/secure/rest/services/"
    "NC1Map_Parcels/FeatureServer/1"
)
ZONING_LAYER_URL = (
    "https://gis.charlottenc.gov/arcgis/rest/services/"
    "PLN/Zoning/MapServer/0"
)

JURISDICTION_NAME = "South Charlotte, NC"
JURISDICTION_STATE = "NC"
JURISDICTION_COUNTY = "Mecklenburg"
MUNI_NAME = "South Charlotte"
PROD_CITY_VALUE = "Charlotte"
ZONING_AUTHORITY = "City of Charlotte"

COUNTY_FILTER = "stcntyfips = '37119'"
CITY_FILTER = "scity = 'CHARLOTTE'"
PARCEL_WHERE = f"{COUNTY_FILTER} AND {CITY_FILTER}"
ZONING_WHERE = "ZoneDes IS NOT NULL"

# Diagnostic rough AOI from docs/MECKLENBURG_NC_ACQUISITION_SPEC.md.
# WGS84 envelope: [-80.93, 35.02, -80.74, 35.20].
ROUGH_AOI_POLYGON = Polygon(
    [
        (-80.93, 35.02),
        (-80.74, 35.02),
        (-80.74, 35.20),
        (-80.93, 35.20),
        (-80.93, 35.02),
    ]
)

# Broad Mecklenburg sanity envelope. This intentionally allows any approved
# South Charlotte AOI inside the county/city, but catches wrong-state mistakes.
BBOX_LON_RANGE = (-81.10, -80.50)
BBOX_LAT_RANGE = (34.95, 35.55)

PARCEL_PAGE_SIZE = 5000
ZONING_PAGE_SIZE = 2000
COPY_CHUNK = 25_000

_STAGE_COLUMNS = [
    "jurisdiction_id", "apn", "address", "city", "owner_name",
    "zoning_code", "zone_class", "land_use_code", "acres",
    "county_link", "in_flood_zone", "in_wetland", "avg_slope_pct",
    "has_structure", "improvement_value",
    "assessed_value", "is_residential",
    "geom_wkb", "centroid_wkb", "raw_json",
]

_CREATE_STAGE_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _stage_parcels (
    jurisdiction_id uuid, apn text, address text, city text,
    owner_name text, zoning_code text, zone_class text,
    land_use_code text, acres double precision, county_link text,
    in_flood_zone boolean, in_wetland boolean, avg_slope_pct double precision,
    has_structure boolean, improvement_value double precision,
    assessed_value double precision, is_residential boolean,
    geom_wkb bytea, centroid_wkb bytea, raw_json text
)
"""

_TRUNCATE_STAGE_SQL = "TRUNCATE _stage_parcels"

_MERGE_SQL = """
INSERT INTO parcels (
    jurisdiction_id, apn, address, city, owner_name, zoning_code, zone_class,
    land_use_code, acres, county_link, in_flood_zone, in_wetland,
    avg_slope_pct, has_structure, improvement_value,
    assessed_value, is_residential,
    geom, centroid, raw
)
SELECT
    s.jurisdiction_id, s.apn, s.address, s.city, s.owner_name,
    s.zoning_code, s.zone_class::zone_class_enum,
    s.land_use_code, s.acres, s.county_link,
    s.in_flood_zone, s.in_wetland, s.avg_slope_pct,
    s.has_structure, s.improvement_value,
    s.assessed_value, s.is_residential,
    ST_GeomFromEWKB(s.geom_wkb),
    ST_GeomFromEWKB(s.centroid_wkb),
    s.raw_json::jsonb
FROM _stage_parcels s
ON CONFLICT ON CONSTRAINT uq_parcels_jurisdiction_apn DO UPDATE SET
    address = EXCLUDED.address,
    city = EXCLUDED.city,
    owner_name = EXCLUDED.owner_name,
    land_use_code = EXCLUDED.land_use_code,
    acres = EXCLUDED.acres,
    county_link = EXCLUDED.county_link,
    has_structure = EXCLUDED.has_structure,
    improvement_value = EXCLUDED.improvement_value,
    assessed_value = COALESCE(EXCLUDED.assessed_value, parcels.assessed_value),
    is_residential = COALESCE(EXCLUDED.is_residential, parcels.is_residential),
    geom = EXCLUDED.geom,
    centroid = EXCLUDED.centroid,
    raw = EXCLUDED.raw,
    updated_at = NOW()
"""

RAW_PARCEL_META = {
    "source_url": PARCEL_LAYER_URL,
    "source_kind": "arcgis_feature_server",
    "source_filter": PARCEL_WHERE,
    "county_filter": COUNTY_FILTER,
    "city_filter": CITY_FILTER,
    "muni_name": MUNI_NAME,
    "muni_type": "sub_neighborhood",
    "prod_city_value": PROD_CITY_VALUE,
    "zoning_authority": ZONING_AUTHORITY,
    "ingested_at": "2026-06-23",
}

RAW_ZONING_KEYS = (
    "OBJECTID", "ZonePetition", "ZoneDes", "SPA", "Overlay", "RezoneDate",
    "ZoneClass", "Hyperlink", "SHAPE.STArea()", "SHAPE.STLength()",
)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _clean_text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_geom(geom_json: dict | None) -> Any:
    if not geom_json:
        return None
    try:
        geom = shape(geom_json)
        if geom.is_empty:
            return None
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.is_empty:
            return None
        return geom
    except Exception:
        return None


def _ensure_valid_geom(geom: Any) -> Any:
    if geom is None or geom.is_empty:
        raise ValueError("empty geometry")
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.is_empty:
        raise ValueError("empty geometry after make_valid")
    return geom


def _load_aoi(path: str | None, use_rough_preview_aoi: bool) -> tuple[Any, str]:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("type") == "FeatureCollection":
            geoms = [shape(feat["geometry"]) for feat in data.get("features", [])
                     if feat.get("geometry")]
            if not geoms:
                raise SystemExit(f"AOI GeoJSON has no feature geometries: {path}")
            return _ensure_valid_geom(unary_union(geoms)), f"geojson:{path}"
        if data.get("type") == "Feature":
            return _ensure_valid_geom(shape(data["geometry"])), f"geojson:{path}"
        return _ensure_valid_geom(shape(data)), f"geojson:{path}"
    if use_rough_preview_aoi:
        return ROUGH_AOI_POLYGON, "rough-preview-envelope"
    raise SystemExit(
        "Approved South Charlotte AOI required. Pass --aoi-geojson, or pass "
        "--use-rough-preview-aoi for diagnostic rehearsal only."
    )


def _aoi_envelope_param(aoi: Any) -> str:
    minx, miny, maxx, maxy = aoi.bounds
    return json.dumps({
        "xmin": minx,
        "ymin": miny,
        "xmax": maxx,
        "ymax": maxy,
        "spatialReference": {"wkid": 4326},
    })


def _classify_residential(use_code: str | None, use_desc: str | None) -> bool | None:
    if not use_code and not use_desc:
        return None
    code = (use_code or "").upper()
    desc = (use_desc or "").upper()
    if code.startswith("R"):
        return True
    if code in {"A500"} or "MULTI FAMILY" in desc or "CONDOMINIUM" in desc:
        return True
    if code.startswith(("C", "O", "I", "W")):
        return False
    return None


def _map_parcel_row(
    props: dict[str, Any],
    geom: Any,
    jid: uuid.UUID,
    aoi_source: str,
) -> dict[str, Any] | None:
    apn = _clean_text(props.get("parno"))
    if not apn:
        return None

    address = _clean_text(props.get("siteadd"))
    owner_name = _clean_text(props.get("ownname"))
    use_code = _clean_text(props.get("parusecode"))
    use_desc = _clean_text(props.get("parusedesc"))
    acres = _safe_float(props.get("gisacres"))
    if acres is not None and acres <= 0:
        acres = None

    land_value = _safe_float(props.get("landval"))
    improvement_value = _safe_float(props.get("improvval"))
    parcel_value = _safe_float(props.get("parval"))
    assessed_value = parcel_value
    if assessed_value is None and (land_value is not None or improvement_value is not None):
        assessed_value = (land_value or 0) + (improvement_value or 0)
    if assessed_value is not None and assessed_value <= 0:
        assessed_value = None

    has_structure = None
    if improvement_value is not None:
        has_structure = improvement_value > 0

    raw = dict(RAW_PARCEL_META)
    raw["aoi_source"] = aoi_source
    for k, v in props.items():
        raw[k] = str(v) if v is not None else None

    return {
        "jurisdiction_id": str(jid),
        "apn": apn,
        "address": address,
        "city": PROD_CITY_VALUE,
        "owner_name": owner_name,
        "zoning_code": None,
        "zone_class": None,
        "land_use_code": use_code,
        "acres": acres,
        "county_link": None,
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": improvement_value,
        "assessed_value": assessed_value,
        "is_residential": _classify_residential(use_code, use_desc),
        "geom": geom,
        "centroid": geom.centroid,
        "raw": raw,
    }


def _row_to_record(r: dict[str, Any]) -> tuple:
    return (
        r["jurisdiction_id"], r["apn"], r.get("address"), r.get("city"),
        r.get("owner_name"), r.get("zoning_code"), r.get("zone_class"),
        r.get("land_use_code"), r.get("acres"), r.get("county_link"),
        r.get("in_flood_zone"), bool(r.get("in_wetland")),
        r.get("avg_slope_pct"), r.get("has_structure"),
        r.get("improvement_value"), r.get("assessed_value"),
        r.get("is_residential"),
        wkb_dumps(r["geom"], hex=False, srid=4326),
        wkb_dumps(r["centroid"], hex=False, srid=4326),
        json.dumps(r.get("raw")) if r.get("raw") is not None else None,
    )


async def _fetch_arcgis_page(
    client: httpx.AsyncClient,
    layer_url: str,
    where: str,
    envelope: str,
    page_size: int,
    offset: int,
    order_by: str,
) -> list[dict[str, Any]]:
    response = await client.get(
        f"{layer_url}/query",
        params={
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "orderByFields": order_by,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload.get("features", [])


async def _fetch_arcgis_features(
    client: httpx.AsyncClient,
    layer_url: str,
    where: str,
    envelope: str,
    page_size: int,
    order_by: str,
    max_features: int | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        requested = page_size
        if max_features is not None:
            remaining = max_features - len(out)
            if remaining <= 0:
                return out[:max_features]
            requested = min(page_size, remaining)
        batch = await _fetch_arcgis_page(
            client, layer_url, where, envelope, requested, offset, order_by,
        )
        out.extend(batch)
        logger.info("fetched %d from %s (cum %d)", len(batch), layer_url, len(out))
        if max_features is not None and len(out) >= max_features:
            return out[:max_features]
        if len(batch) < page_size:
            return out
        offset += page_size


async def _fetch_parcel_source_count(client: httpx.AsyncClient, envelope: str) -> int:
    response = await client.get(
        f"{PARCEL_LAYER_URL}/query",
        params={
            "where": PARCEL_WHERE,
            "returnCountOnly": "true",
            "f": "json",
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        },
    )
    response.raise_for_status()
    return int(response.json().get("count") or 0)


def _build_parcel_rows(
    features: list[dict[str, Any]],
    jid: uuid.UUID,
    aoi: Any,
    aoi_source: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {"geom_skipped": 0, "outside_aoi": 0, "apn_skipped": 0}
    rows_by_apn: dict[str, dict[str, Any]] = {}
    prepared_aoi = aoi
    for feat in features:
        props = feat.get("properties") or {}
        geom = _parse_geom(feat.get("geometry"))
        if geom is None:
            stats["geom_skipped"] += 1
            continue
        if not prepared_aoi.covers(geom.centroid):
            stats["outside_aoi"] += 1
            continue
        mapped = _map_parcel_row(props, geom, jid, aoi_source)
        if mapped is None:
            stats["apn_skipped"] += 1
            continue
        rows_by_apn[mapped["apn"]] = mapped
    return list(rows_by_apn.values()), stats


def _build_zoning_rows(
    features: list[dict[str, Any]],
    jid: uuid.UUID,
    aoi: Any,
    aoi_source: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {"geom_skipped": 0, "outside_aoi": 0, "blank_zone": 0}
    rows = []
    zoning_aoi = aoi.buffer(0.002)  # ~200m guard for boundary-crossing districts.
    for feat in features:
        attrs = feat.get("properties") or {}
        geom_json = feat.get("geometry")
        geom = _parse_geom(geom_json)
        if geom is None:
            stats["geom_skipped"] += 1
            continue
        if not geom.intersects(zoning_aoi):
            stats["outside_aoi"] += 1
            continue
        zone_code = _clean_text(attrs.get("ZoneDes"))
        if not zone_code:
            stats["blank_zone"] += 1
            continue
        raw = {
            "source_url": ZONING_LAYER_URL,
            "source_kind": "arcgis_map_server",
            "source_filter": ZONING_WHERE,
            "aoi_source": aoi_source,
            "muni_name": MUNI_NAME,
            "muni_type": "sub_neighborhood",
            "prod_city_value": PROD_CITY_VALUE,
            "zoning_authority": ZONING_AUTHORITY,
            "ingested_at": "2026-06-23",
        }
        for k in RAW_ZONING_KEYS:
            if k in attrs and attrs[k] is not None:
                raw[k] = attrs[k]
        if geom.geom_type not in {"Polygon", "MultiPolygon"}:
            logger.warning(
                "skip zoning OBJECTID=%s: non-polygon geometry %s",
                attrs.get("OBJECTID"), geom.geom_type,
            )
            stats["geom_skipped"] += 1
            continue
        rows.append({
            "zone_code": zone_code,
            "zone_name": _clean_text(attrs.get("ZoneClass")) or zone_code,
            "geom_wkt": geom.wkt,
            "raw_attributes": json.dumps(raw),
            "jurisdiction_id": str(jid),
        })
    return rows, stats


async def _copy_upsert_parcels(conn: asyncpg.Connection, rows: list[dict[str, Any]]) -> int:
    await conn.execute(_CREATE_STAGE_SQL)
    await conn.execute(_TRUNCATE_STAGE_SQL)
    for i in range(0, len(rows), COPY_CHUNK):
        chunk = rows[i:i + COPY_CHUNK]
        records = [_row_to_record(row) for row in chunk]
        await conn.copy_records_to_table(
            "_stage_parcels", records=records, columns=_STAGE_COLUMNS,
        )
        logger.info("COPY staged %d/%d parcels", min(i + COPY_CHUNK, len(rows)), len(rows))
    inserted = await conn.fetchval(
        "WITH ins AS (" + _MERGE_SQL + " RETURNING 1) SELECT COUNT(*) FROM ins"
    )
    return int(inserted or 0)


async def _resolve_or_register_jurisdiction(conn: asyncpg.Connection) -> uuid.UUID:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        JURISDICTION_NAME, JURISDICTION_STATE,
    )
    if existing:
        return existing["id"]
    new_jid = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO jurisdictions (
            id, name, state, county, parcel_endpoint, zoning_endpoint,
            coverage_level
        ) VALUES (
            $1::uuid, $2, $3, $4, $5, $6, 'partial'::coverage_level_enum
        )
        """,
        str(new_jid), JURISDICTION_NAME, JURISDICTION_STATE,
        JURISDICTION_COUNTY, PARCEL_LAYER_URL, ZONING_LAYER_URL,
    )
    return new_jid


async def _insert_zoning_rows(conn: asyncpg.Connection, jid: uuid.UUID, rows: list[dict[str, Any]]) -> int:
    records = [
        (
            str(jid),
            row["zone_code"],
            row["zone_name"],
            row["geom_wkt"],
            row["raw_attributes"],
        )
        for row in rows
    ]
    await conn.executemany(
        """
        INSERT INTO zoning_districts (
            jurisdiction_id, zone_code, zone_name, zone_class,
            geom, raw_attributes, source
        ) VALUES (
            $1::uuid, $2, $3, 'unknown'::zone_class_enum,
            ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
            $5::jsonb, 'arcgis'::zone_source_enum
        )
        """,
        records,
    )
    return len(rows)


async def _spatial_backfill(conn: asyncpg.Connection, jid: uuid.UUID, nearest_meters: float) -> tuple[int, int]:
    contained_status = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class = sub.zone_class,
               zone_binding_method = 'contained',
               zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
          FROM (
              SELECT p.id AS parcel_id, z.zone_class, z.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                      FROM zoning_districts zd
                     WHERE zd.jurisdiction_id = $1::uuid
                       AND zd.geom IS NOT NULL
                       AND ST_Within(ST_Centroid(p.geom), zd.geom)
                     ORDER BY zd.id
                     LIMIT 1
                ) z
               WHERE p.jurisdiction_id = $1::uuid
                 AND p.geom IS NOT NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        str(jid),
    )
    binding_label = f"nearest_{int(round(nearest_meters))}m"
    nearest_status = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class = sub.zone_class,
               zone_binding_method = $2,
               zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
          FROM (
              SELECT p.id AS parcel_id, z.zone_class, z.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT zd.zone_class, zd.zone_code
                      FROM zoning_districts zd
                     WHERE zd.jurisdiction_id = $1::uuid
                       AND zd.geom IS NOT NULL
                       AND ST_DWithin(
                           zd.geom::geography,
                           ST_Centroid(p.geom)::geography,
                           $3
                       )
                     ORDER BY ST_Distance(
                         zd.geom::geography,
                         ST_Centroid(p.geom)::geography
                     )
                     LIMIT 1
                ) z
               WHERE p.jurisdiction_id = $1::uuid
                 AND p.geom IS NOT NULL
                 AND p.zone_binding_method IS NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        str(jid), binding_label, float(nearest_meters),
    )
    return int(contained_status.split()[-1]), int(nearest_status.split()[-1])


async def _update_bbox(conn: asyncpg.Connection, jid: uuid.UUID) -> list[float]:
    ext = await conn.fetchrow(
        """
        SELECT ST_XMin(ST_Extent(geom)) AS minx,
               ST_YMin(ST_Extent(geom)) AS miny,
               ST_XMax(ST_Extent(geom)) AS maxx,
               ST_YMax(ST_Extent(geom)) AS maxy
          FROM parcels
         WHERE jurisdiction_id = $1::uuid
           AND geom IS NOT NULL
        """,
        str(jid),
    )
    if ext is None or ext["minx"] is None:
        raise RuntimeError("No parcel geometry available for bbox update")
    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    lon_lo, lon_hi = BBOX_LON_RANGE
    lat_lo, lat_hi = BBOX_LAT_RANGE
    if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
        raise RuntimeError(
            f"South Charlotte bbox {bbox} outside Mecklenburg sanity envelope"
        )
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        str(jid), json.dumps(bbox),
    )
    return bbox


async def _summarize(conn: asyncpg.Connection, jid: uuid.UUID) -> None:
    parcel_stats = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> '') AS bound,
               COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
               COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest,
               COUNT(*) FILTER (WHERE raw IS NULL OR raw = '{}'::jsonb) AS empty_raw
          FROM parcels
         WHERE jurisdiction_id = $1::uuid
        """,
        str(jid),
    )
    district_stats = await conn.fetchrow(
        """
        SELECT COUNT(*) AS districts,
               COUNT(DISTINCT zone_code) AS distinct_codes,
               COUNT(*) FILTER (
                   WHERE raw_attributes IS NULL OR raw_attributes = '{}'::jsonb
               ) AS empty_raw
          FROM zoning_districts
         WHERE jurisdiction_id = $1::uuid
        """,
        str(jid),
    )
    total = parcel_stats["total"] or 0
    bound = parcel_stats["bound"] or 0
    nearest = parcel_stats["nearest"] or 0
    coverage = 100.0 * bound / total if total else 0.0
    nearest_pct = 100.0 * nearest / total if total else 0.0
    print("\n=== 5-GATE PREVIEW ===")
    print(f"GATE 1 cov {coverage:.1f}% (>=70%) — {'PASS' if coverage >= 70 else 'SUB'}")
    print(f"GATE 2 near {nearest_pct:.1f}% (<30%) — {'PASS' if nearest_pct < 30 else 'OVER'}")
    print(f"GATE 3 parcel raw empty {parcel_stats['empty_raw']} — {'PASS' if parcel_stats['empty_raw'] == 0 else 'FAIL'}")
    print(f"GATE 4 zoning raw empty {district_stats['empty_raw']} — {'PASS' if district_stats['empty_raw'] == 0 else 'FAIL'}")
    print(f"GATE 5 districts {district_stats['districts']} / codes {district_stats['distinct_codes']} — {'PASS' if district_stats['districts'] else 'FAIL'}")
    print(
        f"  parcels {total:,} bound {bound:,} "
        f"contained {parcel_stats['contained']:,} nearest {nearest:,}"
    )
    codes = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*) AS n
          FROM parcels
         WHERE jurisdiction_id = $1::uuid
           AND zoning_code IS NOT NULL
         GROUP BY 1
         ORDER BY 2 DESC
         LIMIT 30
        """,
        str(jid),
    )
    if codes:
        print("\nTop zoning-code distribution:")
        for row in codes:
            print(f"  {row['zoning_code']:18s} {row['n']:>6,}")


async def _run(
    *,
    dry_run: bool,
    aoi_geojson: str | None,
    use_rough_preview_aoi: bool,
    nearest_meters: float,
    max_parcels: int | None,
) -> int:
    if max_parcels is not None and not dry_run:
        raise SystemExit("--max-parcels is allowed only with --dry-run")

    # Dry-run defaults to the diagnostic rough AOI for easy rehearsal. Fire
    # requires explicit AOI intent via CLI validation in main().
    if dry_run and not aoi_geojson:
        use_rough_preview_aoi = True

    aoi, aoi_source = _load_aoi(aoi_geojson, use_rough_preview_aoi)
    envelope = _aoi_envelope_param(aoi)
    print(f"\n=== {'DRY-RUN (ROLLBACK)' if dry_run else 'FIRE'}: Mecklenburg NC / South Charlotte ===")
    print(f"parcel where : {PARCEL_WHERE}")
    print(f"zoning where : {ZONING_WHERE}")
    print(f"aoi source   : {aoi_source}")
    print(f"aoi bounds   : {[round(v, 6) for v in aoi.bounds]}")

    started = time.time()
    fake_jid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    async with httpx.AsyncClient(timeout=180.0) as client:
        source_count = await _fetch_parcel_source_count(client, envelope)
        print(f"\n[source] NC OneMap envelope+county+Charlotte count: {source_count:,}")
        parcel_features = await _fetch_arcgis_features(
            client,
            PARCEL_LAYER_URL,
            PARCEL_WHERE,
            envelope,
            PARCEL_PAGE_SIZE,
            "objectid",
            max_features=max_parcels,
        )
        zoning_features = await _fetch_arcgis_features(
            client,
            ZONING_LAYER_URL,
            ZONING_WHERE,
            envelope,
            ZONING_PAGE_SIZE,
            "OBJECTID",
        )

    parcel_rows, parcel_build_stats = _build_parcel_rows(
        parcel_features, fake_jid, aoi, aoi_source,
    )
    zoning_rows, zoning_build_stats = _build_zoning_rows(
        zoning_features, fake_jid, aoi, aoi_source,
    )
    print("\n[build]")
    print(f"  parcel features fetched : {len(parcel_features):,}")
    print(f"  parcel rows built       : {len(parcel_rows):,}")
    print(f"  parcel build stats      : {parcel_build_stats}")
    print(f"  zoning features fetched : {len(zoning_features):,}")
    print(f"  zoning rows built       : {len(zoning_rows):,}")
    print(f"  zoning build stats      : {zoning_build_stats}")
    print(f"  zoning distinct codes   : {len({r['zone_code'] for r in zoning_rows})}")
    if parcel_rows:
        raw_keys = sorted(parcel_rows[0]["raw"].keys())
        print(f"  sample parcel raw keys  : {len(raw_keys)} ({raw_keys[:10]}...)")
    if zoning_rows:
        raw = json.loads(zoning_rows[0]["raw_attributes"])
        print(f"  sample zoning raw keys  : {len(raw)} ({sorted(raw.keys())[:10]}...)")

    if not parcel_rows:
        raise SystemExit("No parcel rows built; refusing to continue")
    if not zoning_rows:
        raise SystemExit("No zoning rows built; refusing to continue")

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=7200,
    )
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            jid = await _resolve_or_register_jurisdiction(conn)
            print(f"\n[jurisdiction] {JURISDICTION_NAME} -> {jid}")

            # Rebuild fake JID rows with the real JID after registration.
            for row in parcel_rows:
                row["jurisdiction_id"] = str(jid)
            for row in zoning_rows:
                row["jurisdiction_id"] = str(jid)

            district_clear = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                str(jid),
            )
            parcel_clear = await conn.execute(
                "DELETE FROM parcels WHERE jurisdiction_id=$1::uuid",
                str(jid),
            )
            print(f"[idempotency] cleared {district_clear.split()[-1]} zoning rows")
            print(f"[idempotency] cleared {parcel_clear.split()[-1]} parcel rows")

            inserted_parcels = await _copy_upsert_parcels(conn, parcel_rows)
            print(f"[parcels] COPY/upsert rows: {inserted_parcels:,}")

            inserted_zoning = await _insert_zoning_rows(conn, jid, zoning_rows)
            print(f"[zoning] inserted rows: {inserted_zoning:,}")

            contained, nearest = await _spatial_backfill(conn, jid, nearest_meters)
            print(f"[spatial] contained UPDATEd {contained:,}")
            print(f"[spatial] nearest_{int(round(nearest_meters))}m UPDATEd {nearest:,}")

            bbox = await _update_bbox(conn, jid)
            print(f"[bbox] {bbox}")

            await _summarize(conn, jid)

            if dry_run:
                raise _RollbackForDryRun()

    except _RollbackForDryRun:
        print("\n(DRY-RUN — transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    elapsed = time.time() - started
    print(f"\ncompleted in {elapsed / 60:.1f} min")
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside transaction context to force rollback."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument(
        "--aoi-geojson",
        help="Approved South Charlotte AOI GeoJSON. Required for fire unless "
             "--use-rough-preview-aoi is explicitly passed.",
    )
    parser.add_argument(
        "--use-rough-preview-aoi",
        action="store_true",
        help="Use the diagnostic rough envelope from the acquisition spec. "
             "Dry-run defaults to this when --aoi-geojson is absent; fire "
             "requires this flag explicitly if no approved AOI is provided.",
    )
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    parser.add_argument(
        "--max-parcels",
        type=int,
        help="Dry-run-only cap for quick source-shape rehearsal.",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing — pass --dry-run for rollback rehearsal or "
            "--i-know-this-writes-to-prod to actually fire.",
            file=sys.stderr,
        )
        return 2
    if not args.dry_run and not args.aoi_geojson and not args.use_rough_preview_aoi:
        print(
            "Refusing fire without approved AOI. Pass --aoi-geojson, or "
            "explicitly pass --use-rough-preview-aoi if Master accepts the "
            "diagnostic envelope.",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return asyncio.run(
        _run(
            dry_run=args.dry_run,
            aoi_geojson=args.aoi_geojson,
            use_rough_preview_aoi=args.use_rough_preview_aoi,
            nearest_meters=args.nearest_within_meters,
            max_parcels=args.max_parcels,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
