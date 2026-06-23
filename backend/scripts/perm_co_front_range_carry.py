"""PREP-only Colorado Front Range multi-county carry adapter.

This adapter follows the Hennepin/MetroGIS carry pattern for a statewide
parcel source. When fired by an operator, it performs one guarded carry
sequence:

1. Register/find the three county umbrella jurisdictions:
   Douglas County, CO; Arapahoe County, CO; Jefferson County, CO.
2. Ingest Colorado Public Parcels statewide records filtered to those
   three counties into their county umbrella JIDs.
3. Register/find the three wealth-pocket center jurisdictions inside the
   county umbrellas:
   Highlands Ranch, CO; Cherry Hills Village, CO; Golden, CO.
4. Move matching parcels from the county umbrella JIDs to the per-muni
   JIDs using PATH 1 discipline. Parcel raw payloads are not rewritten.
5. Ingest per-muni zoning districts into the three wealth-pocket JIDs and
   spatially backfill parcel zoning in those same JIDs.

DO NOT FIRE from automation. This file is prep for the OP5 carry. The
`fire` command requires an explicit production-write acknowledgement flag.

Sources are documented in docs/CO_FRONT_RANGE_ACQUISITION_SPEC.md.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import asyncpg
import httpx
from dotenv import load_dotenv
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.wkb import dumps as wkb_dumps


load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL environment variable is required")


STATE = "CO"
PAGE_SIZE = 2000
BATCH_SIZE = 25_000
REQUEST_TIMEOUT = httpx.Timeout(120.0)

CO_PUBLIC_PARCELS_LAYER = (
    "https://gis.colorado.gov/public/rest/services/Address_and_Parcel/"
    "Colorado_Public_Parcels/FeatureServer/0"
)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://",
        "postgresql://",
    )


@dataclass(frozen=True)
class CountyConfig:
    name: str
    county: str
    source_county_name: str
    where: str


@dataclass(frozen=True)
class ZoningSourceConfig:
    name: str
    layer_url: str
    where: str
    object_id_field: str
    zone_code_field: str
    zone_name_field: str | None
    zone_class_field: str | None = None


@dataclass(frozen=True)
class MuniConfig:
    name: str
    county: str
    parent_county_name: str
    prod_city_value: str
    raw_city_values: tuple[str, ...]
    source_scope_note: str
    zoning: ZoningSourceConfig


COUNTIES: tuple[CountyConfig, ...] = (
    CountyConfig(
        name="Douglas County, CO",
        county="Douglas",
        source_county_name="Douglas",
        where="countyName = 'Douglas'",
    ),
    CountyConfig(
        name="Arapahoe County, CO",
        county="Arapahoe",
        source_county_name="Arapahoe",
        where="countyName = 'Arapahoe'",
    ),
    CountyConfig(
        name="Jefferson County, CO",
        county="Jefferson",
        source_county_name="Jefferson",
        where="countyName = 'Jefferson'",
    ),
)

MUNIS: tuple[MuniConfig, ...] = (
    MuniConfig(
        name="Highlands Ranch, CO",
        county="Douglas",
        parent_county_name="Douglas County, CO",
        prod_city_value="Highlands Ranch",
        raw_city_values=("HIGHLANDS RANCH", "Highlands Ranch"),
        source_scope_note=(
            "Highlands Ranch is a CDP. Zoning comes from the Douglas County "
            "ZONING layer and is stored on the Highlands Ranch jurisdiction."
        ),
        zoning=ZoningSourceConfig(
            name="Douglas County ZONING",
            layer_url="https://apps.douglas.co.us/gisod/rest/services/Landuse/MapServer/1",
            where="1=1",
            object_id_field="OBJECTID",
            zone_code_field="ZONE_TYPE",
            zone_name_field="FIRST_DESC",
        ),
    ),
    MuniConfig(
        name="Cherry Hills Village, CO",
        county="Arapahoe",
        parent_county_name="Arapahoe County, CO",
        prod_city_value="Cherry Hills Village",
        raw_city_values=("CHERRY HILLS VILLAGE", "Cherry Hills Village"),
        source_scope_note=(
            "Cherry Hills Village is an incorporated municipality inside "
            "Arapahoe County. Zoning comes from the Arapahoe County zoning "
            "FeatureServer layer identified in the CO Front Range spec."
        ),
        zoning=ZoningSourceConfig(
            name="Arapahoe County Zoning",
            layer_url=(
                "https://services2.arcgis.com/OSbOBWdLkmvu5I9F/arcgis/rest/services/"
                "AC_WSS_Arapahoe_County_Zoning/FeatureServer/89"
            ),
            where="1=1",
            object_id_field="OBJECTID",
            zone_code_field="ZONING",
            zone_name_field="Zoning_Doc",
        ),
    ),
    MuniConfig(
        name="Golden, CO",
        county="Jefferson",
        parent_county_name="Jefferson County, CO",
        prod_city_value="Golden",
        raw_city_values=("GOLDEN", "Golden"),
        source_scope_note=(
            "Golden is an incorporated municipality inside Jefferson County. "
            "Zoning comes from the City of Golden zoning FeatureServer layer."
        ),
        zoning=ZoningSourceConfig(
            name="City of Golden Zoning",
            layer_url=(
                "https://services1.arcgis.com/FP2GwMAr4SrmXGhq/arcgis/rest/services/"
                "Zoning/FeatureServer/0"
            ),
            where="1=1",
            object_id_field="OBJECTID",
            zone_code_field="Zone_Code",
            zone_name_field="Zone_Description",
        ),
    ),
)


_CREATE_STAGE_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _stage_parcels (
    jurisdiction_id TEXT NOT NULL,
    apn TEXT NOT NULL,
    address TEXT,
    city TEXT,
    owner_name TEXT,
    acres NUMERIC,
    zoning_code TEXT,
    land_use_code TEXT,
    improvement_value NUMERIC,
    assessed_value NUMERIC,
    is_residential BOOLEAN,
    has_structure BOOLEAN,
    county_link TEXT,
    geom_wkt TEXT,
    raw_json TEXT NOT NULL
) ON COMMIT PRESERVE ROWS;
"""

_TRUNCATE_STAGE_SQL = "TRUNCATE _stage_parcels;"

_MERGE_PARCELS_SQL = """
WITH normalized AS (
    SELECT
        jurisdiction_id::uuid AS jurisdiction_id,
        apn,
        NULLIF(TRIM(address), '') AS address,
        NULLIF(TRIM(city), '') AS city,
        'CO'::text AS state,
        NULLIF(TRIM(owner_name), '') AS owner_name,
        acres,
        NULLIF(TRIM(zoning_code), '') AS zoning_code,
        NULLIF(TRIM(land_use_code), '') AS land_use_code,
        improvement_value,
        assessed_value,
        is_residential,
        has_structure,
        NULLIF(TRIM(county_link), '') AS county_link,
        ST_Multi(ST_MakeValid(ST_GeomFromText(geom_wkt, 4326))) AS geom,
        raw_json::jsonb AS raw
    FROM _stage_parcels
    WHERE apn IS NOT NULL
      AND NULLIF(TRIM(apn), '') IS NOT NULL
      AND geom_wkt IS NOT NULL
),
deduped AS (
    SELECT DISTINCT ON (jurisdiction_id, apn)
        jurisdiction_id,
        apn,
        address,
        city,
        state,
        owner_name,
        acres,
        zoning_code,
        land_use_code,
        improvement_value,
        assessed_value,
        is_residential,
        has_structure,
        county_link,
        geom,
        raw
    FROM normalized
    ORDER BY jurisdiction_id, apn, address NULLS LAST
),
upserted AS (
    INSERT INTO parcels (
        jurisdiction_id,
        apn,
        address,
        city,
        state,
        owner_name,
        acres,
        zoning_code,
        land_use_code,
        improvement_value,
        assessed_value,
        is_residential,
        has_structure,
        county_link,
        geom,
        centroid,
        raw,
        updated_at
    )
    SELECT
        jurisdiction_id,
        apn,
        address,
        city,
        state,
        owner_name,
        acres,
        zoning_code,
        land_use_code,
        improvement_value,
        assessed_value,
        is_residential,
        has_structure,
        county_link,
        geom,
        ST_PointOnSurface(geom),
        raw,
        NOW()
    FROM deduped
    ON CONFLICT ON CONSTRAINT uq_parcels_jurisdiction_apn
    DO UPDATE SET
        address = EXCLUDED.address,
        city = EXCLUDED.city,
        state = EXCLUDED.state,
        owner_name = EXCLUDED.owner_name,
        acres = EXCLUDED.acres,
        land_use_code = EXCLUDED.land_use_code,
        improvement_value = EXCLUDED.improvement_value,
        assessed_value = EXCLUDED.assessed_value,
        is_residential = EXCLUDED.is_residential,
        has_structure = EXCLUDED.has_structure,
        county_link = EXCLUDED.county_link,
        geom = EXCLUDED.geom,
        centroid = EXCLUDED.centroid,
        raw = EXCLUDED.raw,
        updated_at = NOW()
    RETURNING 1
)
SELECT COUNT(*)::INTEGER FROM upserted;
"""

_INSERT_ZONING_SQL = """
WITH geom_input AS (
    SELECT ST_Multi(ST_MakeValid(ST_GeomFromText($5, 4326))) AS geom
),
upserted AS (
    INSERT INTO zoning_districts (
        jurisdiction_id,
        zone_code,
        zone_name,
        zone_class,
        raw_attributes,
        geom,
        centroid,
        source,
        confidence,
        human_reviewed,
        geom_hash,
        updated_at
    )
    SELECT
        $1::uuid,
        $2,
        $3,
        $4,
        $6::jsonb,
        geom,
        ST_PointOnSurface(geom),
        'arcgis',
        0.90,
        FALSE,
        $7,
        NOW()
    FROM geom_input
    ON CONFLICT ON CONSTRAINT uq_zoning_districts_jur_code_hash
    DO UPDATE SET
        zone_name = EXCLUDED.zone_name,
        zone_class = EXCLUDED.zone_class,
        raw_attributes = EXCLUDED.raw_attributes,
        geom = EXCLUDED.geom,
        centroid = EXCLUDED.centroid,
        source = EXCLUDED.source,
        confidence = EXCLUDED.confidence,
        updated_at = NOW()
    RETURNING 1
)
SELECT COUNT(*)::INTEGER FROM upserted;
"""

_BACKFILL_CONTAINED_SQL = """
WITH contained AS (
    SELECT DISTINCT ON (p.id)
        p.id AS parcel_id,
        zd.zone_code,
        zd.zone_class
    FROM parcels p
    JOIN zoning_districts zd
      ON zd.jurisdiction_id = $1::uuid
     AND zd.raw_attributes->>'muni_name' = $2
     AND p.geom IS NOT NULL
     AND ST_Covers(zd.geom, ST_PointOnSurface(p.geom))
    WHERE p.jurisdiction_id = $1::uuid
      AND (p.zone_binding_method IS NULL OR p.zoning_code IS NULL)
    ORDER BY p.id, ST_Area(zd.geom) ASC
),
updated AS (
    UPDATE parcels p
    SET
        zoning_code = contained.zone_code,
        zone_class = contained.zone_class,
        zone_binding_method = 'contained',
        updated_at = NOW()
    FROM contained
    WHERE p.id = contained.parcel_id
    RETURNING 1
)
SELECT COUNT(*)::INTEGER FROM updated;
"""

_BACKFILL_NEAREST_SQL = """
WITH remaining AS (
    SELECT
        p.id,
        p.geom,
        ST_PointOnSurface(p.geom) AS point_geom
    FROM parcels p
    WHERE p.jurisdiction_id = $1::uuid
      AND p.geom IS NOT NULL
      AND (p.zone_binding_method IS NULL OR p.zoning_code IS NULL)
),
nearest AS (
    SELECT DISTINCT ON (r.id)
        r.id AS parcel_id,
        zd.zone_code,
        zd.zone_class
    FROM remaining r
    JOIN zoning_districts zd
      ON zd.jurisdiction_id = $1::uuid
     AND zd.raw_attributes->>'muni_name' = $2
     AND ST_DWithin(
         r.point_geom::geography,
         ST_ClosestPoint(zd.geom, r.point_geom)::geography,
         50
     )
    ORDER BY
        r.id,
        ST_Distance(r.point_geom::geography, ST_ClosestPoint(zd.geom, r.point_geom)::geography)
),
updated AS (
    UPDATE parcels p
    SET
        zoning_code = nearest.zone_code,
        zone_class = nearest.zone_class,
        zone_binding_method = 'nearest_50m',
        updated_at = NOW()
    FROM nearest
    WHERE p.id = nearest.parcel_id
    RETURNING 1
)
SELECT COUNT(*)::INTEGER FROM updated;
"""

_PRUNE_NON_MUNI_ZONING_SQL = """
WITH deleted AS (
    DELETE FROM zoning_districts zd
    WHERE zd.jurisdiction_id = $1::uuid
      AND zd.raw_attributes->>'muni_name' = $2
      AND NOT EXISTS (
          SELECT 1
          FROM parcels p
          WHERE p.jurisdiction_id = $1::uuid
            AND p.geom IS NOT NULL
            AND p.geom && zd.geom
            AND ST_Intersects(p.geom, zd.geom)
      )
    RETURNING 1
)
SELECT COUNT(*)::INTEGER FROM deleted;
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _trim(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _title_city(value: Any) -> str | None:
    text = _trim(value)
    if not text:
        return None
    return " ".join(part.capitalize() for part in text.split())


def _numeric(value: Any) -> Decimal | None:
    text = _trim(value)
    if not text:
        return None
    cleaned = re.sub(r"[$,]", "", text)
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _residential_hint(props: dict[str, Any]) -> bool | None:
    desc = " ".join(
        str(props.get(field) or "")
        for field in ("landUseDsc", "zoningDesc")
    ).lower()
    if any(token in desc for token in ("residential", "single family", "condo", "townhouse")):
        return True
    if any(token in desc for token in ("commercial", "industrial", "retail", "office")):
        return False
    return None


def _signed_area(coords: list[tuple[float, float]]) -> float:
    area = 0.0
    for idx in range(len(coords) - 1):
        x1, y1 = coords[idx]
        x2, y2 = coords[idx + 1]
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _ring_to_coords(ring: list[list[float]]) -> list[tuple[float, float]]:
    coords = [(float(point[0]), float(point[1])) for point in ring if len(point) >= 2]
    if len(coords) < 3:
        return []
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _arcgis_rings_to_geom(rings: list[list[list[float]]]) -> BaseGeometry | None:
    outers: list[list[tuple[float, float]]] = []
    holes_by_outer: list[list[list[tuple[float, float]]]] = []

    for ring in rings:
        coords = _ring_to_coords(ring)
        if not coords:
            continue
        # ArcGIS polygon rings commonly use clockwise exteriors. If a service
        # flips winding, make_valid below still protects the final geometry.
        if _signed_area(coords) < 0:
            outers.append(coords)
            holes_by_outer.append([])
        elif outers:
            holes_by_outer[-1].append(coords)
        else:
            outers.append(coords)
            holes_by_outer.append([])

    polygons: list[Polygon] = []
    for outer, holes in zip(outers, holes_by_outer):
        try:
            polygon = Polygon(outer, holes)
        except ValueError:
            continue
        if not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return None

    geom: BaseGeometry
    if len(polygons) == 1:
        geom = polygons[0]
    else:
        geom = MultiPolygon(polygons)
    geom = make_valid(geom)
    if geom.is_empty:
        return None
    return geom


def _feature_geom(feature: dict[str, Any]) -> BaseGeometry | None:
    geometry = feature.get("geometry") or {}
    rings = geometry.get("rings")
    if not rings:
        return None
    return _arcgis_rings_to_geom(rings)


def _geom_hash(geom: BaseGeometry) -> str:
    return hashlib.sha256(wkb_dumps(geom, hex=False, srid=4326)).hexdigest()


def _parcel_raw(props: dict[str, Any], county: CountyConfig) -> dict[str, Any]:
    raw = {key: value for key, value in props.items() if value not in (None, "")}
    raw["_op5_source"] = "Colorado Public Parcels statewide layer"
    raw["_op5_source_url"] = CO_PUBLIC_PARCELS_LAYER
    raw["_op5_county_filter"] = county.where
    raw["_op5_county_jurisdiction"] = county.name
    raw["_op5_ingested_at"] = _now_iso()
    return raw


def _parcel_row(
    feature: dict[str, Any],
    county: CountyConfig,
    jurisdiction_id: str,
) -> tuple[Any, ...] | None:
    props = feature.get("attributes") or feature.get("properties") or {}
    geom = _feature_geom(feature)
    if geom is None:
        return None

    apn = _trim(props.get("parcel_id")) or _trim(props.get("account"))
    if not apn:
        return None

    acres = _numeric(props.get("landAcres"))
    if acres is None:
        sqft = _numeric(props.get("landSqft"))
        acres = (sqft / Decimal("43560")) if sqft is not None else None

    # Keep parcel-source zoning in raw only. Authoritative zoning is populated
    # from the per-muni zoning layers below.
    return (
        jurisdiction_id,
        apn,
        _trim(props.get("situsAdd")),
        _title_city(props.get("sitAddCty")),
        _trim(props.get("owner")),
        acres,
        None,
        _trim(props.get("landUseCde")),
        None,
        _numeric(props.get("apprValTot")) or _numeric(props.get("asedValTot")),
        _residential_hint(props),
        None,
        _trim(props.get("URL")),
        geom.wkt,
        json.dumps(_parcel_raw(props, county), sort_keys=True),
    )


def _zoning_raw(
    props: dict[str, Any],
    muni: MuniConfig,
    source: ZoningSourceConfig,
) -> dict[str, Any]:
    raw = {key: value for key, value in props.items() if value not in (None, "")}
    raw["_op5_source"] = source.name
    raw["_op5_source_url"] = source.layer_url
    raw["_op5_source_filter"] = source.where
    raw["_op5_source_scope_note"] = muni.source_scope_note
    raw["muni_name"] = muni.name
    raw["prod_city_value"] = muni.prod_city_value
    raw["county"] = muni.county
    raw["_op5_ingested_at"] = _now_iso()
    return raw


def _zone_row(feature: dict[str, Any], muni: MuniConfig) -> tuple[Any, ...] | None:
    props = feature.get("attributes") or feature.get("properties") or {}
    source = muni.zoning
    geom = _feature_geom(feature)
    if geom is None:
        return None

    code = _trim(props.get(source.zone_code_field))
    if not code:
        return None
    zone_name = _trim(props.get(source.zone_name_field)) if source.zone_name_field else None
    zone_class = _trim(props.get(source.zone_class_field)) if source.zone_class_field else None
    return (
        code,
        zone_name,
        zone_class,
        geom.wkt,
        json.dumps(_zoning_raw(props, muni, source), sort_keys=True),
        _geom_hash(geom),
    )


async def _request_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, 6):
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise RuntimeError(f"ArcGIS error from {url}: {data['error']}")
            return data
        except Exception as exc:  # noqa: BLE001 - retry transport and ArcGIS payload failures.
            last_error = exc
            if attempt == 5:
                break
            await asyncio.sleep(min(2**attempt, 15))
    raise RuntimeError(f"ArcGIS request failed after retries: {last_error}") from last_error


async def _fetch_count(
    client: httpx.AsyncClient,
    layer_url: str,
    where: str,
) -> int | None:
    try:
        data = await _request_json(
            client,
            f"{layer_url}/query",
            {
                "f": "json",
                "where": where,
                "returnCountOnly": "true",
            },
        )
        count = data.get("count")
        return int(count) if count is not None else None
    except Exception as exc:  # noqa: BLE001 - count is informative only.
        print(f"warn: count failed for {layer_url} where {where!r}: {exc}")
        return None


async def _fetch_page(
    client: httpx.AsyncClient,
    layer_url: str,
    where: str,
    *,
    offset: int,
    page_size: int,
    object_id_field: str,
    out_fields: str = "*",
) -> list[dict[str, Any]]:
    data = await _request_json(
        client,
        f"{layer_url}/query",
        {
            "f": "json",
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": "4326",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "orderByFields": object_id_field,
        },
    )
    return list(data.get("features") or [])


async def _iter_features(
    client: httpx.AsyncClient,
    layer_url: str,
    where: str,
    *,
    object_id_field: str,
    page_size: int = PAGE_SIZE,
    limit: int | None = None,
) -> AsyncIterator[list[dict[str, Any]]]:
    emitted = 0
    offset = 0
    while True:
        if limit is not None and emitted >= limit:
            return
        current_page_size = page_size
        if limit is not None:
            current_page_size = min(current_page_size, limit - emitted)
        page = await _fetch_page(
            client,
            layer_url,
            where,
            offset=offset,
            page_size=current_page_size,
            object_id_field=object_id_field,
        )
        if not page:
            return
        emitted += len(page)
        yield page
        if len(page) < current_page_size:
            return
        offset += len(page)


async def _register_or_get_jurisdiction(
    conn: asyncpg.Connection,
    *,
    name: str,
    county: str,
    parcel_endpoint: str | None,
    zoning_endpoint: str | None,
    coverage_level: str,
) -> str:
    existing = await conn.fetchrow(
        """
        SELECT id
        FROM jurisdictions
        WHERE name = $1 AND state = $2 AND county = $3
        ORDER BY id ASC
        LIMIT 1
        """,
        name,
        STATE,
        county,
    )
    if existing:
        jid = str(existing["id"])
        await conn.execute(
            """
            UPDATE jurisdictions
            SET
                parcel_source = COALESCE($2::parcel_source_enum, parcel_source),
                parcel_endpoint = COALESCE($3, parcel_endpoint),
                zoning_endpoint = COALESCE($4, zoning_endpoint),
                coverage_level = COALESCE($5::coverage_level_enum, coverage_level)
            WHERE id = $1::uuid
            """,
            jid,
            "county_gis",
            parcel_endpoint,
            zoning_endpoint,
            coverage_level,
        )
        print(f"registered existing jurisdiction {name}: {jid}")
        return jid

    jid = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO jurisdictions (
            id,
            name,
            state,
            county,
            parcel_source,
            parcel_endpoint,
            zoning_endpoint,
            coverage_level,
            created_at
        )
        VALUES (
            $1::uuid,
            $2,
            $3,
            $4,
            $5::parcel_source_enum,
            $6,
            $7,
            $8::coverage_level_enum,
            NOW()
        )
        """,
        jid,
        name,
        STATE,
        county,
        "county_gis",
        parcel_endpoint,
        zoning_endpoint,
        coverage_level,
    )
    print(f"registered new jurisdiction {name}: {jid}")
    return jid


async def _copy_upsert_parcels(conn: asyncpg.Connection, records: list[tuple[Any, ...]]) -> int:
    if not records:
        return 0
    await conn.execute(_CREATE_STAGE_SQL)
    await conn.execute(_TRUNCATE_STAGE_SQL)
    await conn.copy_records_to_table(
        "_stage_parcels",
        records=records,
        columns=[
            "jurisdiction_id",
            "apn",
            "address",
            "city",
            "owner_name",
            "acres",
            "zoning_code",
            "land_use_code",
            "improvement_value",
            "assessed_value",
            "is_residential",
            "has_structure",
            "county_link",
            "geom_wkt",
            "raw_json",
        ],
    )
    return int(await conn.fetchval(_MERGE_PARCELS_SQL))


async def _ingest_county_parcels(
    conn: asyncpg.Connection,
    client: httpx.AsyncClient,
    county: CountyConfig,
    jurisdiction_id: str,
) -> int:
    count = await _fetch_count(client, CO_PUBLIC_PARCELS_LAYER, county.where)
    if count is None:
        print(f"parcel ingest {county.name}: count unavailable; streaming until empty")
    else:
        print(f"parcel ingest {county.name}: source count {count:,}")

    total = 0
    pending: list[tuple[Any, ...]] = []
    async for page in _iter_features(
        client,
        CO_PUBLIC_PARCELS_LAYER,
        county.where,
        object_id_field="OBJECTID",
    ):
        for feature in page:
            row = _parcel_row(feature, county, jurisdiction_id)
            if row:
                pending.append(row)
            if len(pending) >= BATCH_SIZE:
                total += await _copy_upsert_parcels(conn, pending)
                print(f"parcel ingest {county.name}: upserted {total:,}")
                pending = []

    if pending:
        total += await _copy_upsert_parcels(conn, pending)
    print(f"parcel ingest {county.name}: final upserted {total:,}")
    return total


async def _move_muni_parcels(
    conn: asyncpg.Connection,
    *,
    parent_jid: str,
    muni_jid: str,
    muni: MuniConfig,
) -> dict[str, int]:
    raw_city_values = list(muni.raw_city_values)
    merged_existing = await conn.fetchval(
        """
        WITH source_rows AS (
            SELECT src.*
            FROM parcels src
            WHERE src.jurisdiction_id = $1::uuid
              AND (
                  src.city = $3
                  OR src.raw->>'sitAddCty' = ANY($4::text[])
              )
        ),
        updated_existing AS (
            UPDATE parcels target
            SET
                address = source_rows.address,
                city = $3,
                state = $5,
                owner_name = source_rows.owner_name,
                acres = source_rows.acres,
                land_use_code = source_rows.land_use_code,
                improvement_value = source_rows.improvement_value,
                assessed_value = source_rows.assessed_value,
                is_residential = source_rows.is_residential,
                has_structure = source_rows.has_structure,
                county_link = source_rows.county_link,
                geom = source_rows.geom,
                centroid = source_rows.centroid,
                raw = source_rows.raw,
                updated_at = NOW()
            FROM source_rows
            WHERE target.jurisdiction_id = $2::uuid
              AND target.apn = source_rows.apn
            RETURNING source_rows.id
        ),
        deleted_source_duplicates AS (
            DELETE FROM parcels src
            USING updated_existing
            WHERE src.id = updated_existing.id
            RETURNING 1
        )
        SELECT COUNT(*)::INTEGER FROM deleted_source_duplicates
        """,
        parent_jid,
        muni_jid,
        muni.prod_city_value,
        raw_city_values,
        STATE,
    )
    moved = await conn.fetchval(
        """
        WITH moved AS (
            UPDATE parcels src
            SET
                jurisdiction_id = $2::uuid,
                city = $3,
                state = $5,
                updated_at = NOW()
            WHERE src.jurisdiction_id = $1::uuid
              AND (
                  src.city = $3
                  OR src.raw->>'sitAddCty' = ANY($4::text[])
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM parcels existing
                  WHERE existing.jurisdiction_id = $2::uuid
                    AND existing.apn = src.apn
              )
            RETURNING 1
        )
        SELECT COUNT(*)::INTEGER FROM moved
        """,
        parent_jid,
        muni_jid,
        muni.prod_city_value,
        raw_city_values,
        STATE,
    )
    print(
        f"PATH 1 move {muni.name}: moved {moved:,}; "
        f"merged duplicate rerun rows {merged_existing:,}"
    )
    if int(moved) == 0 and int(merged_existing) == 0:
        raise RuntimeError(
            f"{muni.name}: zero parcels matched city={muni.prod_city_value!r} "
            f"or raw sitAddCty values={raw_city_values!r}; refusing zoning ingest"
        )
    return {"moved": int(moved), "merged_existing": int(merged_existing)}


async def _insert_zoning(
    conn: asyncpg.Connection,
    jurisdiction_id: str,
    row: tuple[Any, ...],
) -> int:
    code, zone_name, zone_class, geom_wkt, raw_json, geom_hash = row
    return int(
        await conn.fetchval(
            _INSERT_ZONING_SQL,
            jurisdiction_id,
            code,
            zone_name,
            zone_class,
            geom_wkt,
            raw_json,
            geom_hash,
        )
    )


async def _ingest_muni_zoning(
    conn: asyncpg.Connection,
    client: httpx.AsyncClient,
    muni: MuniConfig,
    jurisdiction_id: str,
) -> int:
    source = muni.zoning
    count = await _fetch_count(client, source.layer_url, source.where)
    if count is None:
        print(f"zoning ingest {muni.name}: count unavailable; streaming until empty")
    else:
        print(f"zoning ingest {muni.name}: source count {count:,}")

    total = 0
    async for page in _iter_features(
        client,
        source.layer_url,
        source.where,
        object_id_field=source.object_id_field,
    ):
        for feature in page:
            row = _zone_row(feature, muni)
            if not row:
                continue
            total += await _insert_zoning(conn, jurisdiction_id, row)
        print(f"zoning ingest {muni.name}: upserted {total:,}")
    return total


async def _backfill_muni_zoning(
    conn: asyncpg.Connection,
    *,
    jurisdiction_id: str,
    muni: MuniConfig,
) -> dict[str, int]:
    contained = int(
        await conn.fetchval(_BACKFILL_CONTAINED_SQL, jurisdiction_id, muni.name)
    )
    nearest = int(
        await conn.fetchval(_BACKFILL_NEAREST_SQL, jurisdiction_id, muni.name)
    )
    print(f"zoning backfill {muni.name}: contained {contained:,}; nearest_50m {nearest:,}")
    return {"contained": contained, "nearest_50m": nearest}


async def _prune_muni_zoning(
    conn: asyncpg.Connection,
    *,
    jurisdiction_id: str,
    muni: MuniConfig,
) -> int:
    deleted = int(
        await conn.fetchval(_PRUNE_NON_MUNI_ZONING_SQL, jurisdiction_id, muni.name)
    )
    print(f"zoning prune {muni.name}: removed {deleted:,} non-overlapping districts")
    return deleted


async def _update_bbox(conn: asyncpg.Connection, jurisdiction_id: str, name: str) -> None:
    bbox = await conn.fetchrow(
        """
        WITH extent AS (
            SELECT ST_Extent(geom) AS box
            FROM parcels
            WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
        )
        SELECT
            ST_XMin(box::geometry) AS min_lng,
            ST_YMin(box::geometry) AS min_lat,
            ST_XMax(box::geometry) AS max_lng,
            ST_YMax(box::geometry) AS max_lat
        FROM extent
        WHERE box IS NOT NULL
        """,
        jurisdiction_id,
    )
    if not bbox:
        print(f"bbox {name}: skipped; no parcel geometry")
        return

    value = [
        float(bbox["min_lng"]),
        float(bbox["min_lat"]),
        float(bbox["max_lng"]),
        float(bbox["max_lat"]),
    ]
    await conn.execute(
        """
        UPDATE jurisdictions
        SET bbox = $2::jsonb
        WHERE id = $1::uuid
        """,
        jurisdiction_id,
        json.dumps(value),
    )
    print(f"bbox {name}: {value}")


async def _preflight(args: argparse.Namespace) -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        print("CO Front Range carry preflight", flush=True)
        print("parcel source:", CO_PUBLIC_PARCELS_LAYER, flush=True)
        for county in COUNTIES:
            count = None
            if args.with_counts:
                count = await _fetch_count(client, CO_PUBLIC_PARCELS_LAYER, county.where)
            sample_rows = 0
            sample_cities: dict[str, int] = {}
            async for page in _iter_features(
                client,
                CO_PUBLIC_PARCELS_LAYER,
                county.where,
                object_id_field="OBJECTID",
                limit=args.sample_size,
            ):
                for feature in page:
                    props = feature.get("attributes") or feature.get("properties") or {}
                    city = _title_city(props.get("sitAddCty")) or "(blank)"
                    sample_cities[city] = sample_cities.get(city, 0) + 1
                    sample_rows += 1
            print(
                f"county {county.name}: count={count if count is not None else 'unavailable'} "
                f"sample_rows={sample_rows} sample_cities={sample_cities}"
                f"{' (count skipped)' if not args.with_counts else ''}",
                flush=True,
            )

        for muni in MUNIS:
            source = muni.zoning
            count = None
            if args.with_counts:
                count = await _fetch_count(client, source.layer_url, source.where)
            zone_codes: dict[str, int] = {}
            sample_rows = 0
            async for page in _iter_features(
                client,
                source.layer_url,
                source.where,
                object_id_field=source.object_id_field,
                limit=args.sample_size,
            ):
                for feature in page:
                    props = feature.get("attributes") or feature.get("properties") or {}
                    code = _trim(props.get(source.zone_code_field)) or "(blank)"
                    zone_codes[code] = zone_codes.get(code, 0) + 1
                    sample_rows += 1
            print(
                f"zoning {muni.name}: source={source.name} "
                f"count={count if count is not None else 'unavailable'} "
                f"sample_rows={sample_rows} sample_zone_codes={zone_codes}"
                f"{' (count skipped)' if not args.with_counts else ''}",
                flush=True,
            )


async def _fire(args: argparse.Namespace) -> None:
    if not args.i_know_this_writes_to_prod:
        raise SystemExit("Refusing to run without --i-know-this-writes-to-prod")

    conn = await asyncpg.connect(_session_db_url())
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            async with conn.transaction():
                await conn.execute("SET LOCAL statement_timeout = 0;")
                await conn.execute(_CREATE_STAGE_SQL)

                county_jids: dict[str, str] = {}
                muni_jids: dict[str, str] = {}

                print("starting CO Front Range carry transaction")
                for county in COUNTIES:
                    county_jids[county.name] = await _register_or_get_jurisdiction(
                        conn,
                        name=county.name,
                        county=county.county,
                        parcel_endpoint=CO_PUBLIC_PARCELS_LAYER,
                        zoning_endpoint=None,
                        coverage_level="parcels_only",
                    )

                for muni in MUNIS:
                    muni_jids[muni.name] = await _register_or_get_jurisdiction(
                        conn,
                        name=muni.name,
                        county=muni.county,
                        parcel_endpoint=CO_PUBLIC_PARCELS_LAYER,
                        zoning_endpoint=muni.zoning.layer_url,
                        coverage_level="full",
                    )

                parcel_totals: dict[str, int] = {}
                for county in COUNTIES:
                    parcel_totals[county.name] = await _ingest_county_parcels(
                        conn,
                        client,
                        county,
                        county_jids[county.name],
                    )

                move_totals: dict[str, dict[str, int]] = {}
                zoning_totals: dict[str, int] = {}
                prune_totals: dict[str, int] = {}
                backfill_totals: dict[str, dict[str, int]] = {}
                for muni in MUNIS:
                    move_totals[muni.name] = await _move_muni_parcels(
                        conn,
                        parent_jid=county_jids[muni.parent_county_name],
                        muni_jid=muni_jids[muni.name],
                        muni=muni,
                    )
                    zoning_totals[muni.name] = await _ingest_muni_zoning(
                        conn,
                        client,
                        muni,
                        muni_jids[muni.name],
                    )
                    prune_totals[muni.name] = await _prune_muni_zoning(
                        conn,
                        jurisdiction_id=muni_jids[muni.name],
                        muni=muni,
                    )
                    backfill_totals[muni.name] = await _backfill_muni_zoning(
                        conn,
                        jurisdiction_id=muni_jids[muni.name],
                        muni=muni,
                    )

                for county in COUNTIES:
                    await _update_bbox(conn, county_jids[county.name], county.name)
                for muni in MUNIS:
                    await _update_bbox(conn, muni_jids[muni.name], muni.name)

                print("carry transaction summary")
                print("county_jids:", county_jids)
                print("muni_jids:", muni_jids)
                print("parcel_totals:", parcel_totals)
                print("move_totals:", move_totals)
                print("zoning_totals:", zoning_totals)
                print("prune_totals:", prune_totals)
                print("backfill_totals:", backfill_totals)
                print("NO downstream refresh fired by this script")
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PREP-only CO Front Range statewide multi-county carry adapter",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser(
        "preflight",
        help="Read-only source probe; no database writes",
    )
    preflight.add_argument("--sample-size", type=int, default=50)
    preflight.add_argument(
        "--with-counts",
        action="store_true",
        help=(
            "Also request ArcGIS counts. Default skips counts because the "
            "CO statewide service is flaky."
        ),
    )
    preflight.set_defaults(func=_preflight)

    fire = subparsers.add_parser(
        "fire",
        help="Run the guarded production write carry. Do not run during prep.",
    )
    fire.add_argument("--i-know-this-writes-to-prod", action="store_true")
    fire.set_defaults(func=_fire)

    return parser


async def _main_async() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    await args.func(args)


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
