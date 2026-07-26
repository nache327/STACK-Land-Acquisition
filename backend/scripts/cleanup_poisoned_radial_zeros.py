"""One-shot cleanup: NULL the population=0 rows written by the PRE-FIX radial
backfill, so they stop reading as a measured "too rural".

Why these rows are untrustworthy. The old backfill wrote
COALESCE(SUM(...), 0) and could reach 0 three ways that are NOT "genuinely
rural":
  * the jurisdiction's census fetch failed but the INSERT ran anyway;
  * the parcel's own tract had NULL population, so the ring sum silently
    excluded its own residents (tc_pop filtered NULL-pop tracts, tc_all did not);
  * only unpopulated neighbours happened to fall inside the ring.
A measured 0 is load-bearing downstream: it costs -20 in the score and (until the
2026-07-25 remediation) hard-dropped the parcel from the board. NULL is the
honest encoding for "we could not measure this" — it earns a soft flag instead.

So: set population = NULL for every radius=3.0 row currently sitting at 0. The
FIXED backfill can then re-derive, and will write a 0 only where it is now
provably correct (the parcel's own tract has known population and no populated
tract lies within 3 miles). Parcels it cannot measure keep NULL.

Deliberately does NOT touch sqft_per_capita: the audit confirmed 0 such rows
exist, because the saturation pass never ran broadly.

Idempotent (re-running finds nothing). Reports before/after counts.

USAGE (from backend/):
    python scripts/cleanup_poisoned_radial_zeros.py            # dry run
    python scripts/cleanup_poisoned_radial_zeros.py --apply
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


_BY_JURISDICTION = """
    SELECT COALESCE(j.name, '(unknown)') AS name,
           p.jurisdiction_id::text       AS jid,
           count(*)                      AS n
      FROM parcel_radial_metrics pr
      JOIN parcels p ON p.id = pr.parcel_id
      LEFT JOIN jurisdictions j ON j.id = p.jurisdiction_id
     WHERE pr.radius_miles = 3.0 AND pr.population = 0
     GROUP BY 1, 2
     ORDER BY n DESC
"""

_NULL_OUT = """
    UPDATE parcel_radial_metrics
       SET population = NULL, computed_at = now()
     WHERE radius_miles = 3.0 AND population = 0
"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Without this the script only reports.")
    args = ap.parse_args()

    conn = await asyncpg.connect(get_sync_dsn(), timeout=30)
    try:
        await conn.execute("SET statement_timeout = 0")

        rows = await conn.fetch(_BY_JURISDICTION)
        total = sum(r["n"] for r in rows)
        if not total:
            print("Nothing to clean: no radius=3.0 rows with population = 0.")
            return 0

        print(f"{total:,} suspect population=0 row(s) across "
              f"{len(rows)} jurisdiction(s):")
        for r in rows:
            print(f"  {r['n']:>7,}  {r['name']}  ({r['jid'][:8]})")

        # Also report the saturation column, which the audit found clean — so a
        # regression here would be visible rather than assumed away.
        sat_zeros = await conn.fetchval(
            "SELECT count(*) FROM parcel_radial_metrics "
            " WHERE radius_miles = 3.0 AND sqft_per_capita = 0"
        )
        print(f"\nsqft_per_capita = 0 rows: {sat_zeros:,} "
              f"({'expected 0 — saturation pass never ran broadly' if not sat_zeros else 'UNEXPECTED — investigate before re-running saturation'})")

        if not args.apply:
            print("\nDRY RUN — re-run with --apply to NULL these population values.")
            print("Then re-derive honestly:")
            print("  python scripts/backfill_radial_population.py --redo "
                  "--skip-saturation --jurisdiction <jid>   # per affected jid")
            return 0

        status = await conn.execute(_NULL_OUT)
        remaining = await conn.fetchval(
            "SELECT count(*) FROM parcel_radial_metrics "
            " WHERE radius_miles = 3.0 AND population = 0"
        )
        nulls = await conn.fetchval(
            "SELECT count(*) FROM parcel_radial_metrics "
            " WHERE radius_miles = 3.0 AND population IS NULL"
        )
        print(f"\n{status} — population=0 rows remaining: {remaining:,}; "
              f"radius=3.0 rows now NULL (unmeasured): {nulls:,}")
        print("Next: re-run the FIXED backfill with --redo for the jurisdictions "
              "listed above so measurable parcels get an honest value.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
