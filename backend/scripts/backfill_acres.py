"""
Recompute parcel acreages from geometry for all parcels.

The previous ingestion used Shape__Area (ArcGIS native-CRS units) as a fallback,
which could be in sq ft or sq m depending on the source layer's CRS.  This caused
~10.76× inflation when sq ft were treated as sq m.

This script replaces ALL stored acreages with values derived from the WGS84 geometry
via PostGIS ST_Area(geography(geom)), which is correct regardless of source CRS.

Run from the backend/ directory:
    python scripts/backfill_acres.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.db import async_session_maker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_SQM_PER_ACRE = 4046.856


async def run() -> None:
    # Fetch all jurisdiction IDs to process one at a time (avoid statement timeout)
    async with async_session_maker() as db:
        result = await db.execute(text("""
            SELECT j.id, j.name, COUNT(p.id) AS parcel_count
            FROM jurisdictions j
            JOIN parcels p ON p.jurisdiction_id = j.id
            WHERE p.geom IS NOT NULL
            GROUP BY j.id, j.name
            ORDER BY j.name
        """))
        jurisdictions = result.fetchall()

    logger.info("Processing %d jurisdictions", len(jurisdictions))
    total_updated = 0

    for jur in jurisdictions:
        async with async_session_maker() as db:
            result = await db.execute(text(f"""
                UPDATE parcels
                SET acres = ROUND(
                    (ST_Area(geography(geom)) / {_SQM_PER_ACRE})::numeric,
                    4
                )
                WHERE jurisdiction_id = :jid
                  AND geom IS NOT NULL
            """), {"jid": jur.id})
            updated = result.rowcount
            await db.commit()

        total_updated += updated
        logger.info("  %-40s %6d parcels updated", jur.name, updated)

    logger.info("Total updated: %d parcels", total_updated)

    # Spot-check a few values
    async with async_session_maker() as db:
        result = await db.execute(text("""
            SELECT j.name, p.apn, p.acres
            FROM parcels p
            JOIN jurisdictions j ON j.id = p.jurisdiction_id
            WHERE p.acres IS NOT NULL
            ORDER BY random()
            LIMIT 10
        """))
        rows = result.fetchall()

    print(f"\n{'='*60}")
    print("Sample parcels after backfill:")
    for r in rows:
        print(f"  {r.name} | APN {r.apn} | {r.acres} acres")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(run())
