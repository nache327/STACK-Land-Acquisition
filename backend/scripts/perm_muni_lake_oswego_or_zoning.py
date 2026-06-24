"""Lake Oswego OR Class B per-muni zoning adapter (PREP - DO NOT FIRE).

Pattern: PR #334 Winnetka Class B adapter, adapted for a not-yet-loaded
Phase 6 outlier where the parcel substrate must be staged by this script.

Sources, per Agent 11 / PR #344 diagnostic:
  - Parcels: Metro RLIS Taxlots (Public), FeatureServer layer 3.
    Filtered to Lake Oswego taxlots in Clackamas/Multnomah only with
    `JURIS_CITY = 'LAKE OSWEGO' AND (COUNTY = 'C' OR COUNTY = 'M')`.
    RLIS spans Clackamas, Multnomah, and Washington Counties; this adapter
    intentionally excludes small Washington-coded edge rows because the target
    dispatch is Multnomah/Clackamas.
  - Zoning: City of Lake Oswego `Zoning_cache`, MapServer layer 150.
    Local zone code field is `LAYER`; code-section link is `INFO`.

Operational shape:
  - Registers/updates one per-muni product jurisdiction: `Lake Oswego, OR`.
  - Preserves all RLIS source attributes in parcels.raw.source_attributes.
  - Preserves all City zoning attributes in zoning_districts.raw_attributes.
  - Backfills parcel zoning by spatial containment, then nearest fallback.
  - `--dry-run` runs the full transaction and rolls back.

PREP ONLY. Default invocation refuses. Do not pass
`--i-know-this-writes-to-prod` from this PR dispatch.
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
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.wkb import dumps as wkb_dumps

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("lake_oswego_or")

ADAPTER_NAME = "perm_muni_lake_oswego_or_zoning"
SOURCE_DATE = "2026-06-23"

JURISDICTION_NAME = "Lake Oswego, OR"
JURISDICTION_STATE = "OR"
JURISDICTION_COUNTY = "Clackamas/Multnomah"
MUNI_NAME = "Lake Oswego"
MUNI_TYPE = "city"
PROD_CITY_VALUE = "Lake Oswego"

RLIS_TAXLOTS_LAYER = (
    "https://services2.arcgis.com/McQ0OlIABe29rJJy/arcgis/rest/services/"
    "Taxlots_(Public)/FeatureServer/3"
)
LAKE_OSWEGO_ZONING_LAYER = (
    "https://maps.ci.oswego.or.us/server/rest/services/"
    "Zoning_cache/MapServer/150"
)
ORDINANCE_URL = "https://ecode360.com/45996060"
USE_TABLE_URL = "https://ecode360.com/43075916"

PARCEL_WHERE = "JURIS_CITY = 'LAKE OSWEGO' AND (COUNTY = 'C' OR COUNTY = 'M')"
ZONING_WHERE = "1=1"
PARCEL_PAGE_SIZE = 2000
ZONING_PAGE_SIZE = 1000
COPY_CHUNK = 25_000

# Broad Lake Oswego sanity envelope, intentionally allowing both the
# Clackamas-side core and the small Multnomah-side edge.
BBOX_LON = (-122.78, -122.62)
BBOX_LAT = (45.35, 45.47)

_STAGE_COLUMNS = [
    "jurisdiction_id", "apn", "address", "city", "owner_name",
    "zoning_code", "zone_class", "land_use_code", "acres",
    "county_link", "in_flood_zone", "in_wetland", "avg_slope_pct",
    "has_structure", "improvement_value", "assessed_value",
    "is_residential", "geom_wkb", "centroid_wkb", "raw_json",
]

_CREATE_STAGE_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _stage_lake_oswego_parcels (
    jurisdiction_id uuid, apn text, address text, city text,
    owner_name text, zoning_code text, zone_class text,
    land_use_code text, acres double precision, county_link text,
    in_flood_zone boolean, in_wetland boolean, avg_slope_pct double precision,
    has_structure boolean, improvement_value double precision,
    assessed_value double precision, is_residential boolean,
    geom_wkb bytea, centroid_wkb bytea, raw_json text
)
"""

_MERGE_SQL = """
INSERT INTO parcels (
    jurisdiction_id, apn, address, city, owner_name, zoning_code, zone_class,
    land_use_code, acres, county_link, in_flood_zone, in_wetland,
    avg_slope_pct, has_structure, improvement_value, assessed_value,
    is_residential, geom, centroid, raw
)
SELECT
    s.jurisdiction_id, s.apn, s.address, s.city, s.owner_name,
    s.zoning_code, s.zone_class::zone_class_enum, s.land_use_code,
    s.acres, s.county_link, s.in_flood_zone, s.in_wetland,
    s.avg_slope_pct, s.has_structure, s.improvement_value,
    s.assessed_value, s.is_residential, ST_GeomFromEWKB(s.geom_wkb),
    ST_GeomFromEWKB(s.centroid_wkb), s.raw_json::jsonb
FROM _stage_lake_oswego_parcels s
ON CONFLICT ON CONSTRAINT uq_parcels_jurisdiction_apn DO UPDATE SET
    address = EXCLUDED.address,
    city = EXCLUDED.city,
    state = 'OR',
    owner_name = EXCLUDED.owner_name,
    land_use_code = EXCLUDED.land_use_code,
    acres = EXCLUDED.acres,
    county_link = EXCLUDED.county_link,
    has_structure = EXCLUDED.has_structure,
    improvement_value = EXCLUDED.improvement_value,
    assessed_value = EXCLUDED.assessed_value,
    is_residential = EXCLUDED.is_residential,
    geom = EXCLUDED.geom,
    centroid = EXCLUDED.centroid,
    raw = EXCLUDED.raw,
    updated_at = NOW()
"""


def _session_db_url() -> str:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL or SUPABASE_DB_URL not set in environment")
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _polygonal(geom_json: dict[str, Any] | None) -> Polygon | MultiPolygon | None:
    if not geom_json:
        return None
    try:
        geom = make_valid(shape(geom_json))
        if isinstance(geom, (Polygon, MultiPolygon)) and not geom.is_empty:
            return geom
        if isinstance(geom, GeometryCollection):
            polys: list[Polygon] = []
            for part in geom.geoms:
                if isinstance(part, Polygon):
                    polys.append(part)
                elif isinstance(part, MultiPolygon):
                    polys.extend(list(part.geoms))
            if polys:
                return MultiPolygon(polys)
    except Exception:
        return None
    return None


def _county_name(code: Any) -> str | None:
    value = _text(code)
    if value == "C":
        return "Clackamas"
    if value == "M":
        return "Multnomah"
    if value == "W":
        return "Washington"
    return value


def _is_residential(landuse: str | None, prop_code: str | None) -> bool | None:
    use = (landuse or "").upper()
    code = (prop_code or "").strip()
    if use in {"SFR", "MFR", "CONDO", "RES"}:
        return True
    if code.startswith(("1", "2")):
        return True
    if use in {"COM", "IND", "MIX", "PARK", "EXEMPT"}:
        return False
    if code.startswith(("3", "4", "5", "6", "7", "8", "9")):
        return False
    return None


def _zone_class(zone: str) -> str:
    z = zone.upper().strip()
    if z.startswith(("R-", "R/", "R0", "R1", "R2", "R3", "R5", "R7", "R10", "R15")):
        return "residential"
    if z.startswith(("WR", "WLG", "FMU")):
        return "mixed_use"
    if z in {"EC", "EC/R-0", "EC/HC", "MC", "NC", "OC", "CR&D"}:
        return "commercial"
    if z.startswith("I"):
        return "industrial"
    if z in {"PNA", "PF", "PARK", "OS"}:
        return "open_space"
    return "unknown"


async def _fetch_count(client: httpx.AsyncClient, layer: str, where: str) -> int:
    response = await client.get(
        f"{layer}/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return int(payload.get("count") or 0)


async def _fetch_geojson_features(
    client: httpx.AsyncClient,
    layer: str,
    where: str,
    *,
    page_size: int,
    order_by: str | None,
    max_features: int | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        limit = page_size
        if max_features is not None:
            remaining = max_features - len(features)
            if remaining <= 0:
                break
            limit = min(limit, remaining)
        params: dict[str, Any] = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": limit,
        }
        if order_by:
            params["orderByFields"] = order_by
        response = await client.get(f"{layer}/query", params=params, timeout=180.0)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info(
            "fetched %s offset=%d batch=%d total=%d",
            layer,
            offset,
            len(batch),
            len(features),
        )
        if len(batch) < limit:
            break
        offset += len(batch)
    return features


async def _fetch_sources(
    *,
    max_parcels: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with httpx.AsyncClient(timeout=180.0) as client:
        parcel_count = await _fetch_count(client, RLIS_TAXLOTS_LAYER, PARCEL_WHERE)
        zoning_count = await _fetch_count(client, LAKE_OSWEGO_ZONING_LAYER, ZONING_WHERE)
        print(f"[source] RLIS Lake Oswego taxlots: {parcel_count:,}")
        print(f"[source] Lake Oswego zoning polygons: {zoning_count:,}")
        parcels = await _fetch_geojson_features(
            client,
            RLIS_TAXLOTS_LAYER,
            PARCEL_WHERE,
            page_size=PARCEL_PAGE_SIZE,
            order_by="FID",
            max_features=max_parcels,
        )
        zoning = await _fetch_geojson_features(
            client,
            LAKE_OSWEGO_ZONING_LAYER,
            ZONING_WHERE,
            page_size=ZONING_PAGE_SIZE,
            order_by="OBJECTID",
        )
    return parcels, zoning


def _parcel_record(feature: dict[str, Any], jid: str) -> tuple[Any, ...] | None:
    attrs = feature.get("properties") or {}
    geom = _polygonal(feature.get("geometry"))
    apn = _text(attrs.get("TLID")) or _text(attrs.get("PRIMACCNUM"))
    if geom is None or not apn:
        return None

    landuse = _text(attrs.get("LANDUSE"))
    prop_code = _text(attrs.get("PROP_CODE"))
    assessed_value = _float(attrs.get("ASSESSVAL"))
    improvement_value = _float(attrs.get("BLDGVAL"))
    building_sqft = _float(attrs.get("BLDGSQFT"))
    has_structure = None
    if building_sqft is not None:
        has_structure = building_sqft > 0
    elif improvement_value is not None:
        has_structure = improvement_value > 0

    raw = {
        "adapter": ADAPTER_NAME,
        "source_url": RLIS_TAXLOTS_LAYER,
        "source_filter": PARCEL_WHERE,
        "source_kind": "arcgis_feature_server",
        "ingested_at": SOURCE_DATE,
        "muni_name": MUNI_NAME,
        "muni_type": MUNI_TYPE,
        "prod_city_value": PROD_CITY_VALUE,
        "county_code": _text(attrs.get("COUNTY")),
        "county_name": _county_name(attrs.get("COUNTY")),
        "source_attributes": attrs,
    }
    centroid = geom.centroid
    return (
        jid,
        apn,
        _text(attrs.get("SITEADDR")),
        PROD_CITY_VALUE,
        None,
        None,
        None,
        landuse or prop_code,
        _float(attrs.get("GIS_ACRES")) or _float(attrs.get("A_T_ACRES")),
        None,
        False,
        False,
        None,
        has_structure,
        improvement_value,
        assessed_value,
        _is_residential(landuse, prop_code),
        wkb_dumps(geom, hex=False, srid=4326),
        wkb_dumps(centroid, hex=False, srid=4326),
        json.dumps(raw),
    )


def _parcel_rows(
    features: list[dict[str, Any]],
    jid: str,
) -> tuple[list[tuple[Any, ...]], dict[str, int]]:
    rows: list[tuple[Any, ...]] = []
    seen: set[str] = set()
    stats = {"missing_key_or_geom": 0, "duplicate_apn": 0}
    for feature in features:
        row = _parcel_record(feature, jid)
        if row is None:
            stats["missing_key_or_geom"] += 1
            continue
        apn = str(row[1])
        if apn in seen:
            stats["duplicate_apn"] += 1
            continue
        seen.add(apn)
        rows.append(row)
    return rows, stats


def _zoning_rows(features: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    stats = {"missing_zone_or_geom": 0}
    for feature in features:
        attrs = feature.get("properties") or {}
        zone = _text(attrs.get("LAYER"))
        geom = _polygonal(feature.get("geometry"))
        if not zone or geom is None:
            stats["missing_zone_or_geom"] += 1
            continue
        raw = {
            "adapter": ADAPTER_NAME,
            "source_url": LAKE_OSWEGO_ZONING_LAYER,
            "source_filter": ZONING_WHERE,
            "source_kind": "arcgis_map_server",
            "ingested_at": SOURCE_DATE,
            "muni_name": MUNI_NAME,
            "muni_type": MUNI_TYPE,
            "prod_city_value": PROD_CITY_VALUE,
            "ordinance_url": ORDINANCE_URL,
            "use_table_url": USE_TABLE_URL,
            "source_attributes": attrs,
        }
        rows.append({
            "zone_code": zone,
            "zone_name": zone,
            "zone_class": _zone_class(zone),
            "geom_wkb": wkb_dumps(geom, hex=False, srid=4326),
            "raw": json.dumps(raw),
        })
    return rows, stats


async def _register_jurisdiction(conn: asyncpg.Connection) -> str:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        JURISDICTION_NAME,
        JURISDICTION_STATE,
    )
    if existing:
        jid = str(existing["id"])
        await conn.execute(
            """
            UPDATE jurisdictions
               SET county=$2,
                   parcel_source='city_gis'::parcel_source_enum,
                   parcel_endpoint=$3,
                   zoning_endpoint=$4,
                   ordinance_url=$5,
                   coverage_level='partial'::coverage_level_enum
             WHERE id=$1::uuid
            """,
            jid,
            JURISDICTION_COUNTY,
            RLIS_TAXLOTS_LAYER,
            LAKE_OSWEGO_ZONING_LAYER,
            ORDINANCE_URL,
        )
        print(f"[jurisdiction] found existing {JURISDICTION_NAME}: {jid}")
        return jid

    jid = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO jurisdictions (
            id, name, state, county, parcel_source, parcel_endpoint,
            zoning_endpoint, ordinance_url, coverage_level
        )
        VALUES (
            $1::uuid, $2, $3, $4, 'city_gis'::parcel_source_enum, $5,
            $6, $7, 'partial'::coverage_level_enum
        )
        """,
        jid,
        JURISDICTION_NAME,
        JURISDICTION_STATE,
        JURISDICTION_COUNTY,
        RLIS_TAXLOTS_LAYER,
        LAKE_OSWEGO_ZONING_LAYER,
        ORDINANCE_URL,
    )
    print(f"[jurisdiction] registered {JURISDICTION_NAME}: {jid}")
    return jid


async def _stage_and_merge_parcels(
    conn: asyncpg.Connection,
    parcel_features: list[dict[str, Any]],
    jid: str,
) -> int:
    rows, stats = _parcel_rows(parcel_features, jid)
    print(f"[parcels] build stats: {stats}")
    await conn.execute(_CREATE_STAGE_SQL)
    await conn.execute("TRUNCATE _stage_lake_oswego_parcels")
    for i in range(0, len(rows), COPY_CHUNK):
        await conn.copy_records_to_table(
            "_stage_lake_oswego_parcels",
            records=rows[i : i + COPY_CHUNK],
            columns=_STAGE_COLUMNS,
        )
    if rows:
        await conn.execute(_MERGE_SQL)
        await conn.execute(
            """
            UPDATE parcels
               SET city=$2,
                   state='OR',
                   updated_at=NOW()
             WHERE jurisdiction_id=$1::uuid
            """,
            jid,
            PROD_CITY_VALUE,
        )
    return len(rows)


async def _insert_zoning_districts(
    conn: asyncpg.Connection,
    zoning_features: list[dict[str, Any]],
    jid: str,
) -> int:
    rows, stats = _zoning_rows(zoning_features)
    print(f"[zoning] build stats: {stats}")
    for row in rows:
        await conn.execute(
            """
            INSERT INTO zoning_districts (
                jurisdiction_id, zone_code, zone_name, zone_class,
                geom, raw_attributes, source
            )
            VALUES (
                $1::uuid, $2, $3, $4::zone_class_enum,
                ST_Multi(ST_MakeValid(ST_GeomFromEWKB($5))),
                $6::jsonb, 'arcgis'::zone_source_enum
            )
            """,
            jid,
            row["zone_code"],
            row["zone_name"],
            row["zone_class"],
            row["geom_wkb"],
            row["raw"],
        )
    return len(rows)


async def _reset_bindings(conn: asyncpg.Connection, jid: str) -> int:
    status = await conn.execute(
        """
        UPDATE parcels
           SET zoning_code = NULL,
               zone_class = NULL,
               zone_binding_method = NULL,
               updated_at = NOW()
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    return int(status.split()[-1])


async def _spatial_backfill(
    conn: asyncpg.Connection,
    jid: str,
    nearest_meters: float,
) -> tuple[int, int]:
    contained_status = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class = sub.zone_class,
               zone_binding_method = 'contained',
               zoning_code = sub.zone_code,
               updated_at = NOW()
          FROM (
              SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT z.zone_class, z.zone_code
                      FROM zoning_districts z
                     WHERE z.jurisdiction_id=$1::uuid
                       AND z.geom IS NOT NULL
                       AND ST_Within(ST_Centroid(p.geom), z.geom)
                     ORDER BY z.id
                     LIMIT 1
                ) zd
               WHERE p.jurisdiction_id=$1::uuid
                 AND p.geom IS NOT NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        jid,
    )
    binding_label = f"nearest_{int(round(nearest_meters))}m"
    nearest_status = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class = sub.zone_class,
               zone_binding_method = $2,
               zoning_code = sub.zone_code,
               updated_at = NOW()
          FROM (
              SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                FROM parcels p,
                LATERAL (
                    SELECT z.zone_class, z.zone_code
                      FROM zoning_districts z
                     WHERE z.jurisdiction_id=$1::uuid
                       AND z.geom IS NOT NULL
                       AND ST_DWithin(
                           z.geom::geography,
                           ST_Centroid(p.geom)::geography,
                           $3
                       )
                     ORDER BY ST_Distance(
                         z.geom::geography,
                         ST_Centroid(p.geom)::geography
                     )
                     LIMIT 1
                ) zd
               WHERE p.jurisdiction_id=$1::uuid
                 AND p.geom IS NOT NULL
                 AND p.zone_binding_method IS NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        jid,
        binding_label,
        float(nearest_meters),
    )
    return int(contained_status.split()[-1]), int(nearest_status.split()[-1])


async def _update_bbox(conn: asyncpg.Connection, jid: str) -> list[float]:
    ext = await conn.fetchrow(
        """
        SELECT ST_XMin(ST_Extent(geom)) AS minx,
               ST_YMin(ST_Extent(geom)) AS miny,
               ST_XMax(ST_Extent(geom)) AS maxx,
               ST_YMax(ST_Extent(geom)) AS maxy
          FROM parcels
         WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL
        """,
        jid,
    )
    if not ext or ext["minx"] is None:
        raise RuntimeError("no Lake Oswego parcel geometry after ingest")
    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    if not (
        BBOX_LON[0] <= bbox[0] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]
        and BBOX_LON[0] <= bbox[2] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[3] <= BBOX_LAT[1]
    ):
        raise RuntimeError(
            f"bbox {bbox} outside Lake Oswego envelope lon={BBOX_LON} lat={BBOX_LAT}"
        )
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid,
        json.dumps(bbox),
    )
    return bbox


async def _quality_report(conn: asyncpg.Connection, jid: str) -> None:
    parcels = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (
                   WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>''
               ) AS bound,
               COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
               COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest,
               COUNT(*) FILTER (WHERE raw IS NULL OR raw='{}'::jsonb) AS empty_raw
          FROM parcels
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    districts = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT zone_code) AS codes,
               COUNT(*) FILTER (
                   WHERE raw_attributes IS NULL OR raw_attributes='{}'::jsonb
               ) AS empty_raw
          FROM zoning_districts
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    total = int(parcels["total"] or 0)
    bound = int(parcels["bound"] or 0)
    nearest = int(parcels["nearest"] or 0)
    coverage = 100.0 * bound / total if total else 0.0
    nearest_pct = 100.0 * nearest / total if total else 0.0
    print("\n=== 5-GATE PREP REPORT ===")
    print(f"GATE 1 coverage {coverage:.1f}% (>=70%) - {'PASS' if coverage >= 70 else 'SUB'}")
    print(f"GATE 2 nearest {nearest_pct:.1f}% (<30%) - {'PASS' if nearest_pct < 30 else 'OVER'}")
    print(
        f"GATE 3 parcel raw empty {parcels['empty_raw']} / "
        f"zoning raw empty {districts['empty_raw']}"
    )
    print(f"GATE 4 districts {districts['total']} / distinct codes {districts['codes']}")
    print("GATE 5 bbox populated inline")
    print(
        f"  parcels {total:,} bound {bound:,} contained {parcels['contained']:,} "
        f"nearest {nearest:,}"
    )
    codes = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*) AS n
          FROM parcels
         WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
         GROUP BY 1
         ORDER BY 2 DESC, 1
         LIMIT 40
        """,
        jid,
    )
    if codes:
        print("\nDistribution:")
        for row in codes:
            print(f"  {row['zoning_code']:14s} {row['n']:>6,}")


async def _preflight(max_parcels: int | None) -> int:
    print("\n=== PRE-FLIGHT: Lake Oswego OR source shape (NO DB WRITES) ===\n")
    parcels, zoning = await _fetch_sources(max_parcels=max_parcels)
    parcel_rows, parcel_stats = _parcel_rows(parcels, "00000000-0000-0000-0000-000000000000")
    zoning_rows, zoning_stats = _zoning_rows(zoning)

    parcel_attrs = [feature.get("properties") or {} for feature in parcels]
    counties: dict[str, int] = {}
    for attrs in parcel_attrs:
        county = _county_name(attrs.get("COUNTY")) or "unknown"
        counties[county] = counties.get(county, 0) + 1
    parcel_apns = [row[1] for row in parcel_rows]
    zones = sorted({row["zone_code"] for row in zoning_rows})

    print(f"parcel features fetched: {len(parcels):,}")
    print(f"parcel rows built      : {len(parcel_rows):,}")
    print(f"parcel unique APNs     : {len(set(parcel_apns)):,}")
    print(f"parcel build stats     : {parcel_stats}")
    print(f"parcel county split    : {counties}")
    print(f"zoning features fetched: {len(zoning):,}")
    print(f"zoning rows built      : {len(zoning_rows):,}")
    print(f"zoning build stats     : {zoning_stats}")
    print(f"zoning distinct codes  : {len(zones)}")
    print(f"zoning sample codes    : {zones[:25]}")
    if parcel_attrs:
        print(f"parcel raw field count : {len(parcel_attrs[0])}")
    if zoning:
        print(f"zoning raw field count : {len(zoning[0].get('properties') or {})}")
    print("\n(NO DB WRITES - source-only validation.)")
    return 0


async def _run(*, dry_run: bool, max_parcels: int | None, nearest_meters: float) -> int:
    if max_parcels is not None and not dry_run:
        raise SystemExit("--max-parcels is allowed only with --dry-run")
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Lake Oswego OR Class B per-muni adapter ===\n")
    started = time.time()
    parcels, zoning = await _fetch_sources(max_parcels=max_parcels)

    conn = await asyncpg.connect(
        _session_db_url(),
        statement_cache_size=0,
        command_timeout=7200,
    )
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            jid = await _register_jurisdiction(conn)

            cleared = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                jid,
            )
            print(f"[idempotency] cleared {cleared.split()[-1]} zoning_district rows")
            reset = await _reset_bindings(conn, jid)
            print(f"[idempotency] reset {reset:,} parcel bindings")

            parcel_rows = await _stage_and_merge_parcels(conn, parcels, jid)
            print(f"[parcels] staged/upserted {parcel_rows:,} Lake Oswego rows")
            reset = await _reset_bindings(conn, jid)
            print(f"[idempotency] reset {reset:,} parcel bindings after upsert")

            zoning_rows = await _insert_zoning_districts(conn, zoning, jid)
            print(f"[zoning] inserted {zoning_rows:,} Lake Oswego zoning rows")

            contained, nearest = await _spatial_backfill(conn, jid, nearest_meters)
            print(f"[spatial] contained UPDATEd {contained:,}")
            print(f"[spatial] nearest_{int(round(nearest_meters))}m UPDATEd {nearest:,}")

            bbox = await _update_bbox(conn, jid)
            print(f"[bbox] {bbox}")

            await _quality_report(conn, jid)

            if dry_run:
                raise _RollbackForDryRun()
    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    elapsed = time.time() - started
    print(f"\ncompleted in {elapsed / 60:.1f} min")
    return 0


class _RollbackForDryRun(Exception):
    """Sentinel raised inside the transaction context to trigger rollback."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Fetch and summarize public sources only; no database connection or writes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full write path inside a transaction, then roll back.",
    )
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    parser.add_argument(
        "--max-parcels",
        type=int,
        help="Preflight/dry-run cap for faster source-shape rehearsal.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.preflight:
        return asyncio.run(_preflight(args.max_parcels))
    if args.dry_run:
        return asyncio.run(
            _run(
                dry_run=True,
                max_parcels=args.max_parcels,
                nearest_meters=args.nearest_within_meters,
            )
        )
    if args.i_know_this_writes_to_prod:
        return asyncio.run(
            _run(
                dry_run=False,
                max_parcels=args.max_parcels,
                nearest_meters=args.nearest_within_meters,
            )
        )

    print(
        "Refusing - pass --preflight for source-only validation, --dry-run for "
        "transactional rehearsal, or --i-know-this-writes-to-prod to fire.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
