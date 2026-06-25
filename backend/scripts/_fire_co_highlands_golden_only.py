"""Phase-committed slim runner for Highlands Ranch + Golden — post #355 merge.

The trio adapter (perm_co_front_range_carry.py, merged via #355) fires
Douglas + Arapahoe + Jefferson + Highlands Ranch + Cherry Hills + Golden
in ONE transaction. For our current prod state that's problematic:

1. Arapahoe County, CO umbrella already holds 231,430 parcels from
   arapahoegov.com OpenDataService (raw schema PIN/PARCEL_ID/City).
   Re-ingesting from CO Public Parcels statewide would INSERT another
   ~231k rows with the dashed parcel_id APN scheme — bloating Arapahoe
   to ~462k.
2. Cherry Hills Village JID + 2,229 parcels + 1,153 zoning_districts
   were already established via PR #385 / _fire_cherry_hills_only.py.
3. Arapahoe County Zoning layer 89 has OID field drift OBJECTID -> FID
   (last edit 2025-10-23) not landed in #355. Cherry Hills zoning
   ingest within the trio fire would crash and roll back the whole
   transaction.

This runner sidesteps all three by firing only the Douglas + Jefferson
slices of the trio adapter, phase-committed:

  Phase 1:  Register Douglas + Jefferson umbrellas + Highlands Ranch
            + Golden per-muni JIDs.
  Phase 2D: Ingest Douglas County parcels.
  Phase 2J: Ingest Jefferson County parcels.
  Phase 3HR: Move Highlands Ranch parcels from Douglas umbrella.
  Phase 3G:  Move Golden parcels from Jefferson umbrella.
  Phase 4HR: Highlands Ranch zoning ingest + prune + spatial backfill + bbox.
  Phase 4G:  Golden zoning ingest + prune + spatial backfill + bbox.

Each phase opens its own connection and commits independently.

Englewood (PR #368) fires separately via perm_muni_englewood_co_zoning.py.
Cherry Hills was already fired; verify only.
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


# Import the trio adapter as a module to reuse helpers + ZoningSourceConfig etc.
_ADAPTER_PATH = Path(__file__).resolve().parent / "perm_co_front_range_carry.py"
_spec = importlib.util.spec_from_file_location("trio", _ADAPTER_PATH)
trio = importlib.util.module_from_spec(_spec)
sys.modules["trio"] = trio
_spec.loader.exec_module(trio)


REQUEST_TIMEOUT = httpx.Timeout(120.0)


def _county(name: str):
    return next(c for c in trio.COUNTIES if c.name == name)


def _muni(name: str):
    return next(m for m in trio.MUNIS if m.name == name)


async def _open() -> asyncpg.Connection:
    return await asyncpg.connect(_session_db_url(), statement_cache_size=0)


async def phase1_register() -> dict[str, str]:
    conn = await _open()
    out: dict[str, str] = {}
    try:
        async with conn.transaction():
            for cname in ("Douglas County, CO", "Jefferson County, CO"):
                county = _county(cname)
                jid = await trio._register_or_get_jurisdiction(
                    conn,
                    name=county.name,
                    county=county.county,
                    parcel_endpoint=trio.CO_PUBLIC_PARCELS_LAYER,
                    zoning_endpoint=None,
                    coverage_level="parcels_only",
                )
                out[cname] = jid
            for mname in ("Highlands Ranch, CO", "Golden, CO"):
                muni = _muni(mname)
                jid = await trio._register_or_get_jurisdiction(
                    conn,
                    name=muni.name,
                    county=muni.county,
                    parcel_endpoint=trio.CO_PUBLIC_PARCELS_LAYER,
                    zoning_endpoint=muni.zoning.layer_url,
                    coverage_level="full",
                )
                out[mname] = jid
            print(f"[phase1] JIDs: {out}")
            return out
    finally:
        await conn.close()


async def phase2_ingest_county(cname: str, county_jid: str) -> int:
    county = _county(cname)
    conn = await _open()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0;")
            await conn.execute(trio._CREATE_STAGE_SQL)
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                total = await trio._ingest_county_parcels(
                    conn, client, county, county_jid
                )
            print(f"[phase2] {cname} parcels ingested: {total:,}")
            return total
    finally:
        await conn.close()


async def phase3_move_muni(mname: str, county_jid: str, muni_jid: str) -> dict:
    muni = _muni(mname)
    conn = await _open()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0;")
            res = await trio._move_muni_parcels(
                conn,
                parent_jid=county_jid,
                muni_jid=muni_jid,
                muni=muni,
            )
            print(f"[phase3] {mname} move: {res}")
            return res
    finally:
        await conn.close()


async def phase4_muni_zoning(mname: str, muni_jid: str, *, skip_prune: bool = False) -> dict:
    muni = _muni(mname)
    conn = await _open()
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0;")
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                source = muni.zoning
                count = await trio._fetch_count(client, source.layer_url, source.where)
                print(f"[phase4] {mname} zoning source count: {count}")
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
                        total += await trio._insert_zoning(conn, muni_jid, patched)
                print(f"[phase4] {mname} zoning upserted: {total:,}")
            if skip_prune:
                pruned = 0
                print(f"[phase4] {mname} PRUNE SKIPPED")
            else:
                pruned = await trio._prune_muni_zoning(
                    conn, jurisdiction_id=muni_jid, muni=muni
                )
            backfill = await trio._backfill_muni_zoning(
                conn, jurisdiction_id=muni_jid, muni=muni
            )
            await trio._update_bbox(conn, muni_jid, muni.name)
            print(
                f"[phase4] {mname} pruned={pruned} contained={backfill['contained']} "
                f"nearest_50m={backfill['nearest_50m']}"
            )
            return {"upserted": total, "pruned": pruned, **backfill}
    finally:
        await conn.close()


async def _find_jids(conn: asyncpg.Connection) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in (
        "Douglas County, CO",
        "Jefferson County, CO",
        "Highlands Ranch, CO",
        "Golden, CO",
    ):
        jid = await conn.fetchval(
            "SELECT id::text FROM jurisdictions WHERE name=$1 AND state='CO' LIMIT 1",
            name,
        )
        if jid:
            out[name] = jid
    return out


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--i-know-this-writes-to-prod", action="store_true")
    p.add_argument(
        "--phase",
        choices=[
            "1",
            "2d",
            "2j",
            "3hr",
            "3g",
            "4hr",
            "4g",
            "all",
        ],
        default="all",
    )
    p.add_argument("--skip-prune", action="store_true")
    args = p.parse_args()

    if not args.i_know_this_writes_to_prod:
        raise SystemExit("Refusing to run without --i-know-this-writes-to-prod")

    print("=== CO Front Range Highlands Ranch + Golden slim runner ===")

    jids: dict[str, str] = {}

    if args.phase in ("1", "all"):
        jids = await phase1_register()

    if not jids:
        conn = await _open()
        try:
            jids = await _find_jids(conn)
        finally:
            await conn.close()

    if args.phase in ("2d", "all"):
        await phase2_ingest_county("Douglas County, CO", jids["Douglas County, CO"])

    if args.phase in ("2j", "all"):
        await phase2_ingest_county("Jefferson County, CO", jids["Jefferson County, CO"])

    if args.phase in ("3hr", "all"):
        await phase3_move_muni(
            "Highlands Ranch, CO",
            jids["Douglas County, CO"],
            jids["Highlands Ranch, CO"],
        )

    if args.phase in ("3g", "all"):
        await phase3_move_muni(
            "Golden, CO",
            jids["Jefferson County, CO"],
            jids["Golden, CO"],
        )

    if args.phase in ("4hr", "all"):
        await phase4_muni_zoning("Highlands Ranch, CO", jids["Highlands Ranch, CO"], skip_prune=args.skip_prune)

    if args.phase in ("4g", "all"):
        await phase4_muni_zoning("Golden, CO", jids["Golden, CO"], skip_prune=args.skip_prune)

    print("=== done ===")


if __name__ == "__main__":
    asyncio.run(main())
