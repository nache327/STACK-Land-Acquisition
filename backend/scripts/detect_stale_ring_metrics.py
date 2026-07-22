"""Detect stale / mis-anchored drive-time ring rows by cross-checking the
dt=10 isochrone population against the trustworthy 3-mile radial population
(parcel_radial_metrics @ 3.0, from backfill_radial_population.py).

Why this catches real breakage: a 10-minute drive covers well beyond a
3-mile radius in suburbia, so dt10_pop < pop_3mi is (nearly) impossible —
it means the isochrone was anchored on the wrong tract centroid, or a tract
isochrone failed and left a stale/partial row. Nache found 11k@10-min next
to 49k@3-mi on a live card; that's exactly the ratio this flags.

Report-only. Emits parcel_ids for recompute_ring_population.py to fix.

USAGE (from backend/):
    python scripts/detect_stale_ring_metrics.py                    # all
    python scripts/detect_stale_ring_metrics.py --jurisdiction <uuid>
    python scripts/detect_stale_ring_metrics.py --ids-only         # bare ids
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

# dt10 population below this fraction of the 3-mi radial population is
# implausible. Tunable; Nache's live case was 11k/49k = 0.22.
INCONSISTENCY_RATIO = 0.5
MIN_POP3MI = 5000            # ignore genuinely-rural parcels where both are tiny
STALE_DAYS = 180


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", type=str, default=None)
    ap.add_argument("--ids-only", action="store_true")
    args = ap.parse_args()

    conn = await asyncpg.connect(get_sync_dsn())
    try:
        await conn.execute("SET statement_timeout = 0")
        jfilter = "AND p.jurisdiction_id = $1::uuid" if args.jurisdiction else ""
        params = [args.jurisdiction] if args.jurisdiction else []
        rows = await conn.fetch(
            f"""
            SELECT prm.parcel_id,
                   prm.population        AS dt10_pop,
                   prm3.population        AS pop_3mi,
                   prm.computed_at,
                   (prm.computed_at < NOW() - INTERVAL '{STALE_DAYS} days') AS aged,
                   p.jurisdiction_id::text AS jid
              FROM parcel_ring_metrics prm
              JOIN parcel_radial_metrics prm3
                ON prm3.parcel_id = prm.parcel_id AND prm3.radius_miles = 3.0
              JOIN parcels p ON p.id = prm.parcel_id
             WHERE prm.drive_time_minutes = 10
               {jfilter}
               AND (
                     (prm3.population > {MIN_POP3MI}
                      AND prm.population < {INCONSISTENCY_RATIO} * prm3.population)
                  OR prm.computed_at < NOW() - INTERVAL '{STALE_DAYS} days'
               )
             ORDER BY (prm.population::float / NULLIF(prm3.population, 0)) ASC
            """,
            *params,
        )
    finally:
        await conn.close()

    if args.ids_only:
        for r in rows:
            print(r["parcel_id"])
        return

    print(f"{len(rows)} stale/inconsistent dt=10 ring row(s):", flush=True)
    inconsistent = [r for r in rows if not r["aged"]]
    aged = [r for r in rows if r["aged"]]
    print(f"  {len(inconsistent)} inconsistent (dt10 << 3-mi), {len(aged)} aged (>{STALE_DAYS}d)")
    for r in rows[:50]:
        ratio = (r["dt10_pop"] or 0) / r["pop_3mi"] if r["pop_3mi"] else 0
        print(f"  {r['parcel_id']}  dt10={r['dt10_pop']}  3mi={r['pop_3mi']}  "
              f"ratio={ratio:.2f}  {r['computed_at']:%Y-%m-%d}")
    if len(rows) > 50:
        print(f"  … +{len(rows) - 50} more (use --ids-only to pipe to recompute)")


if __name__ == "__main__":
    asyncio.run(main())
