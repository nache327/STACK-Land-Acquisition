"""Canonical CoStar listing matcher — runs match_pending_listings DIRECTLY
against prod, bypassing the Dramatiq worker.

WHY THIS EXISTS (catch #25 recurrence): the Railway worker
(_match-listings-worker / process_listing_match) dies mid-run on county-sized
loads — the matcher's fallback tiers (tier_3_census, tier_4_nominatim) make slow
external geocode calls per unmatched listing, and the dyno is killed before the
batch finishes (observed: Norfolk/Middlesex/Lake froze at partial counts, 3x).
match_pending_listings is IDEMPOTENT (only touches match_method IS NULL rows), so
running it here resumes from wherever the worker stalled and completes reliably.

Use this AFTER POST /api/listings/upload (which inserts the rows) instead of
firing the worker endpoint, for any county-sized CoStar ingest.

USAGE (from backend/):
  python scripts/_match_listings_direct.py <jurisdiction_id> [<jurisdiction_id> ...]
  python scripts/_match_listings_direct.py --source costar <jid> ...
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.db import make_engine  # noqa: E402
from app.services.listing_matcher import match_pending_listings  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jurisdiction_ids", nargs="+")
    ap.add_argument("--source", default="costar")
    args = ap.parse_args()

    engine = make_engine()
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        for jid in args.jurisdiction_ids:
            print(f"=== matching {jid} (source={args.source}) …", flush=True)
            async with sm() as db:
                counts = await match_pending_listings(uuid.UUID(jid), args.source, db)
                await db.commit()
            print(f"    {counts}", flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
