"""Repair parcels.acres where an older ingest left it 0/NULL but a valid geom exists.

Several pre-geom-fallback per-city/county ingests (Seattle, Detroit, Minneapolis,
Bay Area, Pittsburgh clusters + Hingham MA) stored acres=0 straight from the source
assessor field and never ran the geodetic fallback that `ingestion._resolve_acres`
now applies. The needle gate uses `acres >= 1.5` (HARD), so acres=0 silently zeroes
every needle in those jurisdictions despite correct zoning + grounding.

This backfill reproduces exactly what current ingest would write: geodetic area on
the WGS84 ellipsoid, `ST_Area(geom::geography)/4046.86` (== ingestion._geom_acres via
pyproj Geod). It ONLY touches rows where acres IS NULL OR acres = 0 AND geom is present
(idempotent; re-runnable; never overwrites a real assessor acreage).

Usage:
    python scripts/_backfill_acres_from_geom.py            # DRY RUN (counts only)
    python scripts/_backfill_acres_from_geom.py --apply     # write
    python scripts/_backfill_acres_from_geom.py --apply --jurisdiction <jid>   # one jid
"""
from __future__ import annotations

import argparse
import asyncio

import asyncpg
from _db import get_sync_dsn

# 4046.8564224 m^2 per acre (matches ingestion._SQM_PER_ACRE).
_SQM_PER_ACRE = 4046.8564224

_WHERE = "(p.acres IS NULL OR p.acres = 0) AND p.geom IS NOT NULL"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run counts only)")
    ap.add_argument("--jurisdiction", help="limit to one jurisdiction_id")
    args = ap.parse_args()

    c = await asyncpg.connect(get_sync_dsn())
    await c.execute("SET statement_timeout = 0")  # session-mode; big geodetic updates

    jfilter = "AND j.id = $1::uuid" if args.jurisdiction else ""
    params = [args.jurisdiction] if args.jurisdiction else []

    rows = await c.fetch(
        f"""
        SELECT j.id, j.state, j.name,
               count(p.id) FILTER (WHERE {_WHERE}) AS broken
        FROM jurisdictions j JOIN parcels p ON p.jurisdiction_id = j.id
        WHERE TRUE {jfilter}
        GROUP BY j.id, j.state, j.name
        HAVING count(p.id) FILTER (WHERE {_WHERE}) > 0
        ORDER BY count(p.id) FILTER (WHERE {_WHERE}) DESC
        """,
        *params,
    )
    total = sum(r["broken"] for r in rows)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] {len(rows)} jurisdictions, {total} broken rows to repair\n")

    for r in rows:
        print(f"  {r['state']:2} {r['name'][:34]:34} {r['broken']:>9}", flush=True)
        if args.apply:
            res = await c.execute(
                f"""
                UPDATE parcels p
                   SET acres = round((ST_Area(p.geom::geography) / {_SQM_PER_ACRE})::numeric, 3),
                       updated_at = now()
                 WHERE p.jurisdiction_id = $1
                   AND (p.acres IS NULL OR p.acres = 0)
                   AND p.geom IS NOT NULL
                """,
                r["id"],
            )
            print(f"       -> {res}", flush=True)

    if not args.apply:
        print("\n(dry run — re-run with --apply to write)")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
