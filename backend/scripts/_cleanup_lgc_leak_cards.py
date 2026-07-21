"""One-off board cleanup for the viability-gate rollout (QC 2026-07-21).

Context: the board/digest now HARD-GATES out any parcel whose effective
use-verdict is 'prohibited' (see daily_email._top_parcels_for_filter). But
dashboard_push.run_push is UPSERT-ONLY — it stops RE-ADDING the now-ineligible
cards, yet the ones already on the board linger (`_cleanup_delisted` only sweeps
*delisted* listings, not gated/score-dropped ones). This removes exactly the
cards the current selection no longer includes.

Safe + surgical:
  1. Run a fresh `run_push` so every CURRENTLY eligible deal is re-upserted with
     `last_synced_at = now()`.
  2. Delete only cards that are still `status='new'` (never triaged by the owner)
     AND were NOT refreshed by that push (`last_synced_at < push start`) — i.e.
     no longer eligible under any dashboard filter (prohibited-gated, score-
     dropped, or delisted). A card the owner moved to ANY other status is never
     touched.

This is the correct general fix for upsert-only staleness, run once at the gate
rollout. Requires PORTFOLIO_DASHBOARD_DATABASE_URL (the dashboard's separate
Supabase) — run where that is set (Railway / dashboard env). Dry-run by default;
--apply to delete.
"""
from __future__ import annotations

import argparse
import asyncio

import asyncpg

from app.services.dashboard_push import _dashboard_dsn, run_push


async def main(apply: bool) -> None:
    dsn = _dashboard_dsn()
    if not dsn:
        print("PORTFOLIO_DASHBOARD_DATABASE_URL unset — run where the dashboard DSN is set.")
        return

    conn = await asyncpg.connect(dsn, ssl="require")
    try:
        before = await conn.fetchval(
            "SELECT count(*) FROM deal_prospect WHERE status = 'new'")
        push_start = await conn.fetchval("SELECT now()")
        print(f"status='new' cards before: {before}")
        print(f"running run_push (push_start={push_start}) ...")
        result = await run_push(force=True)
        print(f"run_push: {result}")

        stale = await conn.fetch(
            "SELECT parcel_id, city, state, asset_type, use_verdict, score "
            "FROM deal_prospect WHERE status = 'new' AND last_synced_at < $1 "
            "ORDER BY score DESC NULLS LAST",
            push_start,
        )
        print(f"\nstale (ineligible, untriaged) cards to remove: {len(stale)}")
        for r in stale[:40]:
            print(f"  DELETE {r['parcel_id']} {r['city']},{r['state']} "
                  f"asset={r['asset_type']} verdict={r['use_verdict']} score={r['score']}")
        if len(stale) > 40:
            print(f"  … and {len(stale) - 40} more")

        # Sanity: is Brink Rd (Germantown MD, parcel 6580269) among them / gone?
        brink = await conn.fetchrow(
            "SELECT status, last_synced_at < $1 AS stale FROM deal_prospect "
            "WHERE parcel_id = 6580269", push_start)
        print(f"\nBrink Rd (6580269): {dict(brink) if brink else 'not on board'}")

        if not apply:
            print("\nDRY-RUN — re-run with --apply to delete.")
            return
        if stale:
            await conn.execute(
                "DELETE FROM deal_prospect WHERE status = 'new' AND last_synced_at < $1",
                push_start,
            )
            print(f"\nAPPLIED: deleted {len(stale)} stale card(s).")
        else:
            print("\nnothing stale — board already clean.")
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="perform the delete (default: dry-run)")
    args = ap.parse_args()
    asyncio.run(main(args.apply))
