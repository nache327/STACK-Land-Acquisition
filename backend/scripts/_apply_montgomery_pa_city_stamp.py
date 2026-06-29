"""One-off: stamp parcels.city for Montgomery County, PA from the zoning polygon
municipality (catch #33/#35 family — task #90 follow-up to the zoning bind).

Montgomery PA's parcel layer (Montgomery_County_Parcels/10) carries only TAXPIN +
acreage — no municipality field — so all 301k parcels ingested with city=NULL. The
zoning layer (Municipal_Zoning/11) IS name-native: the township/borough name lives
in raw_attributes->>'Municipality'. This script spatially stamps parcels.city from
the containing zoning district so muni-specific Stage-4 verdicts can resolve.

The pipeline now does this inline post-bind (parcel_city_stamp stage), so a future
re-ingest is self-sufficient; this script is the immediate one-off fire that avoids
re-pulling 301k parcels just to stamp city.

Usage (prod — Railway console / session-mode DB):

    cd backend && python scripts/_apply_montgomery_pa_city_stamp.py

Safe + idempotent: only stamps WHERE parcels.city IS NULL (never clobbers a city
already set), and re-running it is a no-op once stamped.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import async_session_maker
from app.services.spatial_backfill import backfill_parcel_city_from_districts


MONTGOMERY_PA_ID = uuid.UUID("a59d956d-5f67-4c39-aef1-36140bd57c6f")


async def main() -> int:
    async with async_session_maker() as db:
        stamped = await backfill_parcel_city_from_districts(MONTGOMERY_PA_ID, db)
        await db.commit()
    print(f"backfill_parcel_city_from_districts stamped city on {stamped} parcels")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
