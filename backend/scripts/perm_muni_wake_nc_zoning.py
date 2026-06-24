"""Wake NC Class B per-muni zoning adapter (PREP — DO NOT FIRE).

Pattern: PR #334 Winnetka Class B per-muni adapter + NC OneMap statewide
parcel carry from the Wake / Mecklenburg acquisition specs.

Scope:
  - Parcel substrate: NC OneMap NC1Map Parcels polygons layer, Wake only.
    Shared upstream with Mecklenburg; this script scopes with the county-FIPS
    field (`stcntyfips='37183'`). Equivalent live fields are
    `cntyname='Wake'` / `cntyfips='183'`.
  - Cary zoning: Town of Cary `LandUse/Zoning/FeatureServer/11`.
    Cary is a separate incorporated town inside Wake.
  - Raleigh / North Raleigh zoning: City of Raleigh `Planning/Zoning`
    layer `MapServer/0`, spatially clipped/backfilled through the Raleigh
    Neighborhood Registry `District='Northeast'` AOI proxy for North Raleigh.
    North Raleigh is not a municipality; municipality discipline remains
    `parcels.city = 'Raleigh'`.

This file intentionally prepares the write path but this dispatch must not
fire it. Use `preflight` for read-only source validation. `fire` requires an
explicit production-write flag and is included only so the adapter is complete
for a later authorized operator.

Hard rules honored:
  - Idempotency: adapter-managed zoning districts are DELETEd before reinsert;
    target parcel bindings are reset before spatial backfill.
  - raw_attributes/raw preservation: parcel raw stores the full NC OneMap
    source row; zoning_districts.raw_attributes stores source metadata plus
    the full ArcGIS source attribute payload.
  - Municipality discipline: spatial backfill is scoped by `parcels.city`
    (`Cary` or `Raleigh`) and by `raw_attributes->>'muni_name'`; North Raleigh
    adds an AOI predicate but does not become a municipality.
  - PREP only: this PR should not execute `fire`.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.wkb import dumps as wkb_dumps

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("wake_nc_perm_muni")

ADAPTER_NAME = "perm_muni_wake_nc_zoning"
INGESTED_AT = "2026-06-23"

WAKE_JURISDICTION_NAME = "Wake County, NC"
WAKE_STATE = "NC"
WAKE_COUNTY = "Wake"

NC_ONEMAP_PARCELS_URL = (
    "https://services.nconemap.gov/secure/rest/services/"
    "NC1Map_Parcels/FeatureServer/1"
)
# Coordinate with Mecklenburg: same source layer, county-scoped read.
# Mecklenburg spec uses `stcntyfips='37119'`; Wake is `37183`.
WAKE_COUNTY_FILTER = "stcntyfips='37183'"
WAKE_EXPECTED_PARCELS = 435_381

TOWN_OF_CARY_ZONING_URL = (
    "https://maps-apis.carync.gov/server/rest/services/"
    "LandUse/Zoning/FeatureServer/11"
)
RALEIGH_ZONING_URL = (
    "https://maps.raleighnc.gov/arcgis/rest/services/"
    "Planning/Zoning/MapServer/0"
)
RALEIGH_NEIGHBORHOOD_REGISTRY_URL = (
    "https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/"
    "Raleigh_Neighborhood_Registry/FeatureServer/0"
)
NORTH_RALEIGH_AOI_FILTER = "District='Northeast'"

ARCGIS_PAGE_SIZE = 2000
NC_ONEMAP_PAGE_SIZE = 5000
PARCEL_BATCH_SIZE = 50_000

WAKE_BBOX_LON_RANGE = (-79.10, -78.10)
WAKE_BBOX_LAT_RANGE = (35.40, 36.20)

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
    city = COALESCE(EXCLUDED.city, parcels.city),
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


@dataclass(frozen=True)
class ZoningSource:
    key: str
    muni_name: str
    muni_type: str
    prod_city_value: str
    layer_url: str
    source_kind: str
    source_filter: str
    zone_code_field: str
    zone_name_field: str | None
    subarea_name: str | None = None
    aoi_filter: str | None = None
    polygon_filter_by_aoi: bool = False


ZONING_SOURCES: tuple[ZoningSource, ...] = (
    ZoningSource(
        key="cary",
        muni_name="Cary",
        muni_type="town",
        prod_city_value="Cary",
        layer_url=TOWN_OF_CARY_ZONING_URL,
        source_kind="arcgis_feature_server",
        source_filter="1=1",
        zone_code_field="ZONECLASS",
        zone_name_field="ZONEDESC",
    ),
    ZoningSource(
        key="north_raleigh",
        muni_name="Raleigh",
        muni_type="city",
        prod_city_value="Raleigh",
        layer_url=RALEIGH_ZONING_URL,
        source_kind="arcgis_map_server",
        source_filter="1=1",
        zone_code_field="ZONING",
        zone_name_field="ZONE_TYPE_DECODE",
        subarea_name="North Raleigh",
        aoi_filter=NORTH_RALEIGH_AOI_FILTER,
        polygon_filter_by_aoi=True,
    ),
)


def _session_db_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL or SUPABASE_DB_URL not set in environment")
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _title_city(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.title()


def _parse_geom(geom_json: dict[str, Any] | None) -> Any:
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


def _classify_residential(parusecode: Any, parusedesc: Any) -> bool | None:
    code = str(parusecode or "").upper().strip()
    desc = str(parusedesc or "").upper().strip()
    if code.startswith(("RH", "R")) or desc == "R" or "RES" in desc:
        return True
    if code or desc:
        return False
    return None


def _map_parcel_row(
    props: dict[str, Any],
    geom: Any,
    jid: uuid.UUID,
) -> dict[str, Any] | None:
    apn = props.get("parno")
    if not apn:
        return None
    apn = str(apn).strip()
    if not apn:
        return None

    land_value = _safe_float(props.get("landval"))
    improvement_value = _safe_float(props.get("improvval"))
    parcel_value = _safe_float(props.get("parval"))
    assessed_value = parcel_value
    if assessed_value is None and (land_value is not None or improvement_value is not None):
        assessed_value = (land_value or 0.0) + (improvement_value or 0.0)
    if assessed_value is not None and assessed_value <= 0:
        assessed_value = None

    has_structure = None
    struct_flag = str(props.get("struct") or "").strip().upper()
    if struct_flag in {"Y", "YES", "1", "TRUE", "T"}:
        has_structure = True
    elif struct_flag in {"N", "NO", "0", "FALSE", "F"}:
        has_structure = False
    elif improvement_value is not None:
        has_structure = improvement_value > 0

    raw = {
        "adapter": ADAPTER_NAME,
        "source_url": NC_ONEMAP_PARCELS_URL,
        "source_filter": WAKE_COUNTY_FILTER,
        "source_kind": "arcgis_feature_server",
        "county_filter_field": "stcntyfips",
        "county_filter_equivalents": {
            "cntyname": "Wake",
            "cntyfips": "183",
        },
        "source_attributes": props,
    }

    return {
        "jurisdiction_id": str(jid),
        "apn": apn,
        "address": str(props.get("siteadd")).strip() if props.get("siteadd") else None,
        "city": _title_city(props.get("scity")),
        "owner_name": str(props.get("ownname")).strip() if props.get("ownname") else None,
        "zoning_code": None,
        "zone_class": None,
        "land_use_code": str(props.get("parusecode")).strip() if props.get("parusecode") else None,
        "acres": _safe_float(props.get("gisacres")),
        "county_link": None,
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": improvement_value,
        "assessed_value": assessed_value,
        "is_residential": _classify_residential(props.get("parusecode"), props.get("parusedesc")),
        "geom": geom,
        "centroid": geom.centroid,
        "raw": raw,
    }


def _row_to_record(row: dict[str, Any]) -> tuple:
    return (
        row["jurisdiction_id"], row["apn"], row.get("address"), row.get("city"),
        row.get("owner_name"), row.get("zoning_code"), row.get("zone_class"),
        row.get("land_use_code"), row.get("acres"), row.get("county_link"),
        row.get("in_flood_zone"), bool(row.get("in_wetland")),
        row.get("avg_slope_pct"), row.get("has_structure"),
        row.get("improvement_value"), row.get("assessed_value"),
        row.get("is_residential"),
        wkb_dumps(row["geom"], hex=False, srid=4326),
        wkb_dumps(row["centroid"], hex=False, srid=4326),
        json.dumps(row["raw"]),
    )


async def _fetch_count(client: httpx.AsyncClient, url: str, where: str) -> int:
    r = await client.get(
        f"{url}/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
    )
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return int(payload.get("count") or 0)


async def _fetch_geojson_features(
    client: httpx.AsyncClient,
    url: str,
    where: str,
    *,
    page_size: int = ARCGIS_PAGE_SIZE,
    max_features: int | None = None,
    order_by: str | None = None,
    start_offset: int = 0,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = start_offset
    while True:
        limit = page_size
        if max_features is not None:
            remaining = max_features - len(features)
            if remaining <= 0:
                break
            limit = min(limit, remaining)
        params = {
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
        r = await client.get(f"{url}/query", params=params)
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info("fetched %d features from %s offset=%d cumulative=%d",
                    len(batch), url, offset, len(features))
        if len(batch) < limit:
            break
        offset += len(batch)
    return features


async def _fetch_north_raleigh_aoi(client: httpx.AsyncClient) -> Any:
    features = await _fetch_geojson_features(
        client,
        RALEIGH_NEIGHBORHOOD_REGISTRY_URL,
        NORTH_RALEIGH_AOI_FILTER,
        page_size=1000,
    )
    geoms = []
    for feature in features:
        geom = _parse_geom(feature.get("geometry"))
        if geom is not None:
            geoms.append(geom)
    if not geoms:
        raise RuntimeError("North Raleigh AOI query returned no usable geometry")
    return make_valid(unary_union(geoms))


def _build_zoning_rows(
    source: ZoningSource,
    features: list[dict[str, Any]],
    jid: uuid.UUID,
    *,
    aoi_geom: Any | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        geom = _parse_geom(feature.get("geometry"))
        if geom is None:
            continue
        if source.polygon_filter_by_aoi:
            if aoi_geom is None:
                raise RuntimeError(f"{source.key} requires an AOI geometry")
            if not geom.intersects(aoi_geom):
                continue
        zone_code = props.get(source.zone_code_field)
        if not zone_code or not str(zone_code).strip():
            continue
        zone_name = props.get(source.zone_name_field) if source.zone_name_field else None
        raw_attributes = {
            "adapter": ADAPTER_NAME,
            "source_url": source.layer_url,
            "source_filter": source.source_filter,
            "source_kind": source.source_kind,
            "ingested_at": INGESTED_AT,
            "muni_name": source.muni_name,
            "muni_type": source.muni_type,
            "prod_city_value": source.prod_city_value,
            "subarea_name": source.subarea_name,
            "aoi_source_url": RALEIGH_NEIGHBORHOOD_REGISTRY_URL if source.aoi_filter else None,
            "aoi_filter": source.aoi_filter,
            "source_attributes": props,
        }
        rows.append({
            "jurisdiction_id": str(jid),
            "source_key": source.key,
            "muni_name": source.muni_name,
            "prod_city_value": source.prod_city_value,
            "subarea_name": source.subarea_name,
            "zone_code": str(zone_code).strip(),
            "zone_name": str(zone_name).strip() if zone_name else str(zone_code).strip(),
            "geom_wkt": geom.wkt,
            "raw_attributes": json.dumps(raw_attributes),
        })
    return rows


async def _resolve_or_register_wake(conn: asyncpg.Connection) -> uuid.UUID:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        WAKE_JURISDICTION_NAME,
        WAKE_STATE,
    )
    if existing:
        return existing["id"]

    jid = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO jurisdictions (id, name, state, county, parcel_endpoint)
        VALUES ($1::uuid, $2, $3, $4, $5)
        """,
        str(jid),
        WAKE_JURISDICTION_NAME,
        WAKE_STATE,
        WAKE_COUNTY,
        NC_ONEMAP_PARCELS_URL,
    )
    return jid


async def _copy_upsert_parcels(rows: list[dict[str, Any]]) -> int:
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        async with conn.transaction():
            await conn.execute(_CREATE_STAGE_SQL)
            await conn.execute(_TRUNCATE_STAGE_SQL)
            for i in range(0, len(rows), 25_000):
                records = [_row_to_record(r) for r in rows[i : i + 25_000]]
                await conn.copy_records_to_table(
                    "_stage_parcels",
                    records=records,
                    columns=_STAGE_COLUMNS,
                )
            inserted = await conn.fetchval(
                "WITH ins AS (" + _MERGE_SQL + " RETURNING 1) SELECT COUNT(*) FROM ins"
            )
            return int(inserted or 0)
    finally:
        await conn.close()


async def _ingest_parcels(jid: uuid.UUID) -> int:
    started = time.time()
    total_mapped = 0
    total_upserted = 0
    total_geom_skipped = 0
    total_apn_skipped = 0

    async with httpx.AsyncClient(timeout=180.0) as client:
        source_count = await _fetch_count(client, NC_ONEMAP_PARCELS_URL, WAKE_COUNTY_FILTER)
        if source_count < 400_000:
            raise RuntimeError(
                f"Wake NC OneMap count unexpectedly low: {source_count:,}; "
                f"expected about {WAKE_EXPECTED_PARCELS:,}"
            )
        print(f"[parcels] source count {source_count:,} via {WAKE_COUNTY_FILTER}")

        for offset in range(0, source_count, PARCEL_BATCH_SIZE):
            features = await _fetch_geojson_features(
                client,
                NC_ONEMAP_PARCELS_URL,
                WAKE_COUNTY_FILTER,
                page_size=NC_ONEMAP_PAGE_SIZE,
                max_features=min(PARCEL_BATCH_SIZE, source_count - offset),
                order_by="objectid",
                start_offset=offset,
            )

            rows_by_apn: dict[str, dict[str, Any]] = {}
            geom_skipped = apn_skipped = 0
            for feature in features:
                props = feature.get("properties") or {}
                geom = _parse_geom(feature.get("geometry"))
                if geom is None:
                    geom_skipped += 1
                    continue
                mapped = _map_parcel_row(props, geom, jid)
                if mapped is None:
                    apn_skipped += 1
                    continue
                rows_by_apn[mapped["apn"]] = mapped

            rows = list(rows_by_apn.values())
            total_mapped += len(rows)
            total_geom_skipped += geom_skipped
            total_apn_skipped += apn_skipped
            upserted = await _copy_upsert_parcels(rows) if rows else 0
            total_upserted += upserted
            print(
                f"[parcels] offset={offset:>7} fetched={len(features):>6} "
                f"mapped={len(rows):>6} upserted={upserted:>6} "
                f"geom_skip={geom_skipped} apn_skip={apn_skipped} "
                f"cumulative={total_upserted:,}",
                flush=True,
            )

    elapsed = time.time() - started
    print(
        f"[parcels] complete mapped={total_mapped:,} upserted={total_upserted:,} "
        f"geom_skip={total_geom_skipped:,} apn_skip={total_apn_skipped:,} "
        f"elapsed={elapsed / 60:.1f}m"
    )
    return total_upserted


async def _load_temp_aoi(conn: asyncpg.Connection, aoi_geom: Any) -> None:
    await conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _wake_nc_north_raleigh_aoi (geom geometry(GEOMETRY, 4326))"
    )
    await conn.execute("TRUNCATE _wake_nc_north_raleigh_aoi")
    await conn.execute(
        """
        INSERT INTO _wake_nc_north_raleigh_aoi (geom)
        VALUES (ST_Multi(ST_MakeValid(ST_GeomFromText($1, 4326))))
        """,
        aoi_geom.wkt,
    )


def _target_predicate(
    source: ZoningSource,
    table_alias: str = "p",
    *,
    city_param: str = "$3",
) -> str:
    base = f"{table_alias}.city = {city_param}"
    if source.aoi_filter:
        return (
            base
            + f""" AND EXISTS (
                SELECT 1 FROM _wake_nc_north_raleigh_aoi aoi
                WHERE ST_Intersects(ST_Centroid({table_alias}.geom), aoi.geom)
            )"""
        )
    return base


async def _reset_bindings(conn: asyncpg.Connection, jid: uuid.UUID, source: ZoningSource) -> int:
    predicate = _target_predicate(source, "p", city_param="$2")
    status = await conn.execute(
        f"""
        UPDATE parcels p
           SET zoning_code = NULL,
               zone_class = NULL,
               zone_binding_method = NULL,
               updated_at = NOW()
         WHERE p.jurisdiction_id = $1::uuid
           AND {predicate}
        """,
        str(jid),
        source.prod_city_value,
    )
    return int(status.split()[-1])


async def _insert_zoning_rows(
    conn: asyncpg.Connection,
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        await conn.execute(
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
            row["jurisdiction_id"],
            row["zone_code"],
            row["zone_name"],
            row["geom_wkt"],
            row["raw_attributes"],
        )


async def _spatial_backfill(
    conn: asyncpg.Connection,
    jid: uuid.UUID,
    source: ZoningSource,
    *,
    nearest_within_meters: float,
) -> tuple[int, int]:
    target_predicate = _target_predicate(source, "p")
    contained_status = await conn.execute(
        f"""
        UPDATE parcels target
        SET zone_class = sub.zone_class,
            zone_binding_method = 'contained',
            zoning_code = sub.zone_code,
            updated_at = NOW()
        FROM (
            SELECT p.id AS parcel_id, m.zone_class, m.zone_code
            FROM parcels p,
            LATERAL (
                SELECT zd.zone_class, zd.zone_code
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id = $1::uuid
                  AND zd.raw_attributes->>'adapter' = $2
                  AND zd.raw_attributes->>'muni_name' = $4
                  AND zd.geom IS NOT NULL
                  AND ST_Within(ST_Centroid(p.geom), zd.geom)
                ORDER BY zd.id
                LIMIT 1
            ) m
            WHERE p.jurisdiction_id = $1::uuid
              AND p.geom IS NOT NULL
              AND {target_predicate}
        ) sub
        WHERE target.id = sub.parcel_id
        """,
        str(jid),
        ADAPTER_NAME,
        source.prod_city_value,
        source.muni_name,
    )
    contained = int(contained_status.split()[-1])

    binding_label = f"nearest_{int(round(nearest_within_meters))}m"
    nearest_status = await conn.execute(
        f"""
        UPDATE parcels target
        SET zone_class = sub.zone_class,
            zone_binding_method = $5,
            zoning_code = sub.zone_code,
            updated_at = NOW()
        FROM (
            SELECT p.id AS parcel_id, m.zone_class, m.zone_code
            FROM parcels p,
            LATERAL (
                SELECT zd.zone_class, zd.zone_code
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id = $1::uuid
                  AND zd.raw_attributes->>'adapter' = $2
                  AND zd.raw_attributes->>'muni_name' = $4
                  AND zd.geom IS NOT NULL
                  AND ST_DWithin(
                      zd.geom::geography,
                      ST_Centroid(p.geom)::geography,
                      $6
                  )
                ORDER BY ST_Distance(
                    zd.geom::geography,
                    ST_Centroid(p.geom)::geography
                )
                LIMIT 1
            ) m
            WHERE p.jurisdiction_id = $1::uuid
              AND p.geom IS NOT NULL
              AND p.zone_binding_method IS NULL
              AND {target_predicate}
        ) sub
        WHERE target.id = sub.parcel_id
        """,
        str(jid),
        ADAPTER_NAME,
        source.prod_city_value,
        source.muni_name,
        binding_label,
        float(nearest_within_meters),
    )
    nearest = int(nearest_status.split()[-1])
    return contained, nearest


async def _update_bbox(conn: asyncpg.Connection, jid: uuid.UUID) -> list[float]:
    ext = await conn.fetchrow(
        """
        SELECT ST_XMin(ST_Extent(geom)) AS minx,
               ST_YMin(ST_Extent(geom)) AS miny,
               ST_XMax(ST_Extent(geom)) AS maxx,
               ST_YMax(ST_Extent(geom)) AS maxy
        FROM parcels
        WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
        """,
        str(jid),
    )
    if ext is None or ext["minx"] is None:
        raise RuntimeError("Wake bbox update failed: no parcel geometry")
    bbox = [
        float(ext["minx"]),
        float(ext["miny"]),
        float(ext["maxx"]),
        float(ext["maxy"]),
    ]
    if not (
        WAKE_BBOX_LON_RANGE[0] <= bbox[0] <= WAKE_BBOX_LON_RANGE[1]
        and WAKE_BBOX_LAT_RANGE[0] <= bbox[1] <= WAKE_BBOX_LAT_RANGE[1]
    ):
        raise RuntimeError(f"Wake bbox {bbox} outside expected NC envelope")
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        str(jid),
        json.dumps(bbox),
    )
    return bbox


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Wake NC per-muni zoning adapter (NO DB WRITES) ===\n")
    fake_jid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    async with httpx.AsyncClient(timeout=180.0) as client:
        parcel_count = await _fetch_count(client, NC_ONEMAP_PARCELS_URL, WAKE_COUNTY_FILTER)
        print(f"NC OneMap Wake parcel count: {parcel_count:,} ({WAKE_COUNTY_FILTER})")

        parcel_sample = await _fetch_geojson_features(
            client,
            NC_ONEMAP_PARCELS_URL,
            WAKE_COUNTY_FILTER,
            page_size=1000,
            max_features=1000,
        )
        mapped = []
        cities: dict[str, int] = {}
        raw_counts: list[int] = []
        for feature in parcel_sample:
            geom = _parse_geom(feature.get("geometry"))
            if geom is None:
                continue
            row = _map_parcel_row(feature.get("properties") or {}, geom, fake_jid)
            if row is None:
                continue
            mapped.append(row)
            if row.get("city"):
                cities[row["city"]] = cities.get(row["city"], 0) + 1
            raw_counts.append(len(row["raw"]["source_attributes"]))
        print(f"Parcel sample fetched/mapped: {len(parcel_sample):,}/{len(mapped):,}")
        if raw_counts:
            print(
                "Parcel raw field-count avg/min/max: "
                f"{sum(raw_counts) / len(raw_counts):.1f}/"
                f"{min(raw_counts)}/{max(raw_counts)}"
            )
        print("Top sample cities:")
        for city, n in sorted(cities.items(), key=lambda x: -x[1])[:10]:
            print(f"  {city:20s} {n:>4}")

        north_raleigh_aoi = await _fetch_north_raleigh_aoi(client)
        print(f"North Raleigh AOI proxy: {NORTH_RALEIGH_AOI_FILTER}")
        print(f"North Raleigh AOI bounds: {[round(v, 6) for v in north_raleigh_aoi.bounds]}")

        for source in ZONING_SOURCES:
            source_count = await _fetch_count(client, source.layer_url, source.source_filter)
            features = await _fetch_geojson_features(
                client,
                source.layer_url,
                source.source_filter,
                page_size=ARCGIS_PAGE_SIZE,
            )
            rows = _build_zoning_rows(
                source,
                features,
                fake_jid,
                aoi_geom=north_raleigh_aoi if source.aoi_filter else None,
            )
            codes = sorted({row["zone_code"] for row in rows})
            print(f"\n{source.key}:")
            print(f"  source features : {source_count:,}")
            print(f"  rows built      : {len(rows):,}")
            print(f"  distinct codes  : {len(codes):,}")
            print(f"  sample codes    : {codes[:15]}")
            if rows:
                sample_raw = json.loads(rows[0]["raw_attributes"])
                attrs = sample_raw.get("source_attributes") or {}
                print(
                    f"  raw top fields  : muni_name={sample_raw.get('muni_name')!r}, "
                    f"subarea={sample_raw.get('subarea_name')!r}, "
                    f"source_attrs={len(attrs)}"
                )

    print("\n(NO DB WRITES — prep-only source and mapping shape validated.)")
    return 0


async def _fire(nearest_within_meters: float, skip_parcels: bool) -> int:
    print("\n=== FIRE: Wake NC parcel + per-muni zoning adapter ===\n")
    conn = await asyncpg.connect(
        _session_db_url(),
        statement_cache_size=0,
        command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        jid = await _resolve_or_register_wake(conn)
        print(f"[jurisdiction] {WAKE_JURISDICTION_NAME}: {jid}")
    finally:
        await conn.close()

    if not skip_parcels:
        await _ingest_parcels(jid)

    async with httpx.AsyncClient(timeout=180.0) as client:
        north_raleigh_aoi = await _fetch_north_raleigh_aoi(client)
        zoning_rows: dict[str, list[dict[str, Any]]] = {}
        for source in ZONING_SOURCES:
            features = await _fetch_geojson_features(
                client,
                source.layer_url,
                source.source_filter,
                page_size=ARCGIS_PAGE_SIZE,
            )
            zoning_rows[source.key] = _build_zoning_rows(
                source,
                features,
                jid,
                aoi_geom=north_raleigh_aoi if source.aoi_filter else None,
            )

    conn = await asyncpg.connect(
        _session_db_url(),
        statement_cache_size=0,
        command_timeout=3600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            await _load_temp_aoi(conn, north_raleigh_aoi)

            deleted = await conn.execute(
                """
                DELETE FROM zoning_districts
                WHERE jurisdiction_id=$1::uuid
                  AND raw_attributes->>'adapter'=$2
                """,
                str(jid),
                ADAPTER_NAME,
            )
            print(f"[idempotency] cleared adapter zoning_districts: {deleted.split()[-1]}")

            for source in ZONING_SOURCES:
                reset = await _reset_bindings(conn, jid, source)
                print(
                    f"[idempotency] reset parcel bindings for {source.key}: "
                    f"{reset:,}"
                )

            for source in ZONING_SOURCES:
                rows = zoning_rows[source.key]
                await _insert_zoning_rows(conn, rows)
                print(f"[zoning] inserted {source.key}: {len(rows):,}")

            for source in ZONING_SOURCES:
                contained, nearest = await _spatial_backfill(
                    conn,
                    jid,
                    source,
                    nearest_within_meters=nearest_within_meters,
                )
                print(
                    f"[spatial] {source.key}: contained={contained:,} "
                    f"nearest_{int(round(nearest_within_meters))}m={nearest:,}"
                )

            bbox = await _update_bbox(conn, jid)
            print(f"[bbox] Wake bbox updated: {bbox}")

        for source in ZONING_SOURCES:
            stats = await conn.fetchrow(
                f"""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (
                         WHERE zoning_code IS NOT NULL AND btrim(zoning_code) <> ''
                       ) AS bound,
                       COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
                       COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest
                FROM parcels p
                WHERE p.jurisdiction_id=$1::uuid
                  AND {_target_predicate(source, "p", city_param="$2")}
                """,
                str(jid),
                source.prod_city_value,
            )
            total = int(stats["total"] or 0)
            bound = int(stats["bound"] or 0)
            pct = 100.0 * bound / total if total else 0.0
            print(
                f"[gate] {source.key}: parcels={total:,} bound={bound:,} "
                f"coverage={pct:.1f}% contained={int(stats['contained'] or 0):,} "
                f"nearest={int(stats['nearest'] or 0):,}"
            )

    finally:
        await conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")

    fire = sub.add_parser("fire")
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    fire.add_argument("--skip-parcels", action="store_true")
    fire.add_argument("--nearest-within-meters", type=float, default=50.0)

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.cmd == "preflight":
        return asyncio.run(_preflight())
    if args.cmd == "fire":
        if not args.i_know_this_writes_to_prod:
            print(
                "Refusing to fire without --i-know-this-writes-to-prod. "
                "This PR is PREP ONLY; do not fire from this dispatch.",
                file=sys.stderr,
            )
            return 2
        return asyncio.run(
            _fire(
                nearest_within_meters=args.nearest_within_meters,
                skip_parcels=args.skip_parcels,
            )
        )
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
