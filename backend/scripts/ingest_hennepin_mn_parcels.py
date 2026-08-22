"""Phase 7A.1 — Hennepin County, MN parcel ingest + jurisdiction registration.

First MN Tier 2 dispatch. Master pivot from WA wave to MN wave after Bellevue +
Mercer Island flips clean (PRs #271, #278) and Bainbridge / Mill Creek /
Gig Harbor lined up (PRs #281, #283, #287). MetroGIS-aggregator-driven
multi-county Class A carry was the original premise per Diagnostic
PR #255 / #236, but the regional aggregator at metc.state.mn.us is gated
behind token auth and the 2023 layer returns "Service not started" —
falling back to Hennepin County direct, which is the operationally
canonical source anyway. Multi-county carry probe deferred to follow-up.

Source layer:

    Hennepin County direct (LAND_PROPERTY MapServer/1: County Parcels)
    https://gis.hennepin.us/arcgis/rest/services/HennepinData/LAND_PROPERTY/MapServer/1

Live probes (2026-06-16):
  - Total parcel count : 448,084 (single-county; not statewide)
  - Max records / query: 2,000
  - Spatial reference  : NAD83 UTM Zone 15N (wkid=26915)
  - Server-side reprojection to WGS84 via outSR=4326 confirmed working
  - 5 wealth-band munis (per Diagnostic PR #255):
      Edina        21,343
      Wayzata       1,992
      Minnetonka   20,911
      Plymouth     29,204
      Eden Prairie 22,956
    Total wealth-band: 96,406 parcels (21.5% of county)
  - Reference scale: Minneapolis = 128,750 parcels

Standalone script (PR #250 / PR #259 pattern). COPY-upsert via asyncpg
directly, preserving the production `_stage_parcels` shape + `INSERT ...
ON CONFLICT ... DO UPDATE` SQL verbatim.

Field mapping (Hennepin LAND_PROPERTY → parcels):

  - PID (13-digit text, e.g. '0411621210001') → parcels.apn
  - MUNIC_NM (ALL-CAPS, space-padded)          → parcels.city, title-cased
  - HOUSE_NO + STREET_NM                       → parcels.address
  - OWNER_NM                                   → parcels.owner_name
  - STATE_CD (integer)                         → parcels.land_use_code
  - TOTAL_MV1 (current market value, $)        → parcels.assessed_value
  - BLDG_MV1                                   → parcels.improvement_value
  - geometry (reprojected → WGS84)             → parcels.geom + .centroid
  - curated subset of source fields            → parcels.raw (Norfolk gate)

is_residential heuristic for MN DOR State Code (PR_TYP_CD1 / STATE_CD):
  - 100-199  → residential / homestead (True)
  - 200-299  → commercial (False)
  - 300-399  → industrial (False)
  - 400-499  → apartment / multifamily (True)
  - others   → None
  See https://www.revenue.state.mn.us for the canonical 100-series codes.

has_structure: BLDG_MV1 > 0 → True; BLDG_MV1 == 0 → False; else None.

Title-case discipline (PR #233 lesson):
  MUNIC_NM publishes ALL-CAPS + space-padded ('EDINA           '). Strip
  whitespace + title-case at ingest ('Edina') so Phase 7A.2 / per-muni
  re-jurisdictioning can use exact-equality joins against the city
  zoning layer's Jurisdiction field. Same approach as Contra Costa
  CCMAP s_city and WA Current Parcels SITUS_CITY_NM.

raw_attributes passthrough is BOUNDED — Hennepin LAND_PROPERTY publishes
200+ fields per parcel; passing them all through would inflate the
parcels.raw JSONB column by ~10x. Curated 19-field subset preserves
operational utility (tax + sale + property type) without bloat.

Subcommands:

  register   Idempotent. Finds/INSERTs Hennepin County, MN in jurisdictions.
  preflight  1k-row sample, NO DB WRITES. Title-case + wealth-muni readiness.
  fire       Real prod ingest. Requires --i-know-this-writes-to-prod.
             Paginates the all-Hennepin filter in 50k-feature batches.

Hard rules honored:
  - raw_attributes preserved verbatim, bounded passthrough (Norfolk gate)
  - MUNIC_NM title-cased before ingest (PR #233 lesson)
  - No zoning data written (Phase 7A.2 is separate)
  - One refresh per task (operator manual at end)
  - Inline jurisdictions.bbox UPDATE at end (PR #261 codified)
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

logger = logging.getLogger("hennepin_mn_ingest")

LAYER_URL = (
    "https://gis.hennepin.us/arcgis/rest/services/HennepinData/"
    "LAND_PROPERTY/MapServer/1"
)
COUNTY_FILTER = "1=1"  # Hennepin-direct layer is already scoped to Hennepin
JUR_NAME = "Hennepin County, MN"
JUR_STATE = "MN"
JUR_COUNTY = "Hennepin"

PAGE_SIZE = 2000
BATCH_SIZE = 50_000

# Bounded raw_attributes passthrough — operationally useful fields only.
_RAW_PASSTHROUGH = (
    "PID", "PID_TEXT", "MUNIC_NM", "MUNIC_CD", "MAILING_MUNIC_NM",
    "HOUSE_NO", "STREET_NM", "OWNER_NM", "TAXPAYER_NM",
    "STATE_CD", "FEATURECODE", "PR_TYP_CD1", "PR_TYP_NM1", "HMSTD_CD1",
    "TOTAL_MV1", "LAND_MV1", "BLDG_MV1",
    "BUILD_YR", "SALE_DATE", "SALE_PRICE",
    "PARCEL_AREA", "LAT", "LON",
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


def _classify_residential(state_cd: int | None) -> bool | None:
    """MN DOR property class → is_residential.

    100s: residential (homestead + non-homestead) → True
    400s: apartment / multifamily                 → True
    200s: commercial                              → False
    300s: industrial                              → False
    others: None (utility, agricultural, exempt)
    """
    if state_cd is None:
        return None
    try:
        u = int(state_cd)
    except (TypeError, ValueError):
        return None
    if 100 <= u <= 199 or 400 <= u <= 499:
        return True
    if 200 <= u <= 399:
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
    """Hennepin fields are space-padded fixed-width; strip + null-out empties."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _map_row(
    props: dict[str, Any],
    geom: Any,
    jid: uuid.UUID,
) -> dict[str, Any] | None:
    pid = _trim(props.get("PID"))
    if not pid:
        return None

    munic = _trim(props.get("MUNIC_NM"))
    city = munic.title() if munic else None  # PR #233 title-case discipline

    house = _safe_int(props.get("HOUSE_NO"))
    street = _trim(props.get("STREET_NM"))
    address: str | None = None
    if house is not None and house > 0 and street:
        address = f"{house} {street}"
    elif street:
        address = street

    owner = _trim(props.get("OWNER_NM"))
    state_cd = _safe_int(props.get("STATE_CD"))
    land_value = _safe_float(props.get("LAND_MV1"))
    bldg_value = _safe_float(props.get("BLDG_MV1"))
    total_value = _safe_float(props.get("TOTAL_MV1"))

    assessed_value = total_value
    if assessed_value is None and (land_value is not None or bldg_value is not None):
        assessed_value = (land_value or 0) + (bldg_value or 0)
    if assessed_value is not None and assessed_value <= 0:
        assessed_value = None

    has_structure = None
    if bldg_value is not None:
        has_structure = bldg_value > 0

    raw = {}
    for k in _RAW_PASSTHROUGH:
        v = props.get(k)
        if v is not None:
            v = str(v).strip() if isinstance(v, str) else v
            if v != "":
                raw[k] = v

    return {
        "jurisdiction_id": str(jid),
        "apn": pid,
        "address": address,
        "city": city,
        "owner_name": owner,
        "zoning_code": None,
        "zone_class": None,
        "land_use_code": str(state_cd) if state_cd is not None else None,
        "acres": None,  # Hennepin PARCEL_AREA units unverified; left null
        "county_link": None,
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": bldg_value,
        "assessed_value": assessed_value,
        "is_residential": _classify_residential(state_cd),
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
    logger.info("Hennepin filter '%s' count: %d", COUNTY_FILTER, n)
    return n


async def _fetch_page_by_offset(
    client: httpx.AsyncClient, offset: int,
) -> list[dict[str, Any]]:
    """Hennepin's ArcGIS endpoint times out intermittently under load — retry
    with exponential backoff up to 5 times, then re-raise."""
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            r = await client.get(
                f"{LAYER_URL}/query",
                params={
                    "where": COUNTY_FILTER, "outFields": "*", "returnGeometry": "true",
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
        f"Hennepin ArcGIS offset={offset} failed after 5 retries: {last_exc}"
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
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=120)
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
            logger.warning("No parcel geometry to compute Hennepin bbox from")
            return
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        # Hennepin County, MN — Twin Cities metro
        if not (-94.0 <= bbox[0] <= -93.0 and 44.6 <= bbox[1] <= 45.4):
            raise RuntimeError(
                f"Hennepin bbox {bbox} outside expected range "
                f"(lon -94.0 to -93.0, lat 44.6 to 45.4)"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(jid), json.dumps(bbox),
        )
        logger.info("Inline jurisdictions.bbox UPDATEd: %s", bbox)
    finally:
        await conn.close()


# ────────────────────────────────────────────────────────────────────────────
# Pre-flight (read-only)
# ────────────────────────────────────────────────────────────────────────────


async def _preflight() -> int:
    """Pipeline-shape validation only. PR #253 lesson: skip prod ROLLBACK
    preflight at Class A scale. NO DB WRITES."""
    print("\n=== PRE-FLIGHT: Hennepin LAND_PROPERTY ingest ===\n")
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

    print(f"\nDistinct MUNIC_NM (title-cased) in sample: {len(cities)}")
    for c, n in sorted(cities.items(), key=lambda x: -x[1])[:20]:
        print(f"  {c:25s} {n}")

    # Phase 7A.2 readiness checks
    print(f"\n5 wealth-band target cities in 1k sample (early offsets):")
    for muni in ("Edina", "Wayzata", "Minnetonka", "Plymouth", "Eden Prairie"):
        print(f"  {muni:18s} (title-case match): {cities.get(muni, 0)}")

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


# ────────────────────────────────────────────────────────────────────────────
# Fire
# ────────────────────────────────────────────────────────────────────────────


async def _fire(jid: uuid.UUID, start_offset: int = 0) -> int:
    print(f"\n=== FIRE: Hennepin LAND_PROPERTY ingest → jurisdiction {jid} "
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

    # PR #261 codified — inline bbox UPDATE at fire-end, pre-empts the
    # missing_bbox residual.
    await _update_bbox_inline(jid)

    # Wealth-band readiness summary
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0)
    try:
        for muni in ("Edina", "Wayzata", "Minnetonka", "Plymouth", "Eden Prairie"):
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid AND city = $2",
                str(jid), muni,
            )
            print(f"  city={muni:18s}: {n:,} parcels (Phase 7A.2 readiness)")
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
        help="Confirmation flag. Required because this writes ~448k parcel "
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
