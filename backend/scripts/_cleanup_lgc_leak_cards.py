"""One-off board cleanup: remove stale Deal Pipeline cards left by the LGC
sibling-leak demotion (QC 2026-07-21).

Context: `_demote_lgc_sibling_leaks.py` demoted luxury_garage_condo rows whose
sibling `self_storage` was human-verified prohibited on a NON-industrial zone
(the Brink Rd leak). After the county re-score those parcels are no longer
lead-eligible on the LGC lane — but `dashboard_push.run_push` is UPSERT-ONLY, so
their cards linger on the board (`_cleanup_delisted` only sweeps *delisted*
listings, not score drops). This removes exactly those now-ineligible cards.

Safe + surgical:
  1. Resolve the demoted parcels (parcels whose (city, zoning_code) matches a
     matrix row carrying the QC demotion note) from ParcelLogic's DB.
  2. Run a fresh `run_push` so every CURRENTLY eligible deal is re-upserted with
     `last_synced_at = now()` (a 'both' parcel still eligible via self_storage is
     refreshed and thus preserved).
  3. Delete only demoted-parcel cards that are still `status='new'` AND were NOT
     refreshed by that push (`last_synced_at < push start`) — i.e. no longer
     eligible under any dashboard filter. A card the owner triaged (any non-'new'
     status) is never touched.

Requires PORTFOLIO_DASHBOARD_DATABASE_URL (the dashboard's separate Supabase) —
run it where that is set (Railway / dashboard env). Dry-run by default; --apply
to delete.
"""
from __future__ import annotations

import argparse
import asyncio

import asyncpg

from app.services.dashboard_push import _dashboard_dsn, _pl_dsn, run_push

_QC_NOTE_MARKER = "sibling leak vs human-verified"


async def _demoted_parcel_ids() -> list[int]:
    conn = await asyncpg.connect(_pl_dsn())
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT p.id
              FROM zone_use_matrix m
              JOIN parcels p
                ON p.jurisdiction_id = m.jurisdiction_id
               AND p.zoning_code = m.zone_code
               AND (m.municipality = p.city OR m.municipality IS NULL)
             WHERE m.deleted_at IS NULL
               AND m.notes LIKE '%' || $1 || '%'
            """,
            _QC_NOTE_MARKER,
        )
    finally:
        await conn.close()
    return [r["id"] for r in rows]


async def main(apply: bool) -> None:
    dsn = _dashboard_dsn()
    if not dsn:
        print("PORTFOLIO_DASHBOARD_DATABASE_URL unset — run where the dashboard DSN is set.")
        return

    demoted = await _demoted_parcel_ids()
    print(f"demoted parcels (from QC note): {len(demoted)}")
    if not demoted:
        return

    conn = await asyncpg.connect(dsn, ssl="require")
    try:
        before = await conn.fetch(
            "SELECT parcel_id, city, state, score, asset_type, status "
            "FROM deal_prospect WHERE parcel_id = ANY($1::bigint[]) ORDER BY score DESC",
            demoted,
        )
        print(f"demoted parcels currently on board: {len(before)}")
        for r in before:
            print(f"  {r['parcel_id']} {r['city']},{r['state']} "
                  f"score={r['score']} asset={r['asset_type']} status={r['status']}")

        # Fresh push: re-upserts every currently-eligible deal with last_synced_at=now().
        push_start = await conn.fetchval("SELECT now()")
        print(f"\nrunning run_push (push_start={push_start}) ...")
        result = await run_push(force=True)
        print(f"run_push: {result}")

        # Cards that are demoted-parcel, still 'new', and were NOT refreshed by the
        # push (last_synced_at < push_start) => no longer eligible => stale leak cards.
        stale = await conn.fetch(
            "SELECT parcel_id, city, state, asset_type FROM deal_prospect "
            "WHERE parcel_id = ANY($1::bigint[]) AND status = 'new' "
            "AND last_synced_at < $2",
            demoted, push_start,
        )
        print(f"\nstale leak cards to remove: {len(stale)}")
        for r in stale:
            print(f"  DELETE {r['parcel_id']} {r['city']},{r['state']} asset={r['asset_type']}")

        if not apply:
            print("\nDRY-RUN — re-run with --apply to delete.")
            return
        if stale:
            ids = [r["parcel_id"] for r in stale]
            await conn.execute(
                "DELETE FROM deal_prospect WHERE parcel_id = ANY($1::bigint[]) "
                "AND status = 'new' AND last_synced_at < $2",
                ids, push_start,
            )
            print(f"\nAPPLIED: deleted {len(ids)} stale leak card(s).")
        else:
            print("\nnothing stale — board already clean.")
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="perform the delete (default: dry-run)")
    args = ap.parse_args()
    asyncio.run(main(args.apply))
