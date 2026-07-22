"""Re-score every jurisdiction's parcels under the default buy-box filters.

Run this after ANY change to the composite scoring formula in
``app/services/buybox_scoring.py`` — existing ``parcel_buybox_scores`` rows
were computed with the old weights and are stale until re-scored. The daily
digest ranks off these rows, so a mixed-formula table ranks incoherently.

It simply enumerates the jurisdictions that have parcels and calls
``auto_score_jurisdiction`` for each (which scores against BOTH default
filters — self_storage and LGC — and is already advisory-locked + chunked).
Sequential by design: one heavy county at a time keeps memory bounded and
avoids hammering the pooled connection.

USAGE (from backend/):
    python scripts/rescore_all_jurisdictions.py            # all jurisdictions
    python scripts/rescore_all_jurisdictions.py --jurisdiction <uuid>   # one
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

from app.services.buybox_scoring import auto_score_jurisdiction  # noqa: E402


async def _jurisdiction_ids(only: uuid.UUID | None) -> list[uuid.UUID]:
    if only is not None:
        return [only]
    conn = await asyncpg.connect(get_sync_dsn())
    try:
        rows = await conn.fetch(
            """
            SELECT jurisdiction_id, COUNT(*) AS n
              FROM parcels
             WHERE jurisdiction_id IS NOT NULL
             GROUP BY jurisdiction_id
             ORDER BY n DESC
            """
        )
    finally:
        await conn.close()
    return [r["jurisdiction_id"] for r in rows]


async def main() -> None:
    ap = argparse.ArgumentParser(description="Re-score all jurisdictions.")
    ap.add_argument("--jurisdiction", type=str, default=None,
                    help="Only re-score this jurisdiction UUID.")
    args = ap.parse_args()
    only = uuid.UUID(args.jurisdiction) if args.jurisdiction else None

    jids = await _jurisdiction_ids(only)
    print(f"Re-scoring {len(jids)} jurisdiction(s)…", flush=True)

    total = 0
    failures: list[tuple[uuid.UUID, str]] = []
    for i, jid in enumerate(jids, 1):
        t0 = time.monotonic()
        try:
            n = await auto_score_jurisdiction(jid)
            total += n
            print(f"  [{i}/{len(jids)}] {jid}  scored={n:,}  "
                  f"({time.monotonic() - t0:.1f}s)", flush=True)
        except Exception as e:  # keep going; report at the end
            failures.append((jid, str(e)))
            print(f"  [{i}/{len(jids)}] {jid}  FAILED: {e}", flush=True)

    print(f"\nDone. {total:,} parcel-scores upserted across {len(jids)} "
          f"jurisdiction(s).", flush=True)
    if failures:
        print(f"{len(failures)} jurisdiction(s) failed:", flush=True)
        for jid, msg in failures:
            print(f"  {jid}: {msg}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
