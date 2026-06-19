"""Phase 7B.1 — Maricopa County, AZ parcel ingest + jurisdiction registration.

Master Wave 2 dispatch after Hennepin MN wave per Diagnostic PR #232 + PR #262.
Maricopa is the second massive-county-with-wealth-pocket Op-5 target
(Scottsdale 150,207 + Paradise Valley 10,071 + Cave Creek + Fountain Hills
+ Carefree per orchestrator's 301-row pre-stage at commits 20dacfc + 9af5827).

Source layer:

    Maricopa County Assessor / GIS Parcel_Data_View
    https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/
    Parcel_Data_View/FeatureServer/0

Live probes (2026-06-11 per PR #232, re-validated 2026-06-18):
  - Total parcel count : 1,742,671 (single-county; SINGLE-COUNTY-PORTAL class)
  - Max records / query: 2,000
  - Spatial reference  : Arizona Central State Plane (wkid=2868)
  - Server-side reprojection to WGS84 via outSR=4326 confirmed working
  - 5 wealth-band munis (per orchestrator's pre-stage):
      SCOTTSDALE      150,207
      PARADISE VALLEY  10,071
      CAVE CREEK        ~5,300
      FOUNTAIN HILLS   ~10,400
      CAREFREE          ~2,000

Standalone script (PR #250 / PR #259 / Hennepin Phase 7A.1 pattern).
COPY-upsert via asyncpg directly, preserving production `_stage_parcels`
shape verbatim.

Field mapping (Maricopa Parcel_Data_View → parcels):

  - APN (numeric, e.g. '13031006D')             → parcels.apn
  - PropertyCity (UPPERCASE verbatim)           → parcels.city
  - PropertyFullStreetAddress                   → parcels.address
  - OwnerName                                   → parcels.owner_name
  - LandLegalClassCode                          → parcels.land_use_code
  - FullCashValue                               → parcels.assessed_value
  - ImprovementFullCashValue                    → parcels.improvement_value
  - LotSize_Acre                                → parcels.acres
  - geometry (reprojected → WGS84)              → parcels.geom + .centroid
  - bounded subset of source fields             → parcels.raw (Norfolk gate)

Case discipline (CRITICAL — different from MN/WA/CT):
  Maricopa publishes PropertyCity in UPPERCASE ('SCOTTSDALE', 'PARADISE VALLEY').
  Per Master's Wave 2 dispatch: PRESERVE UPPERCASE — do NOT title-case.
  This is the AZ convention, codified for Phase 7B.2 per-muni registration
  (UPDATE jurisdiction_id WHERE city='SCOTTSDALE'). Same UPPERCASE pattern
  expected to extend to all AZ counties (Pima, Pinal future waves).

is_residential heuristic via AZ Legal Class Code (LandLegalClassCode):
  3 = Owner-occupied residential                   → True
  4 = Non-owner-occupied (rental) residential      → True
  1 = Commercial / Industrial                      → False
  2 = Vacant land / Agricultural                   → None (vacant uncertain)
  5 = Railroad / Mines / Utilities                 → False
  6 = Historic / Agricultural / Religious          → None
  others                                           → None
  See https://azdor.gov/property/property-tax for canonical codes.

has_structure: ImprovementFullCashValue > 0 → True; ==0 → False; else None.

Scottsdale prefilter gate (per PR #232 risk register):
  Scottsdale PropertyCity='SCOTTSDALE' parcel bbox FAILS the 50% Class A
  primitive against the city zoning layer. Postal-city noise extends well
  beyond actual city limits. This Phase 7B.1 ingests ALL Maricopa parcels;
  Phase 7B.2 per-muni registration of Scottsdale uses
  ingest_maricopa_az_city_limits.py to spatial-join against the canonical
  Maricopa County Reference/ParcelCityCounty/MapServer/1 layer
  (CityName='SCOTTSDALE'), same shape as PR #285 Pierce Task E. Paradise
  Valley, Cave Creek, Fountain Hills, Carefree are expected to pass without
  prefilter (smaller, tighter postal-city alignment).

raw_attributes passthrough is BOUNDED — Parcel_Data_View publishes 95+
fields per parcel; bounded 24-field subset preserves operational utility
(assessor + tax + use code) without bloat.

Subcommands:

  register   Idempotent. Finds/INSERTs Maricopa County, AZ in jurisdictions.
  preflight  1k-row sample, NO DB WRITES. UPPERCASE + wealth-muni readiness.
  fire       Real prod ingest. Requires --i-know-this-writes-to-prod.
             Paginates the all-Maricopa filter in 50k-feature batches.
             Use --start-offset to resume after silent hang.

Hard rules honored:
  - raw_attributes preserved verbatim, bounded passthrough (Norfolk gate)
  - PropertyCity preserved UPPERCASE (AZ discipline per Master)
  - No zoning data written (Phase 7B.3 is separate)
  - One refresh per task (operator manual at end)
  - Inline jurisdictions.bbox UPDATE at end (PR #261 codified)
  - Skip in-DB ROLLBACK preflight at Class A scale (PR #253)
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

logger = logging.getLogger("maricopa_az_ingest")

LAYER_URL = (
    "https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/"
    "Parcel_Data_View/FeatureServer/0"
)
COUNTY_FILTER = "1=1"
JUR_NAME = "Maricopa County, AZ"
JUR_STATE = "AZ"
JUR_COUNTY = "Maricopa"
PAGE_SIZE = 2000
BATCH_SIZE = 50_000

# Bounded raw_attributes passthrough — operationally useful fields only.
_RAW_PASSTHROUGH = (
    "APN", "APNDash", "APNDashSplit",
    "PropertyFullStreetAddress", "PropertyCity", "PropertyZipCode",
    "OwnerName",
    "PropertyUseCode", "PropertyUseDescription",
    "LandLegalClassCode", "LandLegalClassDescription",
    "ImprovementLegalClassCode", "ImprovementLegalClassDescription",
    "TaxingDistrictCode", "TaxingDistrictDescription",
    "FullCashValue", "LimitedPropertyValue",
    "LandFullCashValue", "ImprovementFullCashValue",
    "ConstructionYear", "LivableArea_SqFt", "LotSize_SqFt", "LotSize_Acre",
    "SubdivisionName",
)

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


def _classify_residential(land_class: str | None) -> bool | None:
    """AZ Legal Class Code → is_residential.

    3 = Owner-occupied residential          → True
    4 = Non-owner-occupied rental res       → True
    1 = Commercial / Industrial             → False
    5 = Railroad / Mines / Utilities        → False
    2 = Vacant / Agricultural               → None
    6 = Historic / Religious                → None
    """
    if not land_class:
        return None
    code = str(land_class).strip().upper()
    if not code:
        return None
    first = code[0]
    if first in ("3", "4"):
        return True
    if first in ("1", "5"):
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
    apn = _trim(props.get("APN"))
    if not apn:
        return None

    # CRITICAL: preserve UPPERCASE per Master's AZ case-discipline directive.
    # Do NOT call .title() here. Per-muni Phase 7B.2 registration uses
    # exact-equality city='SCOTTSDALE' joins.
    city = _trim(props.get("PropertyCity"))

    address = _trim(props.get("PropertyFullStreetAddress"))
    owner = _trim(props.get("OwnerName"))
    land_class = _trim(props.get("LandLegalClassCode"))
    full_cash = _safe_float(props.get("FullCashValue"))
    impr_cash = _safe_float(props.get("ImprovementFullCashValue"))
    lot_acres = _safe_float(props.get("LotSize_Acre"))

    assessed_value = full_cash
    if assessed_value is not None and assessed_value <= 0:
        assessed_value = None

    has_structure = None
    if impr_cash is not None:
        has_structure = impr_cash > 0

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
        "land_use_code": land_class,
        "acres": lot_acres,
        "county_link": None,
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": impr_cash,
        "assessed_value": assessed_value,
        "is_residential": _classify_residential(land_class),
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


async def _fetch_total_count(client: httpx.AsyncClient) -> int:
    r = await client.get(
        f"{LAYER_URL}/query",
        params={"where": COUNTY_FILTER, "returnCountOnly": "true", "f": "json"},
    )
    r.raise_for_status()
    n = int(r.json().get("count") or 0)
    logger.info("Maricopa filter '%s' count: %d", COUNTY_FILTER, n)
    return n


async def _fetch_page_by_offset(
    client: httpx.AsyncClient, offset: int,
) -> list[dict[str, Any]]:
    """Retry with exponential backoff (Hennepin precedent)."""
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
                    "orderByFields": "OBJECTID",
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
        f"Maricopa ArcGIS offset={offset} failed after 5 retries: {last_exc}"
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
    """PR #261 codified — set jurisdictions.bbox at fire time."""
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=300)
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
            logger.warning("No parcel geometry to compute Maricopa bbox from")
            return
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        # Maricopa County, AZ — Phoenix metro
        # Full extent per PR #232: [-113.354, 32.687, -111.076, 34.044]
        if not (-113.5 <= bbox[0] <= -111.0 and 32.5 <= bbox[1] <= 34.5):
            raise RuntimeError(
                f"Maricopa bbox {bbox} outside expected range "
                f"(lon -113.5 to -111.0, lat 32.5 to 34.5)"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(jid), json.dumps(bbox),
        )
        logger.info("Inline jurisdictions.bbox UPDATEd: %s", bbox)
    finally:
        await conn.close()


async def _preflight() -> int:
    """Pipeline-shape validation only. PR #253 lesson: skip prod ROLLBACK
    preflight at Class A scale. NO DB WRITES."""
    print("\n=== PRE-FLIGHT: Maricopa Parcel_Data_View ingest ===\n")
    fake_jid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(
            f"{LAYER_URL}/query",
            params={
                "where": COUNTY_FILTER, "outFields": "*",
                "returnGeometry": "true", "outSR": "4326",
                "f": "geojson", "resultRecordCount": 1000,
                "orderByFields": "OBJECTID",
            },
        )
        r.raise_for_status()
        sample = r.json().get("features", [])
    print(f"features fetched : {len(sample)}")

    mapped = []
    geom_skipped = apn_skipped = 0
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
        print(f"raw_attributes field-count avg/min/max: "
              f"{avg:.1f} / {min(raw_field_counts)} / {max(raw_field_counts)}")

    print(f"\nDistinct PropertyCity (UPPERCASE verbatim) in sample: {len(cities)}")
    for c, n in sorted(cities.items(), key=lambda x: -x[1])[:20]:
        print(f"  {c:25s} {n}")

    print(f"\n5 wealth-band target cities in 1k sample (early offsets):")
    for muni in ("SCOTTSDALE", "PARADISE VALLEY", "CAVE CREEK",
                 "FOUNTAIN HILLS", "CAREFREE"):
        print(f"  {muni:18s} (UPPERCASE exact match): {cities.get(muni, 0)}")

    if mapped:
        sample_one = {k: v for k, v in mapped[0].items()
                      if k not in ("geom", "centroid", "raw")}
        raw_keys = list(mapped[0]["raw"].keys())
        sample_one["raw"] = f"<{len(raw_keys)} keys: {raw_keys[:6]}…>"
        print("\nSample mapped row:")
        for k, v in sample_one.items():
            print(f"  {k:20s} = {v!r}")

    print("\n(NO DB WRITES — pipeline shape validated)")
    return 0


async def _fire(jid: uuid.UUID, start_offset: int = 0) -> int:
    print(f"\n=== FIRE: Maricopa Parcel_Data_View ingest → jurisdiction {jid} "
          f"(start_offset={start_offset:,}) ===\n")
    started = time.time()
    total_ingested = 0
    total_apn_skipped = 0
    total_geom_skipped = 0

    async with httpx.AsyncClient(timeout=180.0) as client:
        total = await _fetch_total_count(client)
        if total == 0:
            print("Source returned count=0 — bailing", file=sys.stderr)
            return 1
        print(f"Total features under filter '{COUNTY_FILTER}': {total:,}")

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
                f"  Batch {batch_idx:>3} | offset {batch_start:>9,} "
                f"| feats {len(feats):>6} "
                f"| geom_skip {geom_skipped:>4} | apn_skip {apn_skipped:>4} "
                f"| mapped {n_to_upsert:>6} | upserted {n:>6} "
                f"| fetch {t1-t0:5.1f}s | map {t2-t1:5.1f}s "
                f"| copy {t3-t2:5.1f}s | cumulative {total_ingested:>8,}",
                flush=True,
            )

    elapsed = time.time() - started
    print(f"\n=== Fire complete: {total_ingested:,} parcels upserted "
          f"in {elapsed/60:.1f} min ===")
    print(f"  total_geom_skipped : {total_geom_skipped}")
    print(f"  total_apn_skipped  : {total_apn_skipped}")

    await _update_bbox_inline(jid)

    # Wealth-band readiness summary (Phase 7B.2 will use these)
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0)
    try:
        for muni in ("SCOTTSDALE", "PARADISE VALLEY", "CAVE CREEK",
                     "FOUNTAIN HILLS", "CAREFREE"):
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid AND city = $2",
                str(jid), muni,
            )
            print(f"  city={muni:18s}: {n:,} parcels (Phase 7B.2 readiness)")
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
        help="Confirmation flag. Required because this writes ~1.74M parcel "
             "rows to prod.",
    )
    sub_fire.add_argument(
        "--start-offset", type=int, default=0,
        help="Resume from this paging offset (idempotent — earlier batches "
             "are skipped). Use after a hung fire to avoid re-COPY'ing "
             "already-upserted rows.",
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
        return asyncio.run(_fire(jid, start_offset=args.start_offset))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
