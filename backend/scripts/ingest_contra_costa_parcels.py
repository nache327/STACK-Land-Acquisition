"""Phase 5A.1 — Contra Costa County, CA parcel ingest + jurisdiction registration.

Predecessor: PR #242 (Task 5 Phase 2 HALT — prerequisite gap). Master
authorized Path 5A (split): this dispatch handles parcel ingest + jurisdiction
registration only; the Phase 5A.2 zoning backfill (CA Statewide Zoning North
Class A) waits for a follow-up dispatch on the now-staged parcels.

Source layer:

    CCMAP Assessment Parcels MapServer/0
    https://ccmap.cccounty.us/arcgis/rest/services/CCMAP/Assessment_Parcels_ArcPro/MapServer/0

Live probes (2026-06-11 in PR #242):
  - Total feature count : 387,835
  - Max record count    : 2,000 per query
  - Spatial reference   : Web Mercator (wkid=102100; latestWkid=3857)
  - Bbox (WGS84)        : [-122.439, 37.712, -121.533, 38.102]
  - Field count         : 50

This script is **standalone** — it does the COPY-upsert directly against
the prod DB via asyncpg (avoiding the geopandas runtime dependency and the
Python 3.10+ type syntax in `app.services.ingestion`). Reuses the
production `_stage_parcels` shape and `INSERT … ON CONFLICT … DO UPDATE`
upsert pattern verbatim so the resulting rows are indistinguishable from
those that come through the SQLAlchemy path.

CCMAP → parcels field mapping (Contra Costa specific):

  - APN                       → parcels.apn
  - s_city (title-cased)      → parcels.city
  - full_address_display      → parcels.address
  - USE_CODE (str)            → parcels.land_use_code
  - ACREAGE                   → parcels.acres
  - IMP_VAL                   → parcels.improvement_value
  - LAND_VALUE + IMP_VAL      → parcels.assessed_value
  - assr_url                  → parcels.county_link
  - geometry (WGS84)          → parcels.geom + parcels.centroid
  - all 50 source fields      → parcels.raw (Norfolk gate)

is_residential is derived from Contra Costa assessor use codes: CA
property classes 11-19 are single-family / residential; 21-29 multi-
family; 50-59 mixed-use w/ residential. Conservative threshold per
land use category; orchestrator can refine.

s_city is normalised to title case ("WALNUT CREEK" → "Walnut Creek") on
ingest. PR #233 lesson: prod_city_value must match the downstream zoning
layer's case convention exactly. CA Statewide Zoning North uses title
case for `Jurisdiction` values — so Phase 5A.2 can use exact-equality
joins.

Subcommands:

  register   Idempotent. Finds or INSERTs the Contra Costa, CA row in
             `jurisdictions`. Prints the jurisdiction_id.

  preflight  Read-only. Pulls a 1,000-row sample, validates geometries,
             reports field distributions + sample mapped row. NO DB
             WRITES.

  fire       Real prod ingest. Requires --i-know-this-writes-to-prod
             confirmation. Paginates the full layer in 50,000-feature
             batches and upserts via COPY into `_stage_parcels` →
             `parcels` (idempotent on conflict).

Hard rules honoured:
  - raw_attributes preserved verbatim (Norfolk gate)
  - s_city title-cased before ingest (PR #233 lesson)
  - No zoning data written (Phase 5A.2 is a separate dispatch)
  - One refresh per task (operator fires at end manually)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from shapely.geometry import shape
from shapely.wkb import dumps as wkb_dumps
from shapely import make_valid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import only `settings` — avoids the geopandas / typing chain.
import os
import dotenv
# Repo root .env carries the prod Supabase connection string.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("contra_costa_ingest")

LAYER_URL = (
    "https://ccmap.cccounty.us/arcgis/rest/services/CCMAP/"
    "Assessment_Parcels_ArcPro/MapServer/0"
)
JUR_NAME = "Contra Costa County, CA"
JUR_STATE = "CA"
JUR_COUNTY = "Contra Costa"

PAGE_SIZE = 2000
BATCH_SIZE = 50_000

# Mirror app/services/ingestion.py:_STAGE_COLUMNS exactly.
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


# ────────────────────────────────────────────────────────────────────────────
# Field mapping (Contra Costa specific)
# ────────────────────────────────────────────────────────────────────────────


def _classify_residential(use_code: int | None) -> bool | None:
    """Contra Costa assessor use code → is_residential.

    Reference: California assessor use codes (county-published) commonly group
    11-19 single-family, 21-29 multi-family, 71-79 government, 41-49
    commercial, 51-59 mixed-use, 61-69 agriculture, 81-89 vacant.
    The Description field carries the human label per parcel.
    """
    if use_code is None:
        return None
    try:
        u = int(use_code)
    except (TypeError, ValueError):
        return None
    if 11 <= u <= 29:
        return True
    if 51 <= u <= 59:
        return True  # mixed-use w/ residential
    return False


def _classify_vacant(use_code: int | None, description: str | None) -> bool | None:
    """Contra Costa use code → has_structure (True/False/None).

    81-89 generally vacant land; we also look for "Vacant" in Description.
    Returns has_structure (True if not vacant; None if unknown).
    """
    if use_code is None:
        return None
    try:
        u = int(use_code)
    except (TypeError, ValueError):
        u = None
    is_vacant = False
    if u is not None and 80 <= u <= 89:
        is_vacant = True
    elif description and "vacant" in str(description).lower():
        is_vacant = True
    elif u is None and not description:
        return None
    return not is_vacant


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


def _map_row(
    props: dict[str, Any],
    geom: Any,
    jid: uuid.UUID,
) -> dict[str, Any] | None:
    """Build a parcels-row dict for one CCMAP feature. None if unusable."""
    apn = props.get("APN")
    if not apn:
        return None
    apn = str(apn).strip()
    if not apn:
        return None

    use_code = _safe_int(props.get("USE_CODE"))
    description = props.get("Description")
    land_value = _safe_float(props.get("LAND_VALUE"))
    imp_val = _safe_float(props.get("IMP_VAL"))
    assessed_value = None
    if land_value is not None or imp_val is not None:
        assessed_value = (land_value or 0) + (imp_val or 0)
        if assessed_value <= 0:
            assessed_value = None

    s_city = props.get("s_city")
    if s_city is not None and str(s_city).strip():
        city = str(s_city).strip().title()
    else:
        city = None

    address = props.get("full_address_display")
    if address:
        address = str(address).strip() or None

    assr_url = props.get("assr_url")
    if assr_url and not str(assr_url).startswith(("http://", "https://")):
        assr_url = "https://" + str(assr_url)

    acres = _safe_float(props.get("ACREAGE"))
    if acres is not None and acres <= 0:
        acres = None

    has_structure = _classify_vacant(use_code, description)
    is_residential = _classify_residential(use_code)

    raw = {k: (str(v) if v is not None else None) for k, v in props.items()
           if k not in ("geometry",)}

    return {
        "jurisdiction_id": str(jid),
        "apn": apn,
        "address": address,
        "city": city,
        "owner_name": None,  # CCMAP doesn't publish per-parcel owner
        "zoning_code": None,
        "zone_class": None,
        "land_use_code": str(use_code) if use_code is not None else None,
        "acres": acres,
        "county_link": assr_url,
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": imp_val,
        "assessed_value": assessed_value,
        "is_residential": is_residential,
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


# ────────────────────────────────────────────────────────────────────────────
# Jurisdiction registration
# ────────────────────────────────────────────────────────────────────────────


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


# ────────────────────────────────────────────────────────────────────────────
# CCMAP fetch
# ────────────────────────────────────────────────────────────────────────────


async def _fetch_total_count(client: httpx.AsyncClient) -> int:
    r = await client.get(
        f"{LAYER_URL}/query",
        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
    )
    r.raise_for_status()
    n = int(r.json().get("count") or 0)
    logger.info("CCMAP total feature count: %d", n)
    return n


async def _fetch_page_by_offset(
    client: httpx.AsyncClient, offset: int,
) -> list[dict[str, Any]]:
    """Fetch one page via resultOffset/resultRecordCount.

    ArcGIS REST sorts by OBJECTID ascending by default when orderByFields
    is omitted (most layers; CCMAP confirmed by Phase 1 preview shape).
    Explicit orderByFields=OBJECTID makes the iteration deterministic.
    """
    r = await client.get(
        f"{LAYER_URL}/query",
        params={
            "where": "1=1", "outFields": "*", "returnGeometry": "true",
            "outSR": "4326", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": PAGE_SIZE,
            "orderByFields": "OBJECTID",
        },
    )
    r.raise_for_status()
    return r.json().get("features", [])


async def _fetch_batch_by_offset(
    client: httpx.AsyncClient, offset: int, n: int,
) -> list[dict[str, Any]]:
    """Fetch `n` features starting at `offset` via PAGE_SIZE pages."""
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


# ────────────────────────────────────────────────────────────────────────────
# COPY-upsert
# ────────────────────────────────────────────────────────────────────────────


async def _copy_upsert(rows: list[dict[str, Any]]) -> int:
    """Stage rows via COPY into _stage_parcels, then INSERT…SELECT into parcels.

    Mirrors `app.services.ingestion._copy_upsert_parcels` shape verbatim.
    """
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
                staged = min(i + CHUNK, total)
                logger.debug("COPY staged %d/%d", staged, total)
            r = await conn.fetchval(
                "WITH ins AS (" + _MERGE_SQL + " RETURNING 1) SELECT COUNT(*) FROM ins"
            )
            return int(r or 0)
    finally:
        await conn.close()


# ────────────────────────────────────────────────────────────────────────────
# Pre-flight
# ────────────────────────────────────────────────────────────────────────────


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Contra Costa CCMAP parcel ingest ===\n")
    fake_jid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(
            f"{LAYER_URL}/query",
            params={
                "where": "1=1", "outFields": "*", "returnGeometry": "true",
                "outSR": "4326", "f": "geojson", "resultRecordCount": 1000,
            },
        )
        r.raise_for_status()
        sample = r.json().get("features", [])
    print(f"features fetched : {len(sample)}")

    mapped = []
    geom_skipped = 0
    apn_skipped = 0
    cities: dict[str, int] = {}
    raw_field_counts = []
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
        raw_field_counts.append(len(m["raw"]))

    print(f"geom_skipped     : {geom_skipped}")
    print(f"apn_skipped      : {apn_skipped}")
    print(f"mappable rows    : {len(mapped)}")
    if raw_field_counts:
        avg = sum(raw_field_counts) / len(raw_field_counts)
        print(f"raw_attributes field-count avg / min / max: "
              f"{avg:.1f} / {min(raw_field_counts)} / {max(raw_field_counts)}")

    print(f"\nDistinct s_city (title-cased) in sample: {len(cities)}")
    for c, n in sorted(cities.items(), key=lambda x: -x[1])[:20]:
        print(f"  {c:25s} {n}")
    wc = cities.get("Walnut Creek", 0)
    la = cities.get("Lafayette", 0)
    print(f"\nWalnut Creek title-case match in sample: {wc}")
    print(f"Lafayette    title-case match in sample: {la}")

    if mapped:
        sample_one = {k: v for k, v in mapped[0].items()
                      if k not in ("geom", "centroid", "raw")}
        raw_keys = list(mapped[0]["raw"].keys())
        sample_one["raw"] = f"<{len(raw_keys)} keys: {raw_keys[:6]}…>"
        print("\nSample mapped row:")
        for k, v in sample_one.items():
            print(f"  {k:20s} = {v!r}")

    print("\n(NO DB WRITES — preflight validates pipeline shape only)")
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Fire
# ────────────────────────────────────────────────────────────────────────────


async def _fire(jid: uuid.UUID) -> int:
    print(f"\n=== FIRE: Contra Costa CCMAP parcel ingest → jurisdiction {jid} ===\n")
    started = time.time()
    total_ingested = 0
    total_apn_skipped = 0
    total_geom_skipped = 0

    async with httpx.AsyncClient(timeout=180.0) as client:
        total = await _fetch_total_count(client)
        if total == 0:
            print("CCMAP returned count=0 — bailing", file=sys.stderr)
            return 1
        print(f"Total features: {total:,}")

        batch_idx = 0
        for batch_start in range(0, total, BATCH_SIZE):
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
                logger.warning("Batch %d produced 0 mappable rows — skipping",
                               batch_idx)
                continue
            n = await _copy_upsert(list(rows_by_apn.values()))
            t3 = time.time()
            total_ingested += n
            print(
                f"  Batch {batch_idx:>2} | feats {len(feats):>6} "
                f"| geom_skip {geom_skipped:>4} | apn_skip {apn_skipped:>4} "
                f"| mapped {n_to_upsert:>6} | upserted {n:>6} "
                f"| fetch {t1-t0:5.1f}s | map {t2-t1:5.1f}s "
                f"| copy {t3-t2:5.1f}s | cumulative {total_ingested:>7}",
                flush=True,
            )

    elapsed = time.time() - started
    print(f"\n=== Fire complete: {total_ingested:,} parcels upserted "
          f"in {elapsed/60:.1f} min ===")
    print(f"  total_geom_skipped : {total_geom_skipped}")
    print(f"  total_apn_skipped  : {total_apn_skipped}")
    return 0


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("register")
    sub.add_parser("preflight")
    sub_fire = sub.add_parser("fire")
    sub_fire.add_argument(
        "--i-know-this-writes-to-prod", action="store_true",
        help="Confirmation flag. Required because this writes ~387k parcel "
             "rows to prod.",
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
            print("Refusing to fire without --i-know-this-writes-to-prod",
                  file=sys.stderr)
            return 2
        jid = asyncio.run(_register_jurisdiction())
        return asyncio.run(_fire(jid))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
