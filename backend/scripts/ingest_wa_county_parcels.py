"""Phase 6B.1 — Multi-county Puget Sound parcel ingest (Pierce / Snohomish / Kitsap).

Master authorized Tier 2 multi-county carry after PR #264 (King Phase 6A.2).
The Phase 6A.2 bonus probe confirmed all 4 Puget Sound counties pass the
strengthened Class A bbox primitive (King 95.7%, Pierce 96.3%,
Snohomish 93.3%, Kitsap 89.9%). The Washington State Current Parcels
statewide source carries all 4 under one adapter shape — this script
is the parametrized clone of `ingest_king_wa_parcels.py` (PR #259) with
`--county` (one of Pierce / Snohomish / Kitsap) selecting the
`COUNTY_NM` filter and jurisdiction name at fire time.

Source layer:

    Washington State Current Parcels FeatureServer/0 (Parcels_2026)
    https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Current_Parcels/FeatureServer/0

Live probes (PR #259 bonus + PR #264 carry):
  - Pierce    (COUNTY_NM='53'): 339,590 parcels
  - Snohomish (COUNTY_NM='61'): 318,594 parcels
  - Kitsap    (COUNTY_NM='35'): 139,602 parcels

Standalone — same Python 3.9 / PEP-604 compat pattern as PR #250 + PR #259.

Subcommands per county:

  register  Idempotent. Finds/INSERTs the jurisdiction row.
  preflight Read-only 1,000-row pipeline shape check. NO DB WRITES.
  fire      Real prod ingest. Requires --i-know-this-writes-to-prod.
            COPY-upsert paginated 50k batches. Inline jurisdictions.bbox
            UPDATE at end (codified per PR #261 + PR #264).

Field mapping (same as King WA):
  PARCEL_ID_NR → apn  ·  SITUS_CITY_NM (title()) → city
  SITUS_ADDRESS → address  ·  LANDUSE_CD → land_use_code
  VALUE_LAND+VALUE_BLDG → assessed_value  ·  VALUE_BLDG → improvement_value
  DATA_LINK → county_link  ·  all 17 source fields → raw (Norfolk gate)

Title-case discipline (PR #233 lesson) — preserved verbatim from King
adapter so Phase 6B.2 zoning backfill can use exact-equality joins
against WAZA's `Jurisdiction` field convention.
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

logger = logging.getLogger("wa_county_ingest")

LAYER_URL = (
    "https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/"
    "Current_Parcels/FeatureServer/0"
)

# Per-county static config. Bbox sanity-check range used during inline
# bbox UPDATE (PR #261 lesson) — narrow but tolerant enough for the
# real Puget Sound extents probed in PR #264.
COUNTIES: dict[str, dict[str, Any]] = {
    "Pierce": {
        "county_nm": "53",
        "jur_name": "Pierce County, WA",
        "expected_count": 339_590,
        "bbox_lon_range": (-123.5, -120.5),
        "bbox_lat_range": (46.0, 48.0),
    },
    "Snohomish": {
        "county_nm": "61",
        "jur_name": "Snohomish County, WA",
        "expected_count": 318_594,
        "bbox_lon_range": (-123.0, -120.0),
        "bbox_lat_range": (47.0, 49.0),
    },
    "Kitsap": {
        "county_nm": "35",
        "jur_name": "Kitsap County, WA",
        "expected_count": 139_602,
        "bbox_lon_range": (-124.0, -122.0),
        "bbox_lat_range": (47.0, 48.5),
    },
}

JUR_STATE = "WA"
PAGE_SIZE = 2000
BATCH_SIZE = 50_000

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


def _classify_residential(use_code: int | None) -> bool | None:
    if use_code is None:
        return None
    try:
        u = int(use_code)
    except (TypeError, ValueError):
        return None
    return 11 <= u <= 29


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


def _map_row(props: dict[str, Any], geom: Any, jid: uuid.UUID) -> dict[str, Any] | None:
    apn = props.get("PARCEL_ID_NR")
    if not apn:
        return None
    apn = str(apn).strip()
    if not apn:
        return None

    use_code = _safe_int(props.get("LANDUSE_CD"))
    land_value = _safe_float(props.get("VALUE_LAND"))
    bldg_value = _safe_float(props.get("VALUE_BLDG"))
    assessed_value = None
    if land_value is not None or bldg_value is not None:
        assessed_value = (land_value or 0) + (bldg_value or 0)
        if assessed_value <= 0:
            assessed_value = None

    has_structure = bldg_value > 0 if bldg_value is not None else None

    situs_city = props.get("SITUS_CITY_NM")
    city = str(situs_city).strip().title() if situs_city and str(situs_city).strip() else None

    address = props.get("SITUS_ADDRESS")
    if address:
        address = str(address).strip() or None

    data_link = props.get("DATA_LINK")
    if data_link and not str(data_link).startswith(("http://", "https://")):
        data_link = "https://" + str(data_link)

    raw = {k: (str(v) if v is not None else None) for k, v in props.items()
           if k not in ("geometry",)}

    return {
        "jurisdiction_id": str(jid),
        "apn": apn,
        "address": address,
        "city": city,
        "owner_name": None,
        "zoning_code": None,
        "zone_class": None,
        "land_use_code": str(use_code) if use_code is not None else None,
        "acres": None,
        "county_link": data_link,
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": has_structure,
        "improvement_value": bldg_value,
        "assessed_value": assessed_value,
        "is_residential": _classify_residential(use_code),
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


async def _register_jurisdiction(county: str) -> uuid.UUID:
    cfg = COUNTIES[county]
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=60)
    try:
        existing = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
            cfg["jur_name"], JUR_STATE,
        )
        if existing:
            jid = existing["id"]
            logger.info("Found existing jurisdiction: %s -> %s", cfg["jur_name"], jid)
            return jid
        jid = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO jurisdictions (id, name, state, county, parcel_endpoint)
            VALUES ($1::uuid, $2, $3, $4, $5)
            """,
            str(jid), cfg["jur_name"], JUR_STATE, county, LAYER_URL,
        )
        logger.info("Registered new jurisdiction: %s -> %s", cfg["jur_name"], jid)
        return jid
    finally:
        await conn.close()


async def _fetch_total_count(client: httpx.AsyncClient, county_nm: str) -> int:
    r = await client.get(
        f"{LAYER_URL}/query",
        params={"where": f"COUNTY_NM='{county_nm}'", "returnCountOnly": "true", "f": "json"},
    )
    r.raise_for_status()
    n = int(r.json().get("count") or 0)
    return n


async def _fetch_page_by_offset(
    client: httpx.AsyncClient, county_nm: str, offset: int,
) -> list[dict[str, Any]]:
    r = await client.get(
        f"{LAYER_URL}/query",
        params={
            "where": f"COUNTY_NM='{county_nm}'", "outFields": "*",
            "returnGeometry": "true", "outSR": "4326", "f": "geojson",
            "resultOffset": offset, "resultRecordCount": PAGE_SIZE,
            "orderByFields": "OBJECTID",
        },
    )
    r.raise_for_status()
    return r.json().get("features", [])


async def _fetch_batch_by_offset(
    client: httpx.AsyncClient, county_nm: str, offset: int, n: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    fetched = 0
    while fetched < n:
        feats = await _fetch_page_by_offset(client, county_nm, offset + fetched)
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


async def _update_bbox(jid: uuid.UUID, county: str) -> bool:
    """Inline jurisdictions.bbox UPDATE (PR #261 + PR #264 codified pattern).

    Computed [minLng, minLat, maxLng, maxLat] from ST_Extent over the
    county's parcels.geom. Sanity-checks the bbox falls in the
    configured Puget Sound range before writing.
    """
    cfg = COUNTIES[county]
    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        ext = await conn.fetchrow(
            """
            SELECT
                ST_XMin(ST_Extent(geom)) AS minx,
                ST_YMin(ST_Extent(geom)) AS miny,
                ST_XMax(ST_Extent(geom)) AS maxx,
                ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels
            WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            str(jid),
        )
        if ext is None or ext["minx"] is None:
            print(f"HALT: no parcel geometry for {county}", file=sys.stderr)
            return False
        bbox = [
            float(ext["minx"]), float(ext["miny"]),
            float(ext["maxx"]), float(ext["maxy"]),
        ]
        lon_lo, lon_hi = cfg["bbox_lon_range"]
        lat_lo, lat_hi = cfg["bbox_lat_range"]
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            print(
                f"HALT: {county} bbox {bbox} outside expected range "
                f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})",
                file=sys.stderr,
            )
            return False
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(jid), json.dumps(bbox),
        )
        print(f"[{county}] jurisdictions.bbox UPDATEd: {bbox}")
        return True
    finally:
        await conn.close()


# ────────────────────────────────────────────────────────────────────────────
# Pre-flight
# ────────────────────────────────────────────────────────────────────────────


async def _preflight(county: str) -> int:
    cfg = COUNTIES[county]
    print(f"\n=== PRE-FLIGHT: {cfg['jur_name']} Current_Parcels ingest ===\n")
    fake_jid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(
            f"{LAYER_URL}/query",
            params={
                "where": f"COUNTY_NM='{cfg['county_nm']}'", "outFields": "*",
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
    print(f"\nDistinct SITUS_CITY_NM (title-cased) in sample: {len(cities)}")
    for c, n in sorted(cities.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:25s} {n}")
    print("\n(NO DB WRITES — pipeline shape validated)")
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Fire
# ────────────────────────────────────────────────────────────────────────────


async def _fire(jid: uuid.UUID, county: str) -> int:
    cfg = COUNTIES[county]
    print(f"\n=== FIRE: {cfg['jur_name']} Current_Parcels ingest → jurisdiction {jid} ===\n")
    started = time.time()
    total_ingested = 0
    total_apn_skipped = 0
    total_geom_skipped = 0

    async with httpx.AsyncClient(timeout=180.0) as client:
        total = await _fetch_total_count(client, cfg["county_nm"])
        if total == 0:
            print(f"Source returned count=0 for COUNTY_NM='{cfg['county_nm']}' — bailing",
                  file=sys.stderr)
            return 1
        print(f"Total features under filter COUNTY_NM='{cfg['county_nm']}': {total:,}")

        batch_idx = 0
        for batch_start in range(0, total, BATCH_SIZE):
            batch_idx += 1
            t0 = time.time()
            feats = await _fetch_batch_by_offset(
                client, cfg["county_nm"], batch_start, BATCH_SIZE,
            )
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
                logger.warning("Batch %d produced 0 mappable rows — skipping", batch_idx)
                continue
            n = await _copy_upsert(list(rows_by_apn.values()))
            t3 = time.time()
            total_ingested += n
            print(
                f"  [{county}] Batch {batch_idx:>2} | feats {len(feats):>6} "
                f"| geom_skip {geom_skipped:>4} | apn_skip {apn_skipped:>4} "
                f"| mapped {n_to_upsert:>6} | upserted {n:>6} "
                f"| fetch {t1-t0:5.1f}s | map {t2-t1:5.1f}s "
                f"| copy {t3-t2:5.1f}s | cumulative {total_ingested:>7}",
                flush=True,
            )

    elapsed = time.time() - started
    print(f"\n=== [{county}] Ingest complete: {total_ingested:,} parcels upserted "
          f"in {elapsed/60:.1f} min ===")
    print(f"  total_geom_skipped : {total_geom_skipped}")
    print(f"  total_apn_skipped  : {total_apn_skipped}")

    # Inline jurisdictions.bbox UPDATE (PR #261 + PR #264 codified pattern)
    print(f"\n[{county}] Inline jurisdictions.bbox UPDATE…")
    if not await _update_bbox(jid, county):
        return 5
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for sub_name in ("register", "preflight"):
        s = sub.add_parser(sub_name)
        s.add_argument("--county", required=True, choices=list(COUNTIES.keys()))
    sub_fire = sub.add_parser("fire")
    sub_fire.add_argument("--county", required=True, choices=list(COUNTIES.keys()))
    sub_fire.add_argument(
        "--i-know-this-writes-to-prod", action="store_true",
        help="Confirmation flag. Required because this writes parcel "
             "rows + jurisdictions.bbox on prod.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.cmd == "register":
        jid = asyncio.run(_register_jurisdiction(args.county))
        print(f"\njurisdiction_id={jid}")
        return 0
    elif args.cmd == "preflight":
        return asyncio.run(_preflight(args.county))
    elif args.cmd == "fire":
        if not args.i_know_this_writes_to_prod:
            print("Refusing to fire without --i-know-this-writes-to-prod",
                  file=sys.stderr)
            return 2
        jid = asyncio.run(_register_jurisdiction(args.county))
        return asyncio.run(_fire(jid, args.county))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
