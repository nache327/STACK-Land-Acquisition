"""
Re-run wetland overlay for NYC only (flood already succeeded).
Per-page 504 errors now return partial data instead of aborting.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text

from app.db import async_session_maker
from app.models.jurisdiction import Jurisdiction
from app.services.overlays import apply_wetland_overlay

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with async_session_maker() as db:
        j = (await db.execute(
            select(Jurisdiction).where(Jurisdiction.name == "New York, NY")
        )).scalar_one()
        logger.info("NYC jurisdiction id: %s", j.id)

        logger.info("Running wetland overlay (USFWS NWI via AGOL) …")
        wetland = await apply_wetland_overlay(j.id, db)
        await db.commit()
        logger.info("NYC wetland overlay done: %d parcels flagged", wetland)

        # Verification
        total = (await db.execute(text("SELECT count(*) FROM overlays"))).scalar_one()
        logger.info("Total overlay rows: %d", total)

        rows = (await db.execute(text(
            "SELECT overlay_type, jurisdiction_id, count(*) AS cnt "
            "FROM overlays GROUP BY overlay_type, jurisdiction_id ORDER BY overlay_type, cnt DESC"
        ))).fetchall()
        for row in rows:
            logger.info("  overlay_type=%-20s jurisdiction=%s  count=%d", *row)


if __name__ == "__main__":
    asyncio.run(main())
