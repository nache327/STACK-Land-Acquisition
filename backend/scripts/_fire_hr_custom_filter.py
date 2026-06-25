"""Custom-filter Highlands Ranch move + zoning ingest.

Douglas County umbrella JID was pre-populated with 152,441 parcels from
Douglas County's own GIS (raw schema Account_Fact_CITY_NAME, PARCELS_*),
NOT from CO Public Parcels statewide (raw schema sitAddCty, parcel_id).
The trio adapter's _move_muni_parcels filter on sitAddCty / city='Highlands
Ranch' returns 0 — refuses fire.

This runner moves by raw->>'Account_Fact_CITY_NAME'='HIGHLANDS RANCH'
(30,699 parcels) and reuses trio helpers for zoning ingest + backfill.

Phase-committed.
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


_ADAPTER_PATH = Path(__file__).resolve().parent / "perm_co_front_range_carry.py"
_spec = importlib.util.spec_from_file_location("trio", _ADAPTER_PATH)
trio = importlib.util.module_from_spec(_spec)
sys.modules["trio"] = trio
_spec.loader.exec_module(trio)


DOUGLAS_JID = "ec296fd0-d042-4fbb-aea7-6bf7242a6c45"
HR_JID = "524b1948-f806-4007-b7e3-6ef7219c2b2c"
RAW_CITY_KEY = "HIGHLANDS RANCH"


def _hr_muni():
    return next(m for m in trio.MUNIS if m.name == "Highlands Ranch, CO")


async def _open():
    return await asyncpg.connect(_session_db_url(), statement_cache_size=0)


async def move():
    conn = await _open()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0;")
            moved = await conn.fetchval(
                """
                WITH moved AS (
                    UPDATE parcels SET
                        jurisdiction_id = $2::uuid,
                        city = 'Highlands Ranch',
                        state = 'CO',
                        updated_at = NOW()
                    WHERE jurisdiction_id = $1::uuid
                      AND raw->>'Account_Fact_CITY_NAME' = $3
                    RETURNING 1
                )
                SELECT COUNT(*)::INTEGER FROM moved
                """,
                DOUGLAS_JID,
                HR_JID,
                RAW_CITY_KEY,
            )
            print(f"[move] Highlands Ranch moved: {moved:,}")
            return int(moved)
    finally:
        await conn.close()


async def zoning(skip_prune: bool):
    muni = _hr_muni()
    conn = await _open()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0;")
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                source = muni.zoning
                count = await trio._fetch_count(client, source.layer_url, source.where)
                print(f"[zoning] HR source count: {count}")
                total = 0
                async for page in trio._iter_features(
                    client,
                    source.layer_url,
                    source.where,
                    object_id_field=source.object_id_field,
                ):
                    for feature in page:
                        row = trio._zone_row(feature, muni)
                        if not row:
                            continue
                        code, zone_name, zone_class, geom_wkt, raw_json, geom_hash = row
                        if zone_class is None:
                            zone_class = "unknown"
                        patched = (code, zone_name, zone_class, geom_wkt, raw_json, geom_hash)
                        total += await trio._insert_zoning(conn, HR_JID, patched)
                print(f"[zoning] HR upserted: {total:,}")
            pruned = 0
            if skip_prune:
                print("[zoning] HR prune skipped")
            else:
                pruned = await trio._prune_muni_zoning(
                    conn, jurisdiction_id=HR_JID, muni=muni
                )
            backfill = await trio._backfill_muni_zoning(
                conn, jurisdiction_id=HR_JID, muni=muni
            )
            await trio._update_bbox(conn, HR_JID, muni.name)
            print(
                f"[zoning] HR pruned={pruned} contained={backfill['contained']} "
                f"nearest_50m={backfill['nearest_50m']}"
            )
            return {"upserted": total, "pruned": pruned, **backfill}
    finally:
        await conn.close()


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--i-know-this-writes-to-prod", action="store_true")
    p.add_argument("--step", choices=["move", "zoning", "all"], default="all")
    p.add_argument("--skip-prune", action="store_true")
    args = p.parse_args()
    if not args.i_know_this_writes_to_prod:
        raise SystemExit("Refusing")
    if args.step in ("move", "all"):
        await move()
    if args.step in ("zoning", "all"):
        await zoning(args.skip_prune)


if __name__ == "__main__":
    asyncio.run(main())
