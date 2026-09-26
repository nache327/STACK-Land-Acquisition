"""Phase 7E.1 — Oakland County, MI parcel ingest + jurisdiction registration.

Wave 4 dispatch per Master's 2026-06-19 parallel-wave directive. Second
massive-county wave (after Maricopa Phase 7B.1). Oakland MI per Diagnostic
PR #260 acquisition spec — SINGLE-COUNTY-PORTAL class, 490,590 parcels.

Source: Oakland County Access Oakland open parcel layer
  https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/
  EnterpriseOpenParcelDataMapService/MapServer/1

Live probes (2026-06-19, per PR #260):
  - Layer name     : Tax Parcel Plus
  - Total parcel count: 490,590
  - Max records / query: 2,000
  - Spatial reference  : Web Mercator (wkid=102100); reproject via outSR=4326
  - County bbox WGS84  : [-83.694, 42.426, -83.074, 42.894]
  - 5 wealth-band munis per orchestrator pre-stage 8fe33e5:
      Birmingham         9,786 parcels (Path A direct ArcGIS — 21 codes)
      Beverly Hills      ~5,500 (Path A direct ArcGIS — 12 codes)
      Bloomfield Hills   1,833 (Path B ordinance)
      Bloomfield Township ~25k (Path B ordinance)
      Franklin           ~1,500 (Path B ordinance)
    Total wealth-band: ~44k parcels

Standalone script (PR #250 / Hennepin Phase 7A.1 pattern). COPY-upsert
via asyncpg + _stage_parcels temp table + ON CONFLICT MERGE.

Field mapping (Tax Parcel Plus → parcels):

  - KEYPIN (parcel ID)              → parcels.apn
  - CVTTAXDESCRIPTION (UPPERCASE)   → parcels.city  (political-entity prefix:
      'CITY OF BIRMINGHAM', 'VILLAGE OF FRANKLIN', 'CHARTER TOWNSHIP OF
      BLOOMFIELD', etc — per Diagnostic PR #260)
  - SITEADDRESS                     → parcels.address
  - NAME1                           → parcels.owner_name
  - CLASSCODE                       → parcels.land_use_code
  - ASSESSEDVALUE                   → parcels.assessed_value
  - LIVING_AREA_SQFT                → improvement signal
  - geometry (reprojected → WGS84)  → parcels.geom + .centroid

Case discipline (CRITICAL — different from MN/WA/CT/AZ):
  Oakland publishes CVTTAXDESCRIPTION as UPPERCASE-with-political-entity-
  prefix ('CITY OF BIRMINGHAM' not 'Birmingham'). Per Master's Wave 4
  dispatch: PRESERVE THIS VERBATIM — do NOT strip the prefix. Phase 7E.2
  per-muni registration uses exact-equality CVTTAXDESCRIPTION='CITY OF
  BIRMINGHAM' joins.

  Per Diagnostic PR #260: use CVTTAXDESCRIPTION, not SITECITY (SITECITY
  over-selects Bloomfield-area parcels using postal city which doesn't
  respect actual incorporation).

is_residential heuristic via MI CLASSCODE:
  401-499 = residential                  → True
  301-399 = industrial                   → False
  201-299 = commercial                   → False
  101-199 = agricultural                 → None
  others                                 → None

Birmingham numeric-zero caveat per Diagnostic PR #260: city zoning layer
uses 0-1 / 0-2 (numeric ZERO) for office codes, not the letter O. Phase 7E.3
adapter will need to handle this carefully.

raw_attributes passthrough is BOUNDED — Tax Parcel Plus publishes 24 fields.
Curated 19-field subset preserves operational utility.

Subcommands:

  register   Idempotent. Finds/INSERTs Oakland County, MI in jurisdictions.
  preflight  1k-row sample, NO DB WRITES. UPPERCASE prefix sanity check.
  fire       Real prod ingest. Requires --i-know-this-writes-to-prod.
             Paginates the all-Oakland filter in 50k-feature batches.

Hard rules honored:
  - raw_attributes preserved verbatim, bounded passthrough (Norfolk gate)
  - CVTTAXDESCRIPTION preserved UPPERCASE + political-entity prefix
  - No zoning data written (Phase 7E.3 separate)
  - Inline jurisdictions.bbox UPDATE at fire-end (PR #261 codified)
  - Skip in-DB ROLLBACK preflight at Class A scale (PR #253)
  - --start-offset resume flag for silent-hang recovery (Hennepin precedent)
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
from shapely.geometry import shape
from shapely.wkb import dumps as wkb_dumps
from shapely import make_valid

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("oakland_mi_ingest")

LAYER_URL = (
    "https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/"
    "EnterpriseOpenParcelDataMapService/MapServer/1"
)
COUNTY_FILTER = "1=1"
JUR_NAME = "Oakland County, MI"
JUR_STATE = "MI"
JUR_COUNTY = "Oakland"
PAGE_SIZE = 2000
BATCH_SIZE = 50_000

_RAW_PASSTHROUGH = (
    "KEYPIN", "REVISIONDATE", "CVTTAXCODE", "CVTTAXDESCRIPTION", "PIN",
    "CLASSCODE", "NAME1", "NAME2",
    "SITEADDRESS", "SITECITY", "SITESTATE", "SITEZIP5",
    "POSTALADDRESS",
    "ASSESSEDVALUE", "TAXABLEVALUE",
    "NUM_BEDS", "NUM_BATHS", "STRUCTURE_DESC", "LIVING_AREA_SQFT",
)

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


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def _classify_residential(class_code: str | None) -> bool | None:
    """MI assessing CLASSCODE → is_residential.

    401-499 = residential       → True
    201-299 = commercial        → False
    301-399 = industrial        → False
    101-199 = agricultural      → None
    others                      → None
    """
    if not class_code:
        return None
    try:
        c = int(str(class_code).strip())
    except (TypeError, ValueError):
        return None
    if 401 <= c <= 499:
        return True
    if 201 <= c <= 399:
        return False
    return None


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


def _trim(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _map_row(
    props: dict[str, Any],
    geom: Any,
    jid: uuid.UUID,
) -> dict[str, Any] | None:
    apn = _trim(props.get("KEYPIN")) or _trim(props.get("PIN"))
    if not apn:
        return None

    # CRITICAL: preserve UPPERCASE + political-entity prefix per Master.
    # CVTTAXDESCRIPTION = 'CITY OF BIRMINGHAM' / 'VILLAGE OF FRANKLIN' / etc.
    # Per PR #260: use CVTTAXDESCRIPTION not SITECITY (postal noise).
    city = _trim(props.get("CVTTAXDESCRIPTION"))

    address = _trim(props.get("SITEADDRESS"))
    owner = _trim(props.get("NAME1"))
    class_code = _trim(props.get("CLASSCODE"))
    assessed = _safe_float(props.get("ASSESSEDVALUE"))
    if assessed is not None and assessed <= 0:
        assessed = None

    has_structure = None
    living_area = _safe_int(props.get("LIVING_AREA_SQFT"))
    structure_desc = _trim(props.get("STRUCTURE_DESC"))
    if living_area is not None and living_area > 0:
        has_structure = True
    elif structure_desc:
        has_structure = True
    elif living_area == 0:
        has_structure = False

    raw = {}
    for k in _RAW_PASSTHROUGH:
        v = props.get(k)
        if v is not None:
            v = str(v).strip() if isinstance(v, str) else v
            if v != "":
                raw[k] = v

    return {
        "jurisdiction_id": str(jid),
        "apn": apn,
        "address": address,
        "city": city,
        "owner_name": owner,
        "zoning_code": None,
        "zone_class": None,
        "land_use_code": class_code,
        "acres": None,
        "county_link": None,
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": None,
        "assessed_value": assessed,
        "is_residential": _classify_residential(class_code),
        "geom": geom,
        "centroid": geom.centroid,
        "raw": raw,
    }


def _row_to_record(r: dict[str, Any]) -> tuple:
    raw = r.get("raw")
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
        json.dumps(raw) if raw is not None else None,
    )


async def _register_jurisdiction() -> uuid.UUID:
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=60)
    try:
        existing = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
            JUR_NAME, JUR_STATE,
        )
        if existing:
            jid = existing["id"]
            logger.info("Found existing jurisdiction: %s -> %s", JUR_NAME, jid)
            return jid
        jid = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO jurisdictions (id, name, state, county, parcel_endpoint)
            VALUES ($1::uuid, $2, $3, $4, $5)
            """,
            str(jid), JUR_NAME, JUR_STATE, JUR_COUNTY, LAYER_URL,
        )
        logger.info("Registered new jurisdiction: %s -> %s", JUR_NAME, jid)
        return jid
    finally:
        await conn.close()


async def _fetch_page_by_offset(
    client: httpx.AsyncClient, offset: int,
) -> list[dict[str, Any]]:
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            r = await client.get(
                f"{LAYER_URL}/query",
                params={
                    "where": COUNTY_FILTER, "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": "4326", "f": "geojson",
                    "resultOffset": offset, "resultRecordCount": PAGE_SIZE,
                    "orderByFields": "OBJECTID_12",
                },
                timeout=300.0,
            )
            r.raise_for_status()
            return r.json().get("features", [])
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last_exc = e
            backoff = 2 ** attempt
            logger.warning(
                "offset=%d attempt=%d %s — retrying in %ds",
                offset, attempt + 1, type(e).__name__, backoff,
            )
            await asyncio.sleep(backoff)
    raise RuntimeError(
        f"Oakland ArcGIS offset={offset} failed after 5 retries: {last_exc}"
    )


async def _fetch_batch_by_offset(
    client: httpx.AsyncClient, offset: int, n: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    fetched = 0
    while fetched < n:
        feats = await _fetch_page_by_offset(client, offset + fetched)
        if not feats:
            break
        out.extend(feats)
        fetched += len(feats)
        if len(feats) < PAGE_SIZE:
            break
    return out


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


async def _copy_upsert(rows: list[dict[str, Any]]) -> int:
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0)
    try:
        await conn.execute("SET statement_timeout = 0")
        async with conn.transaction():
            await conn.execute(_CREATE_STAGE_SQL)
            await conn.execute(_TRUNCATE_STAGE_SQL)
            CHUNK = 25_000
            total = len(rows)
            for i in range(0, total, CHUNK):
                chunk = rows[i : i + CHUNK]
                records = [_row_to_record(r) for r in chunk]
                await conn.copy_records_to_table(
                    "_stage_parcels", records=records, columns=_STAGE_COLUMNS,
                )
            r = await conn.fetchval(
                "WITH ins AS (" + _MERGE_SQL + " RETURNING 1) SELECT COUNT(*) FROM ins"
            )
            return int(r or 0)
    finally:
        await conn.close()


async def _update_bbox_inline(jid: uuid.UUID) -> None:
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=1800)
    try:
        ext = await conn.fetchrow(
            """
            SELECT ST_XMin(ST_Extent(geom)) AS minx,
                   ST_YMin(ST_Extent(geom)) AS miny,
                   ST_XMax(ST_Extent(geom)) AS maxx,
                   ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            str(jid),
        )
        if not ext or ext["minx"] is None:
            logger.warning("No parcel geometry to compute Oakland bbox from")
            return
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        # Oakland County, MI — Detroit metro
        if not (-83.8 <= bbox[0] <= -83.0 and 42.3 <= bbox[1] <= 43.0):
            raise RuntimeError(
                f"Oakland bbox {bbox} outside expected range "
                f"(lon -83.8 to -83.0, lat 42.3 to 43.0)"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(jid), json.dumps(bbox),
        )
        logger.info("Inline jurisdictions.bbox UPDATEd: %s", bbox)
    finally:
        await conn.close()


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Oakland Tax Parcel Plus ingest ===\n")
    fake_jid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(
            f"{LAYER_URL}/query",
            params={
                "where": COUNTY_FILTER, "outFields": "*",
                "returnGeometry": "true", "outSR": "4326",
                "f": "geojson", "resultRecordCount": 1000,
                "orderByFields": "OBJECTID_12",
            },
        )
        r.raise_for_status()
        sample = r.json().get("features", [])
    print(f"features fetched : {len(sample)}")
    mapped = []
    geom_skipped = apn_skipped = 0
    cities: dict[str, int] = {}
    for feat in sample:
        props = feat.get("properties") or {}
        geom = _parse_geom(feat.get("geometry"))
        if geom is None:
            geom_skipped += 1
            continue
        m = _map_row(props, geom, fake_jid)
        if m is None:
            apn_skipped += 1
            continue
        mapped.append(m)
        if m.get("city"):
            cities[m["city"]] = cities.get(m["city"], 0) + 1
    print(f"geom_skipped     : {geom_skipped}")
    print(f"apn_skipped      : {apn_skipped}")
    print(f"mappable rows    : {len(mapped)}")
    print(f"\nDistinct CVTTAXDESCRIPTION (UPPERCASE + prefix) in sample: {len(cities)}")
    for c, n in sorted(cities.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:50s} {n}")
    print(f"\n5 wealth-band target munis (UPPERCASE + political prefix):")
    for muni in (
        "CITY OF BIRMINGHAM", "CITY OF BLOOMFIELD HILLS",
        "CHARTER TOWNSHIP OF BLOOMFIELD", "VILLAGE OF FRANKLIN",
        "VILLAGE OF BEVERLY HILLS",
    ):
        print(f"  {muni:38s} (exact-match): {cities.get(muni, 0)}")
    print("\n(NO DB WRITES — pipeline shape validated)")
    return 0


async def _fire(jid: uuid.UUID, start_offset: int = 0) -> int:
    print(f"\n=== FIRE: Oakland Tax Parcel Plus → {jid} "
          f"(start_offset={start_offset:,}) ===\n")
    started = time.time()
    total_ingested = 0
    total_apn_skipped = 0
    total_geom_skipped = 0
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Total count (clamps batch_start range)
        r0 = await client.get(
            f"{LAYER_URL}/query",
            params={"where": COUNTY_FILTER, "returnCountOnly": "true", "f": "json"},
        )
        r0.raise_for_status()
        total = int(r0.json().get("count") or 0)
        if total == 0:
            print("Source returned count=0 — bailing", file=sys.stderr)
            return 1
        print(f"Total Oakland features: {total:,}")
        batch_idx = 0
        for batch_start in range(start_offset, total, BATCH_SIZE):
            batch_idx += 1
            t0 = time.time()
            feats = await _fetch_batch_by_offset(client, batch_start, BATCH_SIZE)
            t1 = time.time()
            rows_by_apn: dict[str, dict] = {}
            geom_skipped = apn_skipped = 0
            for feat in feats:
                props = feat.get("properties") or {}
                geom = _parse_geom(feat.get("geometry"))
                if geom is None:
                    geom_skipped += 1
                    continue
                m = _map_row(props, geom, jid)
                if m is None:
                    apn_skipped += 1
                    continue
                rows_by_apn[m["apn"]] = m
            total_geom_skipped += geom_skipped
            total_apn_skipped += apn_skipped
            t2 = time.time()
            n_to_upsert = len(rows_by_apn)
            if n_to_upsert == 0:
                logger.warning("Batch %d produced 0 mappable rows", batch_idx)
                continue
            n = await _copy_upsert(list(rows_by_apn.values()))
            t3 = time.time()
            total_ingested += n
            print(
                f"  Batch {batch_idx:>3} | offset {batch_start:>8,} "
                f"| feats {len(feats):>5} "
                f"| geom_skip {geom_skipped:>4} | apn_skip {apn_skipped:>4} "
                f"| mapped {n_to_upsert:>5} | upserted {n:>5} "
                f"| fetch {t1-t0:5.1f}s | map {t2-t1:5.1f}s "
                f"| copy {t3-t2:5.1f}s | cumulative {total_ingested:>7,}",
                flush=True,
            )
    elapsed = time.time() - started
    print(f"\n=== Fire complete: {total_ingested:,} parcels upserted "
          f"in {elapsed/60:.1f} min ===")
    print(f"  total_geom_skipped : {total_geom_skipped}")
    print(f"  total_apn_skipped  : {total_apn_skipped}")
    await _update_bbox_inline(jid)
    # Wealth-band readiness
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=600)
    try:
        for muni in (
            "CITY OF BIRMINGHAM", "CITY OF BLOOMFIELD HILLS",
            "CHARTER TOWNSHIP OF BLOOMFIELD", "VILLAGE OF FRANKLIN",
            "VILLAGE OF BEVERLY HILLS",
        ):
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid AND city = $2",
                str(jid), muni,
            )
            print(f"  city={muni:38s}: {n:,} parcels (Phase 7E.2 readiness)")
    finally:
        await conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("register")
    sub.add_parser("preflight")
    sub_fire = sub.add_parser("fire")
    sub_fire.add_argument(
        "--i-know-this-writes-to-prod", action="store_true",
        help="Confirmation flag.",
    )
    sub_fire.add_argument(
        "--start-offset", type=int, default=0,
        help="Resume from this offset after silent hang.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.cmd == "register":
        jid = asyncio.run(_register_jurisdiction())
        print(f"\njurisdiction_id={jid}")
        return 0
    elif args.cmd == "preflight":
        return asyncio.run(_preflight())
    elif args.cmd == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing without --i-know-this-writes-to-prod", file=sys.stderr)
            return 2
        jid = asyncio.run(_register_jurisdiction())
        return asyncio.run(_fire(jid, start_offset=args.start_offset))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
