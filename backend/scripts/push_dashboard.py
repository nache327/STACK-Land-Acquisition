"""Push current buy-box deals to the dashboard board (Deal Pipeline).

WHY A SCRIPT WRAPPER: run_push lives in app/services/dashboard_push.py and needs
PORTFOLIO_DASHBOARD_DATABASE_URL, which is set on RAILWAY and not on dev machines
— run it locally and it no-ops with "unset — skipping". The maintenance runner
(app/services/maintenance_jobs.py) resolves jobs to `scripts/<name>.py`, so this
thin wrapper is what lets the board be pushed on demand via
POST /api/admin/maintenance/run, in the environment that actually holds the DSN.

SAFE FOR TRIAGED CARDS — verified 2026-07-28 before first use:
  * the ONLY DELETE against deal_prospect is _cleanup_delisted, and it requires
    `status = 'new' AND listing_source IS NOT NULL` in BOTH the candidate SELECT
    and the DELETE itself (a deliberate race guard), so a card moved to
    reviewing / loi_sent / watching / under_contract / passed / dead is never
    removed;
  * a parcel falling OUT of the buy-box filter is not deleted at all, at any
    status — run_push only ever UPSERTs, there is no prune step;
  * the disposition columns (status / note / owner_contact / decided_*) appear in
    neither _FACT_COLUMNS nor the ON CONFLICT DO UPDATE set, so a re-sync cannot
    clobber a decision. The listing-derived column is deliberately named
    owner_contact_listing to avoid colliding with the manual owner_contact.
  It DOES refresh the fact columns, so scores/tiers on triaged cards will move
  after a re-score. That is intended; it is not data loss.

USAGE (from backend/):
    python scripts/push_dashboard.py                 # all dashboardEnabled filters
    python scripts/push_dashboard.py --filter-id 3   # one filter (smoke test)

Prints the run summary as JSON so the maintenance runner's captured log carries
the counts (deals synced, dispositions, per-filter detail).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from app.services.dashboard_push import run_push  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser(
        description="Push buy-box deals to the dashboard Deal Pipeline board.")
    # buybox_filters.id is a UUID. This wrapper originally declared type=int,
    # mirroring the same mistake in dashboard_push's own CLI — an int can never
    # match the uuid PK, so --filter-id selected nothing. Fixed in two of the
    # three places first; this was the third.
    ap.add_argument("--filter-id", type=str, default=None,
                    help="Sync a single buybox_filters.id, a UUID (smoke test / "
                         "backfill). Omit to sync every dashboardEnabled filter.")
    args = ap.parse_args()

    result = await run_push(force=True, filter_id=args.filter_id)
    print(json.dumps(result, indent=2, default=str), flush=True)

    if result.get("status") == "skipped":
        # Loud, because the usual cause is running it somewhere without the DSN,
        # where it silently does nothing.
        print(f"\nSKIPPED: {result.get('reason')} — "
              f"PORTFOLIO_DASHBOARD_DATABASE_URL is not set in this environment. "
              f"The board push must run where that DSN exists (Railway).",
              flush=True)
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
