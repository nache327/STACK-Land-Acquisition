"""
Overlay-only ingest for Philadelphia and NYC.
Runs flood (FEMA NFHL layer 28) and wetland (USFWS NWI layer 1) overlays
against existing parcels. Does NOT touch parcels or zoning.
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
from app.services.overlays import apply_flood_overlay, apply_wetland_overlay

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

JURISDICTIONS = ["Philadelphia, PA", "New York, NY"]


async def main() -> None:
    async with async_session_maker() as db:
        for name in JURISDICTIONS:
            j = (await db.execute(
                select(Jurisdiction).where(Jurisdiction.name == name)
            )).scalar_one()
            logger.info("=== %s (id=%s) ===", name, j.id)

            logger.info("[%s] Running flood overlay (FEMA NFHL layer 28) …", name)
            flood = await apply_flood_overlay(j.id, db)
            await db.commit()
            logger.info("[%s] Flood overlay done: %d parcels flagged", name, flood)

            logger.info("[%s] Running wetland overlay (USFWS NWI layer 1) …", name)
            wetland = await apply_wetland_overlay(j.id, db)
            await db.commit()
            logger.info("[%s] Wetland overlay done: %d parcels flagged", name, wetland)

        # Verification
        logger.info("=== Verification ===")
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
