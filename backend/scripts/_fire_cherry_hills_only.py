"""One-off Cherry Hills Village CO fire — phase-committed.

Pre-fire DB probe (2026-06-24) discovered:
- Arapahoe County, CO umbrella JID 5c4b612c already has 231,430 parcels
  ingested from arapahoegov.com OpenDataService (NOT CO Public Parcels
  statewide). raw schema uses PIN/PARCEL_ID/City — APN keys incompatible
  with the trio adapter's statewide source.
- Cherry Hills parcels live under raw->>'City'='CHERRYHILLSVILLAGE'
  (2,229 parcels with geometry).

This runner commits each phase independently so session interruption
doesn't roll back prior work:

Phase 1: Register Cherry Hills Village JID (idempotent).
Phase 2: UPDATE parcels.jurisdiction_id by raw->>'City' filter.
Phase 3: Ingest Cherry Hills zoning from Arapahoe layer 89 (FID, FID-corrected).
Phase 4: Prune + spatial backfill + bbox.

Each phase is rerun-safe via ON CONFLICT / idempotent UPDATEs.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import asyncpg
import httpx
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


_ADAPTER_PATH = Path(__file__).resolve().parent / "perm_co_arapahoe_cherry_hills_standalone.py"
_spec = importlib.util.spec_from_file_location("standalone", _ADAPTER_PATH)
standalone = importlib.util.module_from_spec(_spec)
sys.modules["standalone"] = standalone
_spec.loader.exec_module(standalone)


ARAPAHOE_JID = "5c4b612c-a5a7-47dc-af9f-b955d97c3d4e"
ARAPAHOE_PARCEL_ENDPOINT = (
    "https://gis.arapahoegov.com/arcgis/rest/services/OpenDataService/FeatureServer/0"
)
CHERRY_HILLS_NAME = "Cherry Hills Village, CO"
CHERRY_HILLS_COUNTY = "Arapahoe"
RAW_CITY_KEY = "CHERRYHILLSVILLAGE"

REQUEST_TIMEOUT = httpx.Timeout(120.0)


def _cherry_muni():
    return next(m for m in standalone.MUNIS if m.name == CHERRY_HILLS_NAME)


async def _open() -> asyncpg.Connection:
    return await asyncpg.connect(_session_db_url(), statement_cache_size=0)


async def _find_cherry_jid(conn: asyncpg.Connection) -> str | None:
    row = await conn.fetchval(
        "SELECT id::text FROM jurisdictions WHERE name=$1 AND state='CO' LIMIT 1",
        CHERRY_HILLS_NAME,
    )
    return row


async def phase1_register() -> str:
    conn = await _open()
    try:
        async with conn.transaction():
            cherry_muni = _cherry_muni()
            jid = await standalone._register_or_get_jurisdiction(
                conn,
                name=CHERRY_HILLS_NAME,
                county=CHERRY_HILLS_COUNTY,
                parcel_endpoint=ARAPAHOE_PARCEL_ENDPOINT,
                zoning_endpoint=cherry_muni.zoning.layer_url,
                coverage_level="full",
            )
            print(f"[phase1] Cherry Hills JID: {jid}")
            return jid
    finally:
        await conn.close()


async def phase2_move(cherry_jid: str) -> int:
    conn = await _open()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0;")
            moved = await conn.fetchval(
                """
                WITH moved AS (
                    UPDATE parcels
                    SET jurisdiction_id = $2::uuid,
                        city = 'Cherry Hills Village',
                        state = 'CO',
                        updated_at = NOW()
                    WHERE jurisdiction_id = $1::uuid
                      AND raw->>'City' = $3
                    RETURNING 1
                )
                SELECT COUNT(*)::INTEGER FROM moved
                """,
                ARAPAHOE_JID,
                cherry_jid,
                RAW_CITY_KEY,
            )
            print(f"[phase2] PATH 1 moved {moved:,} Cherry Hills parcels")
            return int(moved)
    finally:
        await conn.close()


async def phase3_zoning(cherry_jid: str) -> int:
    conn = await _open()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0;")
            cherry_muni = _cherry_muni()
            source = cherry_muni.zoning
            total = 0
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                count = await standalone._fetch_count(
                    client, source.layer_url, source.where
                )
                print(f"[phase3] source count: {count}")
                async for page in standalone._iter_features(
                    client,
                    source.layer_url,
                    source.where,
                    object_id_field=source.object_id_field,
                ):
                    for feature in page:
                        row = standalone._zone_row(feature, cherry_muni)
                        if not row:
                            continue
                        code, zone_name, zone_class, geom_wkt, raw_json, geom_hash = row
                        if zone_class is None:
                            zone_class = "unknown"
                        patched_row = (
                            code,
                            zone_name,
                            zone_class,
                            geom_wkt,
                            raw_json,
                            geom_hash,
                        )
                        total += await standalone._insert_zoning(
                            conn, cherry_jid, patched_row
                        )
            print(f"[phase3] upserted {total:,} zoning_districts")
            return total
    finally:
        await conn.close()


async def phase4_prune_backfill_bbox(cherry_jid: str) -> dict:
    conn = await _open()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0;")
            cherry_muni = _cherry_muni()
            pruned = await standalone._prune_muni_zoning(
                conn, jurisdiction_id=cherry_jid, muni=cherry_muni
            )
            backfill = await standalone._backfill_muni_zoning(
                conn, jurisdiction_id=cherry_jid, muni=cherry_muni
            )
            await standalone._update_bbox(conn, cherry_jid, CHERRY_HILLS_NAME)
            print(
                f"[phase4] pruned={pruned} contained={backfill['contained']} "
                f"nearest_50m={backfill['nearest_50m']}"
            )
            return {"pruned": pruned, **backfill}
    finally:
        await conn.close()


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--i-know-this-writes-to-prod", action="store_true")
    p.add_argument("--phase", choices=["1", "2", "3", "4", "all"], default="all")
    args = p.parse_args()

    if not args.i_know_this_writes_to_prod:
        raise SystemExit("Refusing to run without --i-know-this-writes-to-prod")

    print("=== Cherry Hills Village CO fire (phase-committed) ===")
    cherry_jid = None
    if args.phase in ("1", "all"):
        cherry_jid = await phase1_register()
    if args.phase in ("2", "all"):
        if cherry_jid is None:
            conn = await _open()
            try:
                cherry_jid = await _find_cherry_jid(conn)
            finally:
                await conn.close()
            if not cherry_jid:
                raise SystemExit("Cherry Hills JID not registered; run phase 1 first")
        await phase2_move(cherry_jid)
    if args.phase in ("3", "all"):
        if cherry_jid is None:
            conn = await _open()
            try:
                cherry_jid = await _find_cherry_jid(conn)
            finally:
                await conn.close()
        await phase3_zoning(cherry_jid)
    if args.phase in ("4", "all"):
        if cherry_jid is None:
            conn = await _open()
            try:
                cherry_jid = await _find_cherry_jid(conn)
            finally:
                await conn.close()
        await phase4_prune_backfill_bbox(cherry_jid)
    print("=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
