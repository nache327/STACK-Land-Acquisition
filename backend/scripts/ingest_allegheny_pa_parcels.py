"""Phase 7F.1 — Allegheny County, PA parcel ingest + jurisdiction registration.

Wave 5 dispatch per Master's 2026-06-19 final-wedge-wave directive. Closes
the 25-muni wedge cohort. Allegheny PA per Diagnostic PR (acquisition spec)
— SINGLE-COUNTY-PORTAL class, 580,039 parcels.

Source: Allegheny County / WPRDC OPENDATA Parcels (canonical per
Diagnostic PR acquisition spec)
  https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/
  Parcels/MapServer/0

Live probes (2026-06-19, per acquisition spec doc):
  - Layer name        : Parcel
  - Total parcel count: 580,039
  - Max records / query: 1,000
  - Spatial reference  : PA State Plane South (wkid=102729); reproject via outSR=4326
  - 5 wealth-band targets per orchestrator pre-stage d7a0c7a:
      Fox Chapel Borough (MUNICODE=868, 2,179 parcels — PRIMARY 57-list)
      O Hara Township (MUNICODE=931, adjacent — apostrophe stripped per LABEL convention)
      Aspinwall Borough (MUNICODE=801)
      Sewickley Borough (MUNICODE=851)
      Sewickley Heights Borough (MUNICODE=869 — Ordinance No. 294 PDF flagged for Phase 7F.3)

Parcel source quirk: Parcels layer has MUNICODE (integer 801/868/931/...) but
no city/municipality string. City name must be derived via lookup against
the separate Municipal Boundaries Feature Server:

  https://services1.arcgis.com/vdNDkVykv9vEWFX4/arcgis/rest/services/
  AlleghenyCountyMunicipalBoundaries/FeatureServer/0

This adapter fetches the full muni boundary table at fire start, builds
a MUNICODE → LABEL dict, then sets parcels.city = LABEL during ingest.

PA case discipline (CRITICAL — different from MN/WA/CT/AZ/MI):
  Allegheny publishes LABEL as title-case + Borough/Township suffix +
  apostrophe-to-space:
    868 → 'Fox Chapel Borough'
    931 → 'O Hara Township'         (NOT "O'Hara Township")
    851 → 'Sewickley Borough'
    869 → 'Sewickley Heights Borough'
    801 → 'Aspinwall Borough'

  Per Master's Wave 5 dispatch: PRESERVE LABEL VERBATIM — don't strip
  suffix, don't reinsert apostrophes. Phase 7F.2 per-muni registration
  uses exact-equality city='Fox Chapel Borough' joins.

Class C gate result: FAIL. Parcel fields are PIN/MAPBLOCKLOT/MUNICODE only,
no zoning. Phase 7F.3 is Class B/manual per acquisition spec (no public
countywide zoning FeatureServer). Orchestrator pre-stage d7a0c7a (26 rows
total) all LOW Path B — re-author at apply-time from ordinance.

Field mapping (Allegheny OPENDATA Parcels → parcels):

  - PIN (16-char text)              → parcels.apn
  - municode lookup → LABEL          → parcels.city
  - MAPBLOCKLOT                     → raw passthrough only
  - CALCACREAGE                     → parcels.acres
  - geometry (PA State Plane → WGS84) → parcels.geom + .centroid

raw_attributes passthrough is BOUNDED — Parcels publishes 13 fields.
Curated subset preserves PIN + MUNICODE + acreage + creation metadata.

Subcommands:
  register   Idempotent. Finds/INSERTs Allegheny County, PA in jurisdictions.
  preflight  1k-row sample with muni-map join, NO DB WRITES.
  fire       Real prod ingest with city derivation.

Hard rules honored:
  - raw_attributes preserved verbatim, bounded passthrough (Norfolk gate)
  - LABEL preserved verbatim (title-case + suffix + apostrophe-stripped)
  - Inline jurisdictions.bbox UPDATE at fire-end (PR #261 codified)
  - Skip ROLLBACK preflight at Class A scale (PR #253)
  - --start-offset resume flag for silent-hang recovery
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

logger = logging.getLogger("allegheny_pa_ingest")

LAYER_URL = (
    "https://gisdata.alleghenycounty.us/arcgis/rest/services/"
    "OPENDATA/Parcels/MapServer/0"
)
MUNI_LAYER_URL = (
    "https://services1.arcgis.com/vdNDkVykv9vEWFX4/arcgis/rest/services/"
    "AlleghenyCountyMunicipalBoundaries/FeatureServer/0"
)
COUNTY_FILTER = "1=1"
JUR_NAME = "Allegheny County, PA"
JUR_STATE = "PA"
JUR_COUNTY = "Allegheny"
PAGE_SIZE = 1000
BATCH_SIZE = 50_000

_RAW_PASSTHROUGH = (
    "PIN", "MAPBLOCKLOT", "MUNICODE", "CALCACREAGE",
    "NOTES", "PSEUDONO", "COMMENTS",
    "CREATEDBY", "CREATEDON", "MODIFIEDBY", "MODIFIEDON",
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


async def _fetch_muni_map(client: httpx.AsyncClient) -> dict[int, str]:
    """Fetch all Allegheny munis: MUNICODE → LABEL dict."""
    r = await client.get(
        f"{MUNI_LAYER_URL}/query",
        params={
            "where": "1=1", "outFields": "MUNICODE,LABEL,NAME,TYPE",
            "returnGeometry": "false", "f": "json",
            "resultRecordCount": 1000,
        },
        timeout=60.0,
    )
    r.raise_for_status()
    features = r.json().get("features", [])
    out: dict[int, str] = {}
    for f in features:
        a = f.get("attributes", {})
        code = a.get("MUNICODE")
        label = a.get("LABEL")
        if code is None or not label:
            continue
        try:
            out[int(code)] = str(label).strip()
        except (TypeError, ValueError):
            continue
    logger.info("Loaded %d Allegheny muni labels", len(out))
    return out


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
    muni_map: dict[int, str],
) -> dict[str, Any] | None:
    apn = _trim(props.get("PIN"))
    if not apn:
        return None

    municode = _safe_int(props.get("MUNICODE"))
    city = muni_map.get(municode) if municode is not None else None

    acres = _safe_float(props.get("CALCACREAGE"))
    if acres is not None and acres < 0:
        acres = None

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
        "address": None,  # Parcels layer has no address field
        "city": city,
        "owner_name": None,
        "zoning_code": None,
        "zone_class": None,
        "land_use_code": None,
        "acres": acres,
        "county_link": None,
        "in_flood_zone": None,
        "in_wetland": False,
        "avg_slope_pct": None,
        "has_structure": None,
        "improvement_value": None,
        "assessed_value": None,
        "is_residential": None,
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
        f"Allegheny ArcGIS offset={offset} failed after 5 retries: {last_exc}"
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
            logger.warning("No parcel geometry to compute Allegheny bbox from")
            return
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        # Allegheny County, PA — Pittsburgh metro
        if not (-80.5 <= bbox[0] <= -79.5 and 40.1 <= bbox[1] <= 40.8):
            raise RuntimeError(
                f"Allegheny bbox {bbox} outside expected range "
                f"(lon -80.5 to -79.5, lat 40.1 to 40.8)"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(jid), json.dumps(bbox),
        )
        logger.info("Inline jurisdictions.bbox UPDATEd: %s", bbox)
    finally:
        await conn.close()


async def _preflight() -> int:
    print("\n=== PRE-FLIGHT: Allegheny OPENDATA Parcels ingest ===\n")
    fake_jid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    async with httpx.AsyncClient(timeout=120.0) as client:
        muni_map = await _fetch_muni_map(client)
        print(f"Muni map loaded: {len(muni_map)} codes")
        # Show 5 target munis
        for code in (868, 931, 801, 851, 869):
            print(f"  {code}: {muni_map.get(code, '(missing)')!r}")
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
    print(f"\nfeatures fetched : {len(sample)}")
    mapped = []
    geom_skipped = apn_skipped = 0
    cities: dict[str, int] = {}
    for feat in sample:
        props = feat.get("properties") or {}
        geom = _parse_geom(feat.get("geometry"))
        if geom is None:
            geom_skipped += 1
            continue
        m = _map_row(props, geom, fake_jid, muni_map)
        if m is None:
            apn_skipped += 1
            continue
        mapped.append(m)
        if m.get("city"):
            cities[m["city"]] = cities.get(m["city"], 0) + 1
    print(f"geom_skipped     : {geom_skipped}")
    print(f"apn_skipped      : {apn_skipped}")
    print(f"mappable rows    : {len(mapped)}")
    print(f"\nDistinct city (LABEL — title-case + suffix) in sample: {len(cities)}")
    for c, n in sorted(cities.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:35s} {n}")
    print(f"\n5 wealth-band target munis (LABEL exact-match):")
    for muni in (
        "Fox Chapel Borough", "O Hara Township", "Aspinwall Borough",
        "Sewickley Borough", "Sewickley Heights Borough",
    ):
        print(f"  {muni:30s} (exact-match): {cities.get(muni, 0)}")
    print("\n(NO DB WRITES — pipeline shape validated)")
    return 0


async def _fire(jid: uuid.UUID, start_offset: int = 0) -> int:
    print(f"\n=== FIRE: Allegheny OPENDATA Parcels → {jid} "
          f"(start_offset={start_offset:,}) ===\n")
    started = time.time()
    total_ingested = 0
    total_apn_skipped = 0
    total_geom_skipped = 0
    async with httpx.AsyncClient(timeout=180.0) as client:
        muni_map = await _fetch_muni_map(client)
        print(f"Muni map loaded: {len(muni_map)} codes")
        r0 = await client.get(
            f"{LAYER_URL}/query",
            params={"where": COUNTY_FILTER, "returnCountOnly": "true", "f": "json"},
        )
        r0.raise_for_status()
        total = int(r0.json().get("count") or 0)
        if total == 0:
            print("Source returned count=0 — bailing", file=sys.stderr)
            return 1
        print(f"Total Allegheny features: {total:,}")
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
                m = _map_row(props, geom, jid, muni_map)
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
    await _update_bbox_inline(jid)
    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=600)
    try:
        for muni in (
            "Fox Chapel Borough", "O Hara Township", "Aspinwall Borough",
            "Sewickley Borough", "Sewickley Heights Borough",
        ):
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid AND city = $2",
                str(jid), muni,
            )
            print(f"  city={muni:30s}: {n:,} parcels (Phase 7F.2 readiness)")
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
