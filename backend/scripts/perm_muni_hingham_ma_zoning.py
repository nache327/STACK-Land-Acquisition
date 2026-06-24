"""Phase 4 - Hingham MA Class B per-muni greenfield Op-5 adapter.

Per docs/PLYMOUTH_MA_ACQUISITION_SPEC.md (PR #335, merged) and
backend/scripts/_drafts/_hingham_ma_per_muni_probe_v2.md (PR #378, merged).

Greenfield (no Plymouth MA umbrella in prod): registers Hingham, MA as
a standalone per-muni jurisdiction, ingests parcels + zoning fresh.

Source layers (re-verified 2026-06-24):

  PARCELS  : MassGIS Standardized Assessors (statewide L3)
             https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/
                 services/Massachusetts_Property_Tax_Parcels/FeatureServer/0
             filter TOWN_ID=131  ->  8,894 parcels
             SRS: EPSG:26986 (server reprojects to 4326 via outSR)
             zone-code field: MAP_PAR_ID (apn); CITY='HINGHAM' (Norfolk gate)

  ZONING   : MAPC Zoning Atlas v0.2 zoning_full layer 2
             https://geo.mapc.org/server/rest/services/gisdata/
                 Zoning_Atlas_v01/MapServer/2
             filter muni='Hingham'  ->  15 base districts
             SRS: EPSG:3857 (server reprojects to 4326 via outSR)
             zone-code field: zo_code (prefixed with '131' per MA TOWN_ID)
             vintage: 2020-08-03 (service-level; spatialrec NULL per row)

Class C diagnostic only:
  MassGIS parcel ZONING field 7,475/8,894 = 84.0% non-null. Carries
  legacy codes (R1, R3, XX, 00, IA, IB) that don't match current bylaw.
  Per spec, do NOT use for direct backfill - Class B is source-of-record.

This script:
  1. Registers Hingham, MA as a standalone per-muni jurisdiction
     (county='Plymouth', state='MA').
  2. Ingests 8,894 MassGIS parcels with TOWN_ID=131 filter, server-
     reprojected to WGS84.
  3. Ingests 15 MAPC base zoning districts with muni='Hingham' filter.
  4. Spatial backfill (ST_Within centroid + nearest_50m fallback).
  5. raw_attributes preserved on both tables (Norfolk gate).
  6. Bbox written from parcel extent.

Hard rules:
  - greenfield: no umbrella merge / no parcel move; pure ingest
  - raw preserved verbatim (Norfolk gate)
  - CITY title-cased to 'Hingham' at ingest (PR #233 lesson)
  - zone_code = zo_code verbatim from MAPC (prefixed '131*'); substrate
    rows must match
  - Idempotent: re-runs delete + re-insert this Hingham JID's zoning_
    districts + parcel bindings inside a single transaction
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
from shapely.geometry import shape
from shapely.wkb import dumps as wkb_dumps
from shapely import make_valid

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("hingham_ma_zoning")

JURISDICTION_NAME = "Hingham, MA"
JURISDICTION_STATE = "MA"
JURISDICTION_COUNTY = "Plymouth"
MUNI_NAME = "Hingham"
MUNI_TYPE = "town"

PARCEL_LAYER_URL = (
    "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/"
    "Massachusetts_Property_Tax_Parcels/FeatureServer/0"
)
PARCEL_FILTER = "TOWN_ID=131"
PARCEL_PAGE_SIZE = 1000
PARCEL_EXPECTED_COUNT = 8894

ZONING_LAYER_URL = (
    "https://geo.mapc.org/server/rest/services/gisdata/"
    "Zoning_Atlas_v01/MapServer/2"
)
ZONING_FILTER = "muni='Hingham'"
ZONING_PAGE_SIZE = 1000
ZONING_EXPECTED_COUNT = 15
ZONE_CODE_FIELD = "zo_code"
ZONE_NAME_FIELD = "zo_name"
ZONING_RAW_PASSTHROUGH = (
    "OBJECTID",
    "muni",
    "zo_code",
    "zo_name",
    "zo_usety",
    "zo_usede",
    "mulfam2",
    "mnls_eff",
    "lapdu",
    "mxht_eff",
    "mxdu_eff",
    "dupac_eff",
    "far_eff",
    "spatialrec",
)
PARCEL_RAW_FIELDS_DROP = ()

MIN_ZONING_ROWS_FOR_FIRE = 12
MIN_PARCELS_FOR_FIRE = 5000

# Hingham bbox sanity envelope (WGS84). Town extent per live dry-run
# (parcel layer southern edge reaches ~42.15 due to barrier islands /
# inlet parcels). Used as a wrong-target catch, not a tight municipal
# boundary.
BBOX_LON_RANGE = (-71.00, -70.80)
BBOX_LAT_RANGE = (42.10, 42.32)

# Mirror app/services/ingestion.py _STAGE_COLUMNS (King WA precedent).
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


def _session_db_url() -> str:
    # Supabase session pooler (:5432) caps at 15 sessions, which is
    # frequently saturated by the Railway API instance + sibling
    # worktrees. Transaction pooler (:6543) supports much higher
    # concurrency; our entire DDL+DML lives inside one
    # `async with conn.transaction()` block, so the TEMP TABLE and
    # other session-scoped state persist for the duration.
    return DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _classify_residential_ma(use_code: int | None) -> bool | None:
    """MA DOR USE_CODE residential heuristic.

    MA DOR uses 4-digit codes prefixed by the broad class:
      1010-1019 single-family
      1040-1049 two-family / convertible
      1050-1059 three-family
      1090-1099 mixed-use residential
      1110-1119 multi-family
      1310     vacant residential
    """
    if use_code is None:
        return None
    try:
        u = int(use_code)
    except (TypeError, ValueError):
        return None
    if 1010 <= u <= 1199:
        return True
    if u == 1310:
        return True
    return False


def _rings_to_wkt(rings: list[list[list[float]]]) -> str:
    ring_wkts = []
    for ring in rings:
        if len(ring) < 4:
            continue
        coords = ", ".join(f"{p[0]} {p[1]}" for p in ring)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"


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


async def _arcgis_json(
    client: httpx.AsyncClient, url: str, params: dict[str, Any]
) -> dict[str, Any]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"ArcGIS error from {url}: {payload['error']}")
    return payload


async def _source_freshness_check(client: httpx.AsyncClient) -> None:
    # MAPC zoning_full
    zmeta = await _arcgis_json(client, ZONING_LAYER_URL, {"f": "json"})
    if zmeta.get("geometryType") != "esriGeometryPolygon":
        raise RuntimeError(
            f"MAPC source drift: geometryType={zmeta.get('geometryType')}"
        )
    z_fields = {f.get("name") for f in zmeta.get("fields", [])}
    if ZONE_CODE_FIELD not in z_fields:
        raise RuntimeError(
            f"MAPC source drift: missing {ZONE_CODE_FIELD!r}; fields={sorted(z_fields)}"
        )

    zcount = await _arcgis_json(
        client,
        f"{ZONING_LAYER_URL}/query",
        {"where": ZONING_FILTER, "returnCountOnly": "true", "f": "json"},
    )
    zn = int(zcount.get("count") or 0)
    if zn < MIN_ZONING_ROWS_FOR_FIRE:
        raise RuntimeError(f"MAPC zoning drift: Hingham count={zn}")

    # MassGIS parcels
    pmeta = await _arcgis_json(client, PARCEL_LAYER_URL, {"f": "json"})
    if pmeta.get("geometryType") != "esriGeometryPolygon":
        raise RuntimeError(
            f"MassGIS source drift: geometryType={pmeta.get('geometryType')}"
        )
    p_fields = {f.get("name") for f in pmeta.get("fields", [])}
    for required in ("MAP_PAR_ID", "TOWN_ID", "CITY"):
        if required not in p_fields:
            raise RuntimeError(
                f"MassGIS source drift: missing {required!r}; "
                f"fields={sorted(p_fields)}"
            )

    pcount = await _arcgis_json(
        client,
        f"{PARCEL_LAYER_URL}/query",
        {"where": PARCEL_FILTER, "returnCountOnly": "true", "f": "json"},
    )
    pn = int(pcount.get("count") or 0)
    if pn < MIN_PARCELS_FOR_FIRE:
        raise RuntimeError(
            f"MassGIS parcel drift: Hingham (TOWN_ID=131) count={pn}; "
            f"expected ~{PARCEL_EXPECTED_COUNT}"
        )

    print("[source] MAPC zoning_full layer live")
    print(f"  count          : {zn}  (expected {ZONING_EXPECTED_COUNT})")
    print(f"  code field     : {ZONE_CODE_FIELD}")
    print("[source] MassGIS parcels live")
    print(f"  count          : {pn}  (expected {PARCEL_EXPECTED_COUNT})")


async def _fetch_zoning_features(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = await _arcgis_json(
            client,
            f"{ZONING_LAYER_URL}/query",
            {
                "where": ZONING_FILTER,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "resultOffset": offset,
                "resultRecordCount": ZONING_PAGE_SIZE,
                "f": "json",
                "orderByFields": "OBJECTID",
            },
        )
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info(
            "fetched %d zoning features (cumulative %d) offset=%d",
            len(batch), len(features), offset,
        )
        if len(batch) < ZONING_PAGE_SIZE:
            break
        offset += ZONING_PAGE_SIZE
    return features


def _build_district_rows(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")
        zone_code = str(attrs.get(ZONE_CODE_FIELD) or "").strip()
        if not geom or "rings" not in geom or not zone_code:
            continue
        try:
            geom_wkt = _rings_to_wkt(geom["rings"])
        except Exception as exc:
            logger.warning("Skipping OBJECTID=%s: %s", attrs.get("OBJECTID"), exc)
            continue

        raw_attributes = {
            "source_url": ZONING_LAYER_URL,
            "source_kind": "arcgis_map_server",
            "source_filter": ZONING_FILTER,
            "ingested_at": "2026-06-24",
            "muni_name": MUNI_NAME,
            "muni_type": MUNI_TYPE,
            "publisher": "MAPC Zoning Atlas v0.2 (regional)",
            "vintage": "2020-08-03",  # service-level; spatialrec is NULL per row
            "spec_pr": 335,
            "probe_v2_pr": 378,
        }
        for key in ZONING_RAW_PASSTHROUGH:
            if key in attrs and attrs[key] is not None:
                raw_attributes[key] = attrs[key]

        zone_name = str(attrs.get(ZONE_NAME_FIELD) or zone_code).strip()
        rows.append(
            {
                "zone_code": zone_code,
                "zone_name": zone_name,
                "geom_wkt": geom_wkt,
                "raw_attributes": json.dumps(raw_attributes),
            }
        )
    return rows


async def _fetch_parcel_count(client: httpx.AsyncClient) -> int:
    payload = await _arcgis_json(
        client,
        f"{PARCEL_LAYER_URL}/query",
        {"where": PARCEL_FILTER, "returnCountOnly": "true", "f": "json"},
    )
    return int(payload.get("count") or 0)


async def _fetch_parcels_page(
    client: httpx.AsyncClient, offset: int,
) -> list[dict[str, Any]]:
    payload = await _arcgis_json(
        client,
        f"{PARCEL_LAYER_URL}/query",
        {
            "where": PARCEL_FILTER,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "resultOffset": offset,
            "resultRecordCount": PARCEL_PAGE_SIZE,
            "f": "geojson",
            "orderByFields": "OBJECTID",
        },
    )
    return payload.get("features", [])


def _build_parcel_record(
    feature: dict[str, Any], jid: uuid.UUID,
) -> tuple | None:
    props = feature.get("properties") or feature.get("attributes") or {}
    geom_json = feature.get("geometry")
    geom = _parse_geom(geom_json)
    if geom is None:
        return None

    apn = props.get("MAP_PAR_ID")
    if not apn:
        return None
    apn = str(apn).strip()
    if not apn:
        return None

    use_code = _safe_int(props.get("USE_CODE"))
    land_value = _safe_float(props.get("LAND_VAL"))
    bldg_value = _safe_float(props.get("BLDG_VAL"))
    assessed_value = _safe_float(props.get("TOTAL_VAL"))
    if assessed_value is None and (land_value is not None or bldg_value is not None):
        assessed_value = (land_value or 0) + (bldg_value or 0)
        if assessed_value <= 0:
            assessed_value = None

    has_structure = None
    if bldg_value is not None:
        has_structure = bldg_value > 0

    city = props.get("CITY")
    if city is not None and str(city).strip():
        city = str(city).strip().title()  # 'HINGHAM' -> 'Hingham'
    else:
        city = MUNI_NAME

    address = props.get("SITE_ADDR")
    if address:
        address = str(address).strip() or None

    lot_size = _safe_float(props.get("LOT_SIZE"))
    acres = lot_size / 43560.0 if lot_size and lot_size > 0 else None

    raw = {
        k: (str(v) if v is not None else None)
        for k, v in props.items()
        if k not in ("geometry",)
    }

    return (
        str(jid),
        apn,
        address,
        city,
        None,                                # owner_name (privacy + spec parity)
        None,                                # zoning_code (Class B writes it later)
        None,                                # zone_class
        str(use_code) if use_code is not None else None,
        acres,
        None,                                # county_link
        None,                                # in_flood_zone
        False,                               # in_wetland
        None,                                # avg_slope_pct
        has_structure,
        bldg_value,
        assessed_value,
        _classify_residential_ma(use_code),
        wkb_dumps(geom, hex=False, srid=4326),
        wkb_dumps(geom.centroid, hex=False, srid=4326),
        json.dumps(raw) if raw else None,
    )


async def _resolve_or_register_hingham(conn: asyncpg.Connection) -> str:
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        JURISDICTION_NAME, JURISDICTION_STATE,
    )
    if existing:
        jid = str(existing["id"])
        print(f"[jurisdiction] found existing {JURISDICTION_NAME}: {jid}")
        return jid

    jid = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO jurisdictions (id, name, state, county, parcel_endpoint)
           VALUES ($1::uuid, $2, $3, $4, $5)""",
        jid,
        JURISDICTION_NAME,
        JURISDICTION_STATE,
        JURISDICTION_COUNTY,
        PARCEL_LAYER_URL,
    )
    print(f"[jurisdiction] registered {JURISDICTION_NAME}: {jid}")
    return jid


async def _ingest_parcels(
    conn: asyncpg.Connection, jid: str, parcel_records: list[tuple],
) -> int:
    # MassGIS Hingham occasionally publishes >1 row per MAP_PAR_ID
    # (split lots / multi-polygon assemblages). Dedupe by APN here
    # (keep last seen) so the ON CONFLICT clause doesn't trip
    # "command cannot affect row a second time".
    by_apn: dict[str, tuple] = {}
    for rec in parcel_records:
        by_apn[rec[1]] = rec
    deduped = list(by_apn.values())
    dropped = len(parcel_records) - len(deduped)
    if dropped:
        print(f"[parcels] deduped {dropped} duplicate APN row(s) "
              f"({len(parcel_records)} -> {len(deduped)})")

    await conn.execute(_CREATE_STAGE_SQL)
    await conn.execute(_TRUNCATE_STAGE_SQL)
    CHUNK = 2000
    total = len(deduped)
    for i in range(0, total, CHUNK):
        chunk = deduped[i : i + CHUNK]
        await conn.copy_records_to_table(
            "_stage_parcels", records=chunk, columns=_STAGE_COLUMNS,
        )
    inserted = await conn.fetchval(
        "WITH ins AS (" + _MERGE_SQL + " RETURNING 1) SELECT COUNT(*) FROM ins"
    )
    return int(inserted or 0)


async def _update_hingham_bbox(conn: asyncpg.Connection, jid: str) -> list[float]:
    ext = await conn.fetchrow(
        """SELECT ST_XMin(ST_Extent(geom)) AS minx,
                  ST_YMin(ST_Extent(geom)) AS miny,
                  ST_XMax(ST_Extent(geom)) AS maxx,
                  ST_YMax(ST_Extent(geom)) AS maxy
           FROM parcels WHERE jurisdiction_id=$1::uuid AND geom IS NOT NULL""",
        jid,
    )
    if ext is None or ext["minx"] is None:
        raise RuntimeError("no Hingham parcel geometry post-ingest")
    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    lon_lo, lon_hi = BBOX_LON_RANGE
    lat_lo, lat_hi = BBOX_LAT_RANGE
    if not (
        lon_lo <= bbox[0] <= lon_hi
        and lon_lo <= bbox[2] <= lon_hi
        and lat_lo <= bbox[1] <= lat_hi
        and lat_lo <= bbox[3] <= lat_hi
    ):
        raise RuntimeError(
            f"Hingham bbox {bbox} outside expected range "
            f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
        )
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid, json.dumps(bbox),
    )
    print(f"[bbox] verified+updated: {bbox}")
    return bbox


class _RollbackForDryRun(Exception):
    pass


async def _run(nearest_within_meters: float, dry_run: bool) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Hingham MA Class B per-muni greenfield ===\n")

    async with httpx.AsyncClient(timeout=120.0) as client:
        await _source_freshness_check(client)
        # Zoning
        zfeatures = await _fetch_zoning_features(client)
        district_rows = _build_district_rows(zfeatures)
        distinct = sorted({row["zone_code"] for row in district_rows})
        print(f"[zoning] features={len(zfeatures)} rows={len(district_rows)} "
              f"distinct={len(distinct)}")
        print(f"[zoning] codes={distinct}")
        if len(district_rows) < MIN_ZONING_ROWS_FOR_FIRE:
            raise RuntimeError(
                f"REFUSE FIRE - only {len(district_rows)} zoning rows"
            )

        # Parcels
        ptotal = await _fetch_parcel_count(client)
        print(f"[parcels] live count: {ptotal:,}")
        if ptotal < MIN_PARCELS_FOR_FIRE:
            raise RuntimeError(f"REFUSE FIRE - parcel count {ptotal}")

        fake_jid_for_dry_record = uuid.UUID("00000000-0000-0000-0000-000000000000")
        parcel_records: list[tuple] = []
        offset = 0
        while True:
            batch = await _fetch_parcels_page(client, offset)
            if not batch:
                break
            for feat in batch:
                rec = _build_parcel_record(feat, fake_jid_for_dry_record)
                if rec is not None:
                    parcel_records.append(rec)
            logger.info(
                "fetched %d parcels (cumulative %d) offset=%d",
                len(batch), len(parcel_records), offset,
            )
            if len(batch) < PARCEL_PAGE_SIZE:
                break
            offset += PARCEL_PAGE_SIZE
        print(f"[parcels] mapped: {len(parcel_records):,}")
        if len(parcel_records) < MIN_PARCELS_FOR_FIRE:
            raise RuntimeError(
                f"REFUSE FIRE - mapped only {len(parcel_records)} parcels"
            )

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=3600
    )
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")
            jid = await _resolve_or_register_hingham(conn)

            # Repoint parcel records to the real JID.
            real_records = [
                (jid,) + rec[1:] for rec in parcel_records
            ]

            # Idempotency: clear prior Hingham zoning_districts + reset bindings.
            cleared = await conn.execute(
                "DELETE FROM zoning_districts WHERE jurisdiction_id=$1::uuid", jid,
            )
            print(
                f"[idempotency] cleared {int(cleared.split()[-1])} "
                "prior zoning_districts rows"
            )

            existing_parcels = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid", jid,
            )
            print(f"[parcels] existing under Hingham JID: {existing_parcels:,}")

            inserted = await _ingest_parcels(conn, jid, real_records)
            print(f"[parcels] inserted/updated: {inserted:,}")

            reset = await conn.execute(
                """UPDATE parcels
                      SET zoning_code=NULL,
                          zone_class=NULL,
                          zone_binding_method=NULL
                    WHERE jurisdiction_id=$1::uuid""",
                jid,
            )
            print(f"[idempotency] reset bindings on {int(reset.split()[-1])} parcels")

            print(f"[insert] {len(district_rows)} zoning_districts")
            for row in district_rows:
                await conn.execute(
                    """INSERT INTO zoning_districts (
                           jurisdiction_id, zone_code, zone_name, zone_class,
                           geom, raw_attributes, source
                       ) VALUES (
                           $1::uuid, $2, $3, 'unknown'::zone_class_enum,
                           ST_Multi(ST_MakeValid(ST_GeomFromText($4, 4326))),
                           $5::jsonb, 'arcgis'::zone_source_enum
                       )""",
                    jid, row["zone_code"], row["zone_name"],
                    row["geom_wkt"], row["raw_attributes"],
                )

            contained = await conn.execute(
                """
                UPDATE parcels target
                SET zone_class=sub.zone_class,
                    zone_binding_method='contained',
                    zoning_code=COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
                FROM (
                    SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                    FROM parcels p,
                    LATERAL (
                        SELECT d.zone_class, d.zone_code
                        FROM zoning_districts d
                        WHERE d.jurisdiction_id=$1::uuid
                          AND d.geom IS NOT NULL
                          AND ST_Within(ST_Centroid(p.geom), d.geom)
                        ORDER BY d.id
                        LIMIT 1
                    ) zd
                    WHERE p.jurisdiction_id=$1::uuid
                      AND p.geom IS NOT NULL
                ) sub
                WHERE target.id=sub.parcel_id
                """,
                jid,
            )
            print(f"[spatial] contained updated {int(contained.split()[-1])}")

            binding_label = f"nearest_{int(round(nearest_within_meters))}m"
            nearest = await conn.execute(
                """
                UPDATE parcels target
                SET zone_class=sub.zone_class,
                    zone_binding_method=$2,
                    zoning_code=COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
                FROM (
                    SELECT p.id AS parcel_id, zd.zone_class, zd.zone_code
                    FROM parcels p,
                    LATERAL (
                        SELECT d.zone_class, d.zone_code
                        FROM zoning_districts d
                        WHERE d.jurisdiction_id=$1::uuid
                          AND d.geom IS NOT NULL
                          AND ST_DWithin(
                              d.geom::geography,
                              ST_Centroid(p.geom)::geography,
                              $3
                          )
                        ORDER BY ST_Distance(
                            d.geom::geography,
                            ST_Centroid(p.geom)::geography
                        )
                        LIMIT 1
                    ) zd
                    WHERE p.jurisdiction_id=$1::uuid
                      AND p.geom IS NOT NULL
                      AND p.zone_binding_method IS NULL
                ) sub
                WHERE target.id=sub.parcel_id
                """,
                jid, binding_label, float(nearest_within_meters),
            )
            print(f"[spatial] {binding_label} updated {int(nearest.split()[-1])}")

            await _update_hingham_bbox(conn, jid)

            parcel_stats = await conn.fetchrow(
                """SELECT COUNT(*) AS total,
                          COUNT(*) FILTER (
                              WHERE zoning_code IS NOT NULL
                                AND btrim(zoning_code) <> ''
                          ) AS bound,
                          COUNT(*) FILTER (
                              WHERE zone_binding_method='contained'
                          ) AS contained,
                          COUNT(*) FILTER (
                              WHERE zone_binding_method LIKE 'nearest_%'
                          ) AS nearest
                   FROM parcels WHERE jurisdiction_id=$1::uuid""",
                jid,
            )
            district_count = await conn.fetchval(
                "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id=$1::uuid",
                jid,
            )
            empty_raw = await conn.fetchval(
                """SELECT COUNT(*) FROM zoning_districts
                   WHERE jurisdiction_id=$1::uuid
                     AND (raw_attributes IS NULL OR raw_attributes='{}'::jsonb)""",
                jid,
            )
            coverage = (
                100.0 * parcel_stats["bound"] / parcel_stats["total"]
                if parcel_stats["total"] else 0.0
            )
            nearest_pct = (
                100.0 * parcel_stats["nearest"] / parcel_stats["total"]
                if parcel_stats["total"] else 0.0
            )
            print("\n=== 5-GATE ===")
            print(f"GATE 1 cov {coverage:.1f}% (>=70%) - "
                  f"{'PASS' if coverage >= 70 else 'SUB'}")
            print(f"GATE 2 near {nearest_pct:.1f}% (<30%) - "
                  f"{'PASS' if nearest_pct < 30 else 'OVER'}")
            print(f"GATE 3 raw empty {empty_raw} - "
                  f"{'PASS' if empty_raw == 0 else 'FAIL'}")
            print(f"GATE 4 districts {district_count} - "
                  f"{'PASS' if district_count > 0 else 'FAIL'}")
            print("GATE 5 bbox populated")
            print(f"  parcels {parcel_stats['total']:,} "
                  f"bound {parcel_stats['bound']:,} "
                  f"contained {parcel_stats['contained']:,} "
                  f"nearest {parcel_stats['nearest']:,}")

            codes = await conn.fetch(
                """SELECT zoning_code, COUNT(*) AS n
                   FROM parcels
                   WHERE jurisdiction_id=$1::uuid
                     AND zoning_code IS NOT NULL
                     AND btrim(zoning_code) <> ''
                   GROUP BY 1
                   ORDER BY 2 DESC, 1""",
                jid,
            )
            print(f"\nDistribution ({len(codes)}):")
            for code in codes:
                print(f"  {code['zoning_code']:15s} {code['n']:>5,}")

            if dry_run:
                raise _RollbackForDryRun()

    except _RollbackForDryRun:
        print("\n(DRY-RUN - transaction rolled back; no prod writes survived)")
    finally:
        await conn.close()

    return 0


async def _source_check_only() -> int:
    async with httpx.AsyncClient(timeout=120.0) as client:
        await _source_freshness_check(client)
        zfeatures = await _fetch_zoning_features(client)
    rows = _build_district_rows(zfeatures)
    distinct = sorted({row["zone_code"] for row in rows})
    print(f"[zoning] full fetch features={len(zfeatures)} rows={len(rows)}")
    print(f"[zoning] distinct codes ({len(distinct)}): {distinct}")
    if len(rows) < MIN_ZONING_ROWS_FOR_FIRE:
        raise RuntimeError(f"source check failed - only {len(rows)} usable rows")
    print("\n(NO DB WRITES - source freshness only.)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-know-this-writes-to-prod", action="store_true")
    parser.add_argument("--nearest-within-meters", type=float, default=50.0)
    args = parser.parse_args()

    if args.source_check_only:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        raise SystemExit(asyncio.run(_source_check_only()))

    if not args.dry_run and not args.i_know_this_writes_to_prod:
        print(
            "Refusing - pass --dry-run for transactional rehearsal or "
            "--i-know-this-writes-to-prod to actually fire.",
            file=sys.stderr,
        )
        sys.exit(2)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(
        asyncio.run(_run(args.nearest_within_meters, dry_run=args.dry_run))
    )
