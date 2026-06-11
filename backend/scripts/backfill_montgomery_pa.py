"""Phase-2A one-off invocation for Montgomery County, PA spatial backfill.

DO NOT RUN as-is. Pre-flight discovered the 54 ingested zoning_districts
cover ~1.2 % of the county by area (single township's worth), so the
backfill would bind <3 % of parcels. See docs/OP5_MONTGOMERY_PA_BACKFILL.md
for the diagnosis and the prerequisites.

This script is committed to the branch so that, when county-wide zoning
district data IS loaded for Montgomery County (Phase 2A-redux), the
operator has a tested one-off invocation path that mirrors the existing
post-ingest hook at pipeline.py:1617 — no new code, just a one-jurisdiction
fire.

Usage (once prerequisites are met):

    cd backend && python scripts/backfill_montgomery_pa.py

The canonical admin-endpoint equivalent is:

    POST /api/debug/fix-zoning/{jurisdiction_id}

This script writes via the same in-process call so the operator can see
the parcels_updated return value directly in stdout.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import async_session_maker
from app.services.spatial_backfill import backfill_parcel_zoning_from_districts


MONTGOMERY_PA_ID = uuid.UUID("a59d956d-5f67-4c39-aef1-36140bd57c6f")


async def main() -> int:
    async with async_session_maker() as db:
        # nearest_within_meters is intentionally left at None for the
        # contained-only ST_Within pass. The 30 % nearest_* quality gate
        # from docs/INGESTION_PIPELINE_PLAN.md would fail today against
        # the partial district coverage; do not enable the fallback
        # until county-wide districts are loaded.
        updated = await backfill_parcel_zoning_from_districts(
            MONTGOMERY_PA_ID, db, fill_missing_zone_code=True
        )
        await db.commit()
    print(f"backfill_parcel_zoning_from_districts updated {updated} parcels")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
