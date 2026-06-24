"""Phase 6 expansion PREP - Summit UT Snyderville/Promontory adapter.

PREP ONLY. Do not fire without explicit Master approval.

Source path, per PR #344 diagnostic and the Phase 6 follow-up:
  - Parcels: UT AGRC Summit County parcels
    https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Summit_LIR/FeatureServer/0
  - Zoning: Summit County Zoning_Service FeatureServer
    layer 2: Snyderville Basin Planning District
    layer 3: Eastern Summit County Planning District
    https://services2.arcgis.com/gyfpgFh2Wj2gglYD/arcgis/rest/services/Zoning_Service/FeatureServer

Scope:
  - This is NOT Park City proper. Park City city zoning is already a separate
    loaded/operational subset.
  - Target rows are AGRC Summit parcels whose centroids fall inside the union
    of Summit County layer 2 + layer 3 zoning polygons.
  - Registers a Summit County umbrella JID plus a sub-region per-muni JID:
    "Snyderville/Promontory, UT".

Idempotency:
  - Full write path is wrapped in one transaction.
  - Jurisdictions are registered/updated.
  - Parcels are staged and upserted on (jurisdiction_id, apn).
  - Existing zoning_districts for the sub-region JID are delete-then-inserted.
  - Parcel zoning bindings for the sub-region JID are reset before spatial
    backfill runs.
  - --dry-run runs the full transaction and rolls back.

Default invocation refuses. Use --preflight for source-only validation.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import dotenv
import httpx
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.wkb import dumps as wkb_dumps

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("summit_ut_snyderville")

UMBRELLA_JURISDICTION_NAME = "Summit County, UT"
JURISDICTION_NAME = "Snyderville/Promontory, UT"
JURISDICTION_STATE = "UT"
JURISDICTION_COUNTY = "Summit"
MUNI_NAME = "Snyderville/Promontory"
PROD_CITY_VALUE = "Snyderville/Promontory"

PARCEL_LAYER = (
    "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/"
    "Parcels_Summit_LIR/FeatureServer/0"
)
ZONING_BASE = (
    "https://services2.arcgis.com/gyfpgFh2Wj2gglYD/arcgis/rest/services/"
    "Zoning_Service/FeatureServer"
)
ZONING_LAYERS = [
    {
        "name": "Snyderville Basin Planning District",
        "layer": f"{ZONING_BASE}/2",
        "order_field": "OBJECTID",
        "code_field": "Zone_Abbre",
        "name_fields": ("Description", "Zone_"),
    },
    {
        "name": "Eastern Summit County Planning District",
        "layer": f"{ZONING_BASE}/3",
        "order_field": "OBJECTID_1",
        "code_field": "Label",
        "name_fields": ("DESCRIPTIO", "Label"),
    },
]
ORDINANCE_URL = "https://ut-summitcounty2.civicplus.com/2583/Summit-County-Code"

PARCEL_WHERE = "1=1"
PAGE_SIZE = 2000
SOURCE_DATE = "2026-06-24"
NEAREST_FALLBACK_METERS = 50.0

# Loose Summit County sanity envelope. East edge runs to the UT-WY border
# (~-110.00) because the Eastern Summit County Planning District reaches it.
BBOX_LON = (-111.85, -109.95)
BBOX_LAT = (40.45, 41.30)

_STAGE_COLUMNS = [
    "jurisdiction_id", "apn", "address", "city", "owner_name",
    "zoning_code", "zone_class", "land_use_code", "acres",
    "county_link", "in_flood_zone", "in_wetland", "avg_slope_pct",
    "has_structure", "improvement_value", "assessed_value",
    "is_residential", "geom_wkb", "centroid_wkb", "raw_json",
]

_CREATE_PARCEL_STAGE_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _stage_summit_snyderville_parcels (
    jurisdiction_id uuid, apn text, address text, city text,
    owner_name text, zoning_code text, zone_class text,
    land_use_code text, acres double precision, county_link text,
    in_flood_zone boolean, in_wetland boolean, avg_slope_pct double precision,
    has_structure boolean, improvement_value double precision,
    assessed_value double precision, is_residential boolean,
    geom_wkb bytea, centroid_wkb bytea, raw_json text
)
"""

_MERGE_PARCELS_SQL = """
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
FROM _stage_summit_snyderville_parcels s
ON CONFLICT ON CONSTRAINT uq_parcels_jurisdiction_apn DO UPDATE SET
    address = EXCLUDED.address,
    city = EXCLUDED.city,
    state = 'UT',
    owner_name = EXCLUDED.owner_name,
    land_use_code = EXCLUDED.land_use_code,
    acres = EXCLUDED.acres,
    has_structure = EXCLUDED.has_structure,
    improvement_value = EXCLUDED.improvement_value,
    assessed_value = EXCLUDED.assessed_value,
    is_residential = EXCLUDED.is_residential,
    geom = EXCLUDED.geom,
    centroid = EXCLUDED.centroid,
    raw = EXCLUDED.raw,
    updated_at = NOW()
"""

_CREATE_ZONING_STAGE_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _stage_summit_snyderville_zoning (
    zone_code text,
    zone_name text,
    zone_class text,
    geom_wkb bytea,
    raw_json text
)
"""


def _session_db_url() -> str:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL not set in environment")
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_structure(attrs: dict[str, Any]) -> bool | None:
    sqft = _float(attrs.get("BLDG_SQFT"))
    houses = _float(attrs.get("HOUSE_CNT"))
    if sqft is not None:
        return sqft > 0
    if houses is not None:
        return houses > 0
    return None


def _is_residential(attrs: dict[str, Any]) -> bool | None:
    prop_class = (attrs.get("PROP_CLASS") or "").upper()
    primary = (attrs.get("PRIMARY_RES") or "").upper()
    if primary == "Y" or "RESIDENTIAL" in prop_class:
        return True
    if any(token in prop_class for token in ("COMMERCIAL", "INDUSTRIAL", "AGRICULTURAL")):
        return False
    return None


def _base_apn(attrs: dict[str, Any]) -> str | None:
    return (
        _text(attrs.get("SERIAL_NUM"))
        or _text(attrs.get("PARCEL_ID"))
        or (f"OBJECTID:{attrs.get('OBJECTID')}" if attrs.get("OBJECTID") is not None else None)
    )


def _deduped_apn(attrs: dict[str, Any], seen_apns: set[str]) -> str | None:
    base = _base_apn(attrs)
    if not base:
        return None
    if base not in seen_apns:
        return base
    object_id = attrs.get("OBJECTID")
    if object_id is None:
        return None
    return f"{base}:OBJECTID:{object_id}"


def _zone_class(zone: str, name: str | None = None) -> str:
    z = zone.strip().upper()
    n = (name or "").upper()
    if z in {"RR", "MR"} or "RESIDENTIAL" in n:
        return "residential"
    if z.startswith("AG"):
        return "agricultural"
    if z in {"INDUS", "LI"} or "INDUSTRIAL" in n:
        return "industrial"
    if z in {"TC", "RC"} or "RESORT" in n or "TOWN CENTER" in n:
        return "mixed_use"
    if z in {"CC", "NC", "C"} or "COMMERCIAL" in n:
        return "commercial"
    if z in {"HS", "SC"}:
        return "special"
    return "unknown"


def _polygonal(geom: Any) -> Polygon | MultiPolygon:
    fixed = make_valid(geom)
    if isinstance(fixed, (Polygon, MultiPolygon)):
        return fixed
    if isinstance(fixed, GeometryCollection):
        polys: list[Polygon] = []
        for part in fixed.geoms:
            if isinstance(part, Polygon):
                polys.append(part)
            elif isinstance(part, MultiPolygon):
                polys.extend(list(part.geoms))
        if polys:
            return MultiPolygon(polys)
    raise ValueError(f"geometry is not polygonal after make_valid: {fixed.geom_type}")


async def _fetch_count(client: httpx.AsyncClient, layer: str, where: str) -> int:
    r = await client.get(
        f"{layer}/query",
        params={"where": where, "returnCountOnly": "true", "f": "json"},
    )
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return int(payload.get("count") or 0)


async def _fetch_geojson_features(
    client: httpx.AsyncClient,
    layer: str,
    where: str,
    *,
    order_field: str,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        r = await client.get(
            f"{layer}/query",
            params={
                "where": where,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "orderByFields": order_field,
            },
            timeout=240.0,
        )
        r.raise_for_status()
        payload = r.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info("fetched %s offset=%d batch=%d total=%d", layer, offset, len(batch), len(features))
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return features


async def _fetch_sources() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with httpx.AsyncClient(timeout=240.0) as client:
        parcel_count = await _fetch_count(client, PARCEL_LAYER, PARCEL_WHERE)
        print(f"[source] AGRC Summit parcel count: {parcel_count:,}")
        zoning_features: list[dict[str, Any]] = []
        for layer in ZONING_LAYERS:
            count = await _fetch_count(client, layer["layer"], "1=1")
            print(f"[source] {layer['name']} zoning count: {count:,}")
            feats = await _fetch_geojson_features(
                client,
                layer["layer"],
                "1=1",
                order_field=layer["order_field"],
            )
            for feat in feats:
                feat["_summit_layer"] = layer
            zoning_features.extend(feats)
        parcel_features = await _fetch_geojson_features(
            client,
            PARCEL_LAYER,
            PARCEL_WHERE,
            order_field="OBJECTID",
        )
    return parcel_features, zoning_features


def _zoning_geom_union(zoning_features: list[dict[str, Any]]) -> Polygon | MultiPolygon:
    geoms = []
    for feature in zoning_features:
        geom_json = feature.get("geometry")
        if not geom_json:
            continue
        geoms.append(_polygonal(shape(geom_json)))
    if not geoms:
        raise RuntimeError("no Summit zoning geometry fetched")
    return _polygonal(unary_union(geoms))


def _filter_target_parcels(
    parcel_features: list[dict[str, Any]],
    zoning_features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    target_union = _zoning_geom_union(zoning_features)
    target = prep(target_union)
    selected: list[dict[str, Any]] = []
    skipped = 0
    for feature in parcel_features:
        geom_json = feature.get("geometry")
        if not geom_json:
            skipped += 1
            continue
        try:
            geom = _polygonal(shape(geom_json))
        except Exception:
            skipped += 1
            continue
        if target.covers(geom.centroid):
            selected.append(feature)
    if skipped:
        print(f"[parcels] skipped {skipped} parcel rows with missing/invalid geometry during target filter")
    return selected


def _parcel_rows(features: list[dict[str, Any]], jid: str) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    skipped = 0
    seen_apns: set[str] = set()
    for feature in features:
        attrs = feature.get("properties") or {}
        # AGRC PARCEL_ID is public-facing but duplicates inside the Summit
        # target slice. SERIAL_NUM is cleaner where present; OBJECTID suffixes
        # keep duplicate condominium/edge rows idempotent instead of dropping
        # target polygons.
        apn = _deduped_apn(attrs, seen_apns)
        geom_json = feature.get("geometry")
        if not apn or not geom_json:
            skipped += 1
            continue
        if apn in seen_apns:
            logger.warning("skip duplicate parcel key apn=%s SERIAL_NUM=%s", apn, attrs.get("SERIAL_NUM"))
            skipped += 1
            continue
        seen_apns.add(apn)
        try:
            geom = _polygonal(shape(geom_json))
        except Exception as exc:
            logger.warning("skip parcel PARCEL_ID=%s: %s", apn, exc)
            skipped += 1
            continue

        raw = {
            "source_url": PARCEL_LAYER,
            "source_filter": PARCEL_WHERE,
            "source_kind": "arcgis_feature_server",
            "ingested_at": SOURCE_DATE,
            "muni_name": MUNI_NAME,
            "muni_type": "subregion",
            "publisher": "UT AGRC Parcels_Summit_LIR",
            "target_scope": "Summit County zoning layers 2/3 centroid filter",
            **attrs,
        }
        centroid = geom.centroid
        rows.append((
            jid,
            apn,
            _text(attrs.get("PARCEL_ADD")),
            PROD_CITY_VALUE,
            None,
            None,
            None,
            _text(attrs.get("PROP_CLASS")),
            _float(attrs.get("PARCEL_ACRES")),
            None,
            False,
            False,
            None,
            _bool_structure(attrs),
            _float(attrs.get("BLDG_SQFT")),
            _float(attrs.get("TOTAL_MKT_VALUE")),
            _is_residential(attrs),
            wkb_dumps(geom, hex=False, srid=4326),
            wkb_dumps(centroid, hex=False, srid=4326),
            json.dumps(raw),
        ))
    if skipped:
        print(f"[parcels] skipped {skipped} target rows with missing key/geometry")
    return rows


def _zoning_rows(features: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    skipped = 0
    for feature in features:
        attrs = feature.get("properties") or {}
        layer = feature.get("_summit_layer") or {}
        code_field = layer.get("code_field")
        zone = _text(attrs.get(code_field))
        geom_json = feature.get("geometry")
        if not zone or not geom_json:
            skipped += 1
            continue
        zone_name = None
        for name_field in layer.get("name_fields", ()):
            zone_name = _text(attrs.get(name_field))
            if zone_name:
                break
        zone_name = zone_name or zone
        try:
            geom = _polygonal(shape(geom_json))
        except Exception as exc:
            logger.warning("skip zoning layer=%s code=%s: %s", layer.get("name"), zone, exc)
            skipped += 1
            continue
        raw = {
            "source_url": layer.get("layer"),
            "source_kind": "arcgis_feature_server",
            "source_layer": layer.get("name"),
            "ingested_at": SOURCE_DATE,
            "muni_name": MUNI_NAME,
            "muni_type": "subregion",
            "publisher": "Summit County Zoning_Service",
            **attrs,
        }
        rows.append((
            zone,
            zone_name,
            _zone_class(zone, zone_name),
            wkb_dumps(geom, hex=False, srid=4326),
            json.dumps(raw),
        ))
    if skipped:
        print(f"[zoning] skipped {skipped} rows with missing zone/geometry")
    return rows


async def _register_jurisdictions(conn: asyncpg.Connection) -> str:
    umbrella = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        UMBRELLA_JURISDICTION_NAME,
        JURISDICTION_STATE,
    )
    if umbrella:
        await conn.execute(
            """
            UPDATE jurisdictions
               SET county=$2,
                   parcel_source='county_gis'::parcel_source_enum,
                   parcel_endpoint=$3,
                   zoning_endpoint=$4,
                   ordinance_url=$5,
                   coverage_level='partial'::coverage_level_enum
             WHERE id=$1::uuid
            """,
            str(umbrella),
            JURISDICTION_COUNTY,
            PARCEL_LAYER,
            ZONING_BASE,
            ORDINANCE_URL,
        )
        print(f"[jurisdiction] found/updated umbrella {UMBRELLA_JURISDICTION_NAME}: {umbrella}")
    else:
        umbrella = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO jurisdictions (
                id, name, state, county, parcel_source, parcel_endpoint,
                zoning_endpoint, ordinance_url, coverage_level
            )
            VALUES (
                $1::uuid, $2, $3, $4, 'county_gis'::parcel_source_enum,
                $5, $6, $7, 'partial'::coverage_level_enum
            )
            """,
            str(umbrella),
            UMBRELLA_JURISDICTION_NAME,
            JURISDICTION_STATE,
            JURISDICTION_COUNTY,
            PARCEL_LAYER,
            ZONING_BASE,
            ORDINANCE_URL,
        )
        print(f"[jurisdiction] registered umbrella {UMBRELLA_JURISDICTION_NAME}: {umbrella}")

    jid = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        JURISDICTION_NAME,
        JURISDICTION_STATE,
    )
    if jid:
        await conn.execute(
            """
            UPDATE jurisdictions
               SET county=$2,
                   parcel_source='county_gis'::parcel_source_enum,
                   parcel_endpoint=$3,
                   zoning_endpoint=$4,
                   ordinance_url=$5,
                   coverage_level='partial'::coverage_level_enum
             WHERE id=$1::uuid
            """,
            str(jid),
            JURISDICTION_COUNTY,
            PARCEL_LAYER,
            ZONING_BASE,
            ORDINANCE_URL,
        )
        print(f"[jurisdiction] found/updated {JURISDICTION_NAME}: {jid}")
        return str(jid)

    jid = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO jurisdictions (
            id, name, state, county, parcel_source, parcel_endpoint,
            zoning_endpoint, ordinance_url, coverage_level
        )
        VALUES (
            $1::uuid, $2, $3, $4, 'county_gis'::parcel_source_enum,
            $5, $6, $7, 'partial'::coverage_level_enum
        )
        """,
        jid,
        JURISDICTION_NAME,
        JURISDICTION_STATE,
        JURISDICTION_COUNTY,
        PARCEL_LAYER,
        ZONING_BASE,
        ORDINANCE_URL,
    )
    print(f"[jurisdiction] registered {JURISDICTION_NAME}: {jid}")
    return jid


async def _stage_and_merge_parcels(
    conn: asyncpg.Connection,
    parcel_features: list[dict[str, Any]],
    jid: str,
) -> int:
    rows = _parcel_rows(parcel_features, jid)
    await conn.execute(_CREATE_PARCEL_STAGE_SQL)
    await conn.execute("TRUNCATE _stage_summit_snyderville_parcels")
    if rows:
        await conn.copy_records_to_table(
            "_stage_summit_snyderville_parcels",
            records=rows,
            columns=_STAGE_COLUMNS,
        )
        await conn.execute(_MERGE_PARCELS_SQL)
        await conn.execute(
            """
            UPDATE parcels
               SET city=$2,
                   state='UT',
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
    rows = _zoning_rows(zoning_features)
    await conn.execute(_CREATE_ZONING_STAGE_SQL)
    await conn.execute("TRUNCATE _stage_summit_snyderville_zoning")
    if rows:
        await conn.copy_records_to_table(
            "_stage_summit_snyderville_zoning",
            records=rows,
            columns=["zone_code", "zone_name", "zone_class", "geom_wkb", "raw_json"],
        )
        await conn.execute(
            """
            INSERT INTO zoning_districts (
                jurisdiction_id, zone_code, zone_name, zone_class,
                geom, raw_attributes, source
            )
            SELECT
                $1::uuid, zone_code, zone_name, zone_class::zone_class_enum,
                ST_Multi(ST_MakeValid(ST_GeomFromEWKB(geom_wkb))),
                raw_json::jsonb, 'arcgis'::zone_source_enum
            FROM _stage_summit_snyderville_zoning
            """,
            jid,
        )
    return len(rows)


async def _spatial_backfill(conn: asyncpg.Connection, jid: str) -> tuple[int, int, int]:
    await conn.execute(
        """
        UPDATE parcels
           SET zoning_code = NULL,
               zone_class = NULL,
               zone_binding_method = NULL
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    s1 = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class=sub.zone_class,
               zone_binding_method='contained',
               zoning_code=sub.zone_code,
               updated_at=NOW()
          FROM (
              SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                FROM parcels p
                JOIN LATERAL (
                    SELECT z.zone_class, z.zone_code
                      FROM zoning_districts z
                     WHERE z.jurisdiction_id=$1::uuid
                       AND z.geom IS NOT NULL
                       AND ST_Within(ST_Centroid(p.geom), z.geom)
                     ORDER BY z.id
                     LIMIT 1
                ) zd ON TRUE
               WHERE p.jurisdiction_id=$1::uuid AND p.geom IS NOT NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        jid,
    )
    contained = int(s1.split()[-1])

    label = f"nearest_{int(round(NEAREST_FALLBACK_METERS))}m"
    s2 = await conn.execute(
        """
        UPDATE parcels target
           SET zone_class=sub.zone_class,
               zone_binding_method=$2,
               zoning_code=sub.zone_code,
               updated_at=NOW()
          FROM (
              SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                FROM parcels p
                JOIN LATERAL (
                    SELECT z.zone_class, z.zone_code
                      FROM zoning_districts z
                     WHERE z.jurisdiction_id=$1::uuid
                       AND z.geom IS NOT NULL
                       AND ST_DWithin(z.geom::geography, ST_Centroid(p.geom)::geography, $3)
                     ORDER BY ST_Distance(z.geom::geography, ST_Centroid(p.geom)::geography), z.id
                     LIMIT 1
                ) zd ON TRUE
               WHERE p.jurisdiction_id=$1::uuid
                 AND p.geom IS NOT NULL
                 AND p.zone_binding_method IS NULL
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        jid,
        label,
        NEAREST_FALLBACK_METERS,
    )
    nearest = int(s2.split()[-1])
    unmatched = await conn.fetchval(
        """
        SELECT COUNT(*)
          FROM parcels
         WHERE jurisdiction_id=$1::uuid
           AND (zoning_code IS NULL OR btrim(zoning_code)='')
        """,
        jid,
    )
    return contained, nearest, int(unmatched)


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
        raise RuntimeError("no Summit target parcel geometry after ingest")
    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    if not (
        BBOX_LON[0] <= bbox[0] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]
        and BBOX_LON[0] <= bbox[2] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[3] <= BBOX_LAT[1]
    ):
        raise RuntimeError(f"bbox {bbox} outside Summit envelope lon={BBOX_LON} lat={BBOX_LAT}")
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid,
        json.dumps(bbox),
    )
    return bbox


async def _quality_report(conn: asyncpg.Connection, jid: str) -> None:
    p = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>'') AS bound,
               COUNT(*) FILTER (WHERE zone_binding_method='contained') AS contained,
               COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest,
               COUNT(*) FILTER (WHERE raw IS NULL OR raw='{}'::jsonb) AS empty_raw
          FROM parcels
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    d = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE raw_attributes IS NULL OR raw_attributes='{}'::jsonb) AS empty_raw,
               COUNT(DISTINCT zone_code) AS codes
          FROM zoning_districts
         WHERE jurisdiction_id=$1::uuid
        """,
        jid,
    )
    cov = 100.0 * p["bound"] / p["total"] if p["total"] else 0.0
    near_pct = 100.0 * p["nearest"] / p["total"] if p["total"] else 0.0
    print("\n=== 5-GATE PREP REPORT ===")
    print(f"GATE 1 parcel zoning coverage {cov:.1f}% (>=70%) - {'PASS' if cov >= 70 else 'SUB'}")
    print(f"GATE 2 nearest fallback {near_pct:.1f}%")
    print(f"GATE 3 parcel raw empty {p['empty_raw']} / zoning raw empty {d['empty_raw']}")
    print(f"GATE 4 zoning_district rows {d['total']} / distinct codes {d['codes']}")
    print("GATE 5 bbox populated inline")
    print(f"  parcels {p['total']:,} bound {p['bound']:,} contained {p['contained']:,} nearest {p['nearest']:,}")

    codes = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*) AS n
          FROM parcels
         WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
         GROUP BY 1
         ORDER BY 2 DESC, 1
        """,
        jid,
    )
    print(f"\nDistribution ({len(codes)}):")
    for row in codes:
        print(f"  {row['zoning_code']:12s} {row['n']:>6,}")


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Summit UT Snyderville/Promontory source shape ===\n")
    parcels, zoning = await _fetch_sources()
    target_parcels = _filter_target_parcels(parcels, zoning)
    zone_rows = _zoning_rows(zoning)
    parcel_props = [p.get("properties", {}) for p in target_parcels]
    parcel_ids = [_text(p.get("PARCEL_ID")) for p in parcel_props if _text(p.get("PARCEL_ID"))]
    serials = [_text(p.get("SERIAL_NUM")) for p in parcel_props if _text(p.get("SERIAL_NUM"))]
    seen_report_apns: set[str] = set()
    chosen_apns = []
    for props in parcel_props:
        apn = _deduped_apn(props, seen_report_apns)
        if apn:
            chosen_apns.append(apn)
            seen_report_apns.add(apn)
    zones = sorted({row[0] for row in zone_rows})
    print(f"all Summit parcels fetched: {len(parcels):,}")
    print(f"target centroid-filter parcels: {len(target_parcels):,}")
    print(f"target PARCEL_ID present: {len(parcel_ids):,}; unique PARCEL_ID: {len(set(parcel_ids)):,}")
    print(f"target SERIAL_NUM present: {len(serials):,}; unique SERIAL_NUM: {len(set(serials)):,}")
    print(f"chosen APN present: {len(chosen_apns):,}; unique chosen APN: {len(set(chosen_apns)):,}")
    print(f"zoning rows fetched: {len(zoning):,}")
    print(f"zoning distinct codes ({len(zones)}): {zones}")
    print("sample target parcels:")
    for props in parcel_props[:10]:
        print(
            "  "
            f"PARCEL_ID={props.get('PARCEL_ID')} SERIAL_NUM={props.get('SERIAL_NUM')} "
            f"addr={props.get('PARCEL_ADD')} city={props.get('PARCEL_CITY')} "
            f"subdiv={props.get('SUBDIV_NAME')}"
        )
    print("\n(NO DB WRITES - source-only validation.)")
    return 0


async def _run(*, dry_run: bool) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Summit UT Snyderville/Promontory Class B adapter ===\n")
    parcels, zoning = await _fetch_sources()
    target_parcels = _filter_target_parcels(parcels, zoning)
    print(f"[target] centroid-filtered parcels: {len(target_parcels):,}")

    conn = await asyncpg.connect(
        _session_db_url(),
        statement_cache_size=0,
        command_timeout=3600,
    )
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            jid = await _register_jurisdictions(conn)

            cleared = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                jid,
            )
            print(f"[idempotency] cleared {cleared.split()[-1]} zoning_district rows")

            parcel_rows = await _stage_and_merge_parcels(conn, target_parcels, jid)
            print(f"[parcels] staged/upserted {parcel_rows:,} target rows")

            zoning_rows = await _insert_zoning_districts(conn, zoning, jid)
            print(f"[zoning] inserted {zoning_rows:,} Summit zoning rows")

            contained, nearest, unmatched = await _spatial_backfill(conn, jid)
            print(f"[backfill] contained {contained:,}; nearest {nearest:,}; unmatched {unmatched:,}")

            bbox = await _update_bbox(conn, jid)
            print(f"[bbox] {bbox}")

            await _quality_report(conn, jid)

            if dry_run:
                raise _RollbackForDryRun()
    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()
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
        help="Run the full write path inside a transaction, then roll back.",
    )
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.preflight:
        return asyncio.run(_preflight())
    if args.dry_run:
        return asyncio.run(_run(dry_run=True))
    if args.i_know_this_writes_to_prod:
        return asyncio.run(_run(dry_run=False))

    print(
        "Refusing - pass --preflight for source-only validation, --dry-run for "
        "transactional rehearsal, or --i-know-this-writes-to-prod to fire.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
