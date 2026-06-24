"""Phase 6 expansion PREP - Pinecrest FL Class B per-muni adapter.

PREP ONLY. Do not fire without explicit Master approval.

Source path, per PR #344 diagnostic:
  - Parcels: Miami-Dade PaParcelView filtered to TRUE_SITE_CITY='Pinecrest'
    https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/PaParcelView_gdb/FeatureServer/0
  - Zoning: Village of Pinecrest Zoning / Pinecrest_Zoning_JAN2025_Updt
    https://services3.arcgis.com/0IbOaQdCzMiaAcDv/arcgis/rest/services/Zoning/FeatureServer/1

Pattern: PR #334 Winnetka prep shape, adapted for a direct per-muni parcel
ingest. Miami-Dade umbrella county remains untouched. Pinecrest registers as
its own per-muni jurisdiction and ingests only Pinecrest parcels.

Why this is the clean path:
  - PaParcelView carries PID and FOLIO for Pinecrest parcels.
  - Pinecrest zoning rows carry PID, FOLIO, and ZONE.
  - Backfill is by parcel keys (PID first, FOLIO fallback), not a county
    geometry guess.

Idempotency:
  - Full write path is wrapped in one transaction.
  - Jurisdiction registration is upsert-like.
  - Parcels are staged and upserted on (jurisdiction_id, apn).
  - Existing zoning_districts for the Pinecrest JID are delete-then-inserted.
  - Parcel zoning bindings for the Pinecrest JID are reset before the PID/FOLIO
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
from shapely.wkb import dumps as wkb_dumps

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")

logger = logging.getLogger("pinecrest_fl")

JURISDICTION_NAME = "Pinecrest, FL"
JURISDICTION_STATE = "FL"
JURISDICTION_COUNTY = "Miami-Dade"
MUNI_NAME = "Pinecrest"
PROD_CITY_VALUE = "Pinecrest"

PARCEL_LAYER = (
    "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/"
    "PaParcelView_gdb/FeatureServer/0"
)
ZONING_LAYER = (
    "https://services3.arcgis.com/0IbOaQdCzMiaAcDv/arcgis/rest/services/"
    "Zoning/FeatureServer/1"
)
ORDINANCE_URL = (
    "https://library.municode.com/fl/pinecrest/codes/code_of_ordinances"
)

PARCEL_WHERE = "TRUE_SITE_CITY = 'Pinecrest'"
PAGE_SIZE = 2000
SOURCE_DATE = "2026-06-23"

# Loose Pinecrest / south Miami-Dade sanity envelope.
BBOX_LON = (-80.37, -80.25)
BBOX_LAT = (25.60, 25.72)

_STAGE_COLUMNS = [
    "jurisdiction_id", "apn", "address", "city", "owner_name",
    "zoning_code", "zone_class", "land_use_code", "acres",
    "county_link", "in_flood_zone", "in_wetland", "avg_slope_pct",
    "has_structure", "improvement_value", "assessed_value",
    "is_residential", "geom_wkb", "centroid_wkb", "raw_json",
]

_CREATE_STAGE_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _stage_pinecrest_parcels (
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
FROM _stage_pinecrest_parcels s
ON CONFLICT ON CONSTRAINT uq_parcels_jurisdiction_apn DO UPDATE SET
    address = EXCLUDED.address,
    city = EXCLUDED.city,
    state = 'FL',
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


def _residential_from_dor(dor_code: str | None, dor_desc: str | None) -> bool | None:
    code = (dor_code or "").strip()
    desc = (dor_desc or "").upper()
    if code.startswith(("01", "02", "03", "04", "08")):
        return True
    if any(token in desc for token in ("SINGLE FAMILY", "MULTIFAMILY", "CONDOMINIUM", "RESIDENTIAL")):
        return True
    if any(token in desc for token in ("COMMERCIAL", "PARKING", "EDUCATIONAL", "GOVERNMENT")):
        return False
    return None


def _sqft_to_acres(value: Any) -> float | None:
    sqft = _float(value)
    if sqft is None:
        return None
    return sqft / 43560.0


def _zone_class(zone: str) -> str:
    z = zone.strip().upper()
    if z.startswith(("EU", "RU")):
        return "residential"
    if z.startswith(("BU", "IU")):
        return "commercial"
    if z in {"PS", "GU"}:
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
    order_field: str = "OBJECTID",
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
            timeout=180.0,
        )
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("features", [])
        features.extend(batch)
        logger.info("fetched %s offset=%d batch=%d total=%d", layer, offset, len(batch), len(features))
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return features


async def _fetch_sources() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with httpx.AsyncClient(timeout=180.0) as client:
        parcel_count = await _fetch_count(client, PARCEL_LAYER, PARCEL_WHERE)
        zoning_count = await _fetch_count(client, ZONING_LAYER, "1=1")
        print(f"[source] Pinecrest parcel count: {parcel_count:,}")
        print(f"[source] Pinecrest zoning count: {zoning_count:,}")
        parcels = await _fetch_geojson_features(client, PARCEL_LAYER, PARCEL_WHERE)
        zoning = await _fetch_geojson_features(client, ZONING_LAYER, "1=1")
    return parcels, zoning


def _parcel_rows(features: list[dict[str, Any]], jid: str) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    skipped = 0
    seen_apns: set[str] = set()
    for feature in features:
        attrs = feature.get("properties") or {}
        # FOLIO is the public property key, but the live source has duplicate
        # FOLIO rows for a few nonstandard parcels. PID is present on both
        # parcel and zoning sources and is unique enough for the DB upsert key.
        apn = _text(attrs.get("PID")) or _text(attrs.get("FOLIO"))
        geom_json = feature.get("geometry")
        if not apn or not geom_json:
            skipped += 1
            continue
        if apn in seen_apns:
            logger.warning("skip duplicate parcel key apn=%s FOLIO=%s", apn, attrs.get("FOLIO"))
            skipped += 1
            continue
        seen_apns.add(apn)
        try:
            geom = _polygonal(shape(geom_json))
        except Exception as exc:
            logger.warning("skip parcel FOLIO=%s PID=%s: %s", apn, attrs.get("PID"), exc)
            skipped += 1
            continue

        raw = {
            "source_url": PARCEL_LAYER,
            "source_filter": PARCEL_WHERE,
            "source_kind": "arcgis_feature_server",
            "ingested_at": SOURCE_DATE,
            "muni_name": MUNI_NAME,
            "muni_type": "village",
            "publisher": "Miami-Dade County PaParcelView",
            **attrs,
        }
        address = _text(attrs.get("TRUE_SITE_ADDR"))
        city = _text(attrs.get("TRUE_SITE_CITY")) or PROD_CITY_VALUE
        dor_code = _text(attrs.get("DOR_CODE_CUR"))
        dor_desc = _text(attrs.get("DOR_DESC"))
        assessed_value = _float(attrs.get("ASSESSED_VAL_CUR"))
        building_area = _float(attrs.get("BUILDING_ACTUAL_AREA"))
        centroid = geom.centroid
        rows.append((
            jid,
            apn,
            address,
            city,
            _text(attrs.get("TRUE_OWNER1")),
            None,
            None,
            dor_code,
            _sqft_to_acres(attrs.get("LOT_SIZE")),
            None,
            False,
            False,
            None,
            building_area is not None and building_area > 0,
            None,
            assessed_value,
            _residential_from_dor(dor_code, dor_desc),
            wkb_dumps(geom, hex=False, srid=4326),
            wkb_dumps(centroid, hex=False, srid=4326),
            json.dumps(raw),
        ))
    if skipped:
        print(f"[parcels] skipped {skipped} rows with missing key/geometry")
    return rows


def _zoning_rows(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skipped = 0
    for feature in features:
        attrs = feature.get("properties") or {}
        zone = _text(attrs.get("ZONE"))
        geom_json = feature.get("geometry")
        if not zone or not geom_json:
            skipped += 1
            continue
        try:
            geom = _polygonal(shape(geom_json))
        except Exception as exc:
            logger.warning("skip zoning OBJECTID=%s PID=%s: %s", attrs.get("OBJECTID"), attrs.get("PID"), exc)
            skipped += 1
            continue
        raw = {
            "source_url": ZONING_LAYER,
            "source_filter": "1=1",
            "source_kind": "arcgis_feature_server",
            "ingested_at": SOURCE_DATE,
            "muni_name": MUNI_NAME,
            "muni_type": "village",
            "publisher": "Village of Pinecrest Zoning",
            **attrs,
        }
        rows.append({
            "zone_code": zone,
            "zone_name": zone,
            "zone_class": _zone_class(zone),
            "geom_wkb": wkb_dumps(geom, hex=False, srid=4326),
            "raw": json.dumps(raw),
        })
    if skipped:
        print(f"[zoning] skipped {skipped} rows with missing zone/geometry")
    return rows


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
            PARCEL_LAYER,
            ZONING_LAYER,
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
        PARCEL_LAYER,
        ZONING_LAYER,
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
    await conn.execute(_CREATE_STAGE_SQL)
    await conn.execute("TRUNCATE _stage_pinecrest_parcels")
    if rows:
        await conn.copy_records_to_table(
            "_stage_pinecrest_parcels",
            records=rows,
            columns=_STAGE_COLUMNS,
        )
        await conn.execute(_MERGE_SQL)
        await conn.execute(
            """
            UPDATE parcels
               SET city=$2,
                   state='FL',
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
        raise RuntimeError("no Pinecrest parcel geometry after ingest")
    bbox = [float(ext["minx"]), float(ext["miny"]), float(ext["maxx"]), float(ext["maxy"])]
    if not (
        BBOX_LON[0] <= bbox[0] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[1] <= BBOX_LAT[1]
        and BBOX_LON[0] <= bbox[2] <= BBOX_LON[1]
        and BBOX_LAT[0] <= bbox[3] <= BBOX_LAT[1]
    ):
        raise RuntimeError(f"bbox {bbox} outside Pinecrest envelope lon={BBOX_LON} lat={BBOX_LAT}")
    await conn.execute(
        "UPDATE jurisdictions SET bbox=$2::jsonb WHERE id=$1::uuid",
        jid,
        json.dumps(bbox),
    )
    return bbox


async def _backfill_by_pid_folio(conn: asyncpg.Connection, jid: str) -> tuple[int, int]:
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

    status = await conn.execute(
        """
        UPDATE parcels target
           SET zoning_code = sub.zone_code,
               zone_class = sub.zone_class,
               zone_binding_method = 'pid_folio',
               updated_at = NOW()
          FROM (
              SELECT p.id AS parcel_id, zd.zone_code, zd.zone_class
                FROM parcels p
                JOIN LATERAL (
                    SELECT z.zone_code, z.zone_class
                      FROM zoning_districts z
                     WHERE z.jurisdiction_id=$1::uuid
                       AND (
                         NULLIF(p.raw->>'PID', '') = NULLIF(z.raw_attributes->>'PID', '')
                         OR NULLIF(p.raw->>'FOLIO', '') = NULLIF(z.raw_attributes->>'FOLIO', '')
                         OR p.apn = NULLIF(z.raw_attributes->>'PID', '')
                       )
                     ORDER BY
                       CASE WHEN NULLIF(p.raw->>'PID', '') = NULLIF(z.raw_attributes->>'PID', '') THEN 0 ELSE 1 END,
                       z.id
                     LIMIT 1
                ) zd ON TRUE
               WHERE p.jurisdiction_id=$1::uuid
          ) sub
         WHERE target.id = sub.parcel_id
        """,
        jid,
    )
    keyed = int(status.split()[-1])

    unmatched = await conn.fetchval(
        """
        SELECT COUNT(*)
          FROM parcels
         WHERE jurisdiction_id=$1::uuid
           AND (zoning_code IS NULL OR btrim(zoning_code)='')
        """,
        jid,
    )
    return keyed, int(unmatched)


async def _quality_report(conn: asyncpg.Connection, jid: str) -> None:
    p = await conn.fetchrow(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND btrim(zoning_code)<>'') AS bound,
               COUNT(*) FILTER (WHERE zone_binding_method='pid_folio') AS pid_folio,
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
    print("\n=== 5-GATE PREP REPORT ===")
    print(f"GATE 1 parcel zoning coverage {cov:.1f}% (>=70%) - {'PASS' if cov >= 70 else 'SUB'}")
    print("GATE 2 nearest fallback 0.0% - PASS (PID/FOLIO key bridge only)")
    print(f"GATE 3 parcel raw empty {p['empty_raw']} / zoning raw empty {d['empty_raw']}")
    print(f"GATE 4 zoning_district rows {d['total']} / distinct codes {d['codes']}")
    print("GATE 5 bbox populated inline")
    print(f"  parcels {p['total']:,} bound {p['bound']:,} pid_folio {p['pid_folio']:,}")

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
    print("\n=== PRE-FLIGHT: Pinecrest FL source shape ===\n")
    parcels, zoning = await _fetch_sources()
    parcel_keys = [p.get("properties", {}) for p in parcels[:5]]
    parcel_props = [p.get("properties", {}) for p in parcels]
    parcel_pids = [_text(p.get("PID")) for p in parcel_props if _text(p.get("PID"))]
    parcel_folios = [_text(p.get("FOLIO")) for p in parcel_props if _text(p.get("FOLIO"))]
    zoning_props = [z.get("properties", {}) for z in zoning]
    zones = sorted({_text(p.get("ZONE")) for p in zoning_props if _text(p.get("ZONE"))})
    pid_present = sum(1 for p in zoning_props if _text(p.get("PID")))
    folio_present = sum(1 for p in zoning_props if _text(p.get("FOLIO")))
    print(f"parcel rows fetched: {len(parcels):,}")
    print(
        f"parcel PID present: {len(parcel_pids):,}; unique PID: {len(set(parcel_pids)):,}; "
        f"unique FOLIO: {len(set(parcel_folios)):,}"
    )
    print(f"zoning rows fetched: {len(zoning):,}")
    print(f"zoning distinct codes ({len(zones)}): {zones}")
    print(f"zoning PID present: {pid_present:,}; FOLIO present: {folio_present:,}")
    print("sample parcel keys:")
    for props in parcel_keys:
        print(
            "  "
            f"FOLIO={props.get('FOLIO')} PID={props.get('PID')} "
            f"addr={props.get('TRUE_SITE_ADDR')} city={props.get('TRUE_SITE_CITY')}"
        )
    print("\n(NO DB WRITES - source-only validation.)")
    return 0


async def _run(*, dry_run: bool) -> int:
    mode = "DRY-RUN (ROLLBACK)" if dry_run else "FIRE"
    print(f"\n=== {mode}: Pinecrest FL Class B per-muni adapter ===\n")
    parcels, zoning = await _fetch_sources()

    conn = await asyncpg.connect(
        _session_db_url(),
        statement_cache_size=0,
        command_timeout=3600,
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

            parcel_rows = await _stage_and_merge_parcels(conn, parcels, jid)
            print(f"[parcels] staged/upserted {parcel_rows:,} Pinecrest rows")

            zoning_rows = await _insert_zoning_districts(conn, zoning, jid)
            print(f"[zoning] inserted {zoning_rows:,} Pinecrest zoning rows")

            keyed, unmatched = await _backfill_by_pid_folio(conn, jid)
            print(f"[backfill] PID/FOLIO bound {keyed:,}; unmatched {unmatched:,}")

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
