"""
Pre-fetch all Philadelphia parcels into the DB so future jobs skip the
download phase entirely.

Usage (from backend/):
    python scripts/prefetch_philadelphia_parcels.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, func, select

from app.db import async_session_maker
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.services.arcgis_query import download_all_features
from app.services.ingestion import ingest_parcels

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PARCEL_ENDPOINT = (
    "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest"
    "/services/PWD_PARCELS/FeatureServer/0"
)


async def main() -> None:
    # ── Find or create the Philadelphia jurisdiction row ──────────────────
    async with async_session_maker() as db:
        result = await db.execute(
            select(Jurisdiction).where(Jurisdiction.name == "Philadelphia, PA")
        )
        jurisdiction = result.scalars().first()

        if jurisdiction is None:
            logger.error(
                "No 'Philadelphia, PA' jurisdiction found in DB. "
                "Run a Philadelphia job first so the jurisdiction row exists, "
                "then re-run this script."
            )
            return

        jur_id = jurisdiction.id
        logger.info("Jurisdiction: %s (%s)", jurisdiction.name, jur_id)

        # Clear any partial parcel data from prior failed jobs
        deleted = await db.execute(
            delete(Parcel).where(Parcel.jurisdiction_id == jur_id)
        )
        await db.commit()
        logger.info("Cleared %d stale parcel rows", deleted.rowcount)

    # ── Download all ~500K parcels (no pipeline timeout) ──────────────────
    logger.info("Starting parcel download from OPA ArcGIS endpoint …")
    start = time.monotonic()
    last_log = [0]

    async def on_progress(downloaded: int, total: int) -> None:
        # Log every 10K parcels
        if downloaded - last_log[0] >= 10_000 or downloaded == total:
            elapsed = time.monotonic() - start
            pct = downloaded / total * 100 if total else 0
            rate = downloaded / elapsed if elapsed else 0
            eta = (total - downloaded) / rate if rate else 0
            logger.info(
                "  %d / %d (%.0f%%) — %.0f/s — ETA %.0f min",
                downloaded, total, pct, rate, eta / 60,
            )
            last_log[0] = downloaded

    gdf = await download_all_features(
        PARCEL_ENDPOINT,
        where="1=1",
        progress_callback=on_progress,
    )
    logger.info(
        "Download complete: %d features in %.1f min",
        len(gdf),
        (time.monotonic() - start) / 60,
    )

    # ── Ingest into PostGIS ────────────────────────────────────────────────
    logger.info("Ingesting %d parcels into PostGIS …", len(gdf))
    ingest_start = time.monotonic()
    ingest_last_log = [0]

    async def on_ingest_progress(phase: str, completed: int, total: int) -> None:
        if completed - ingest_last_log[0] >= 20_000 or completed == total:
            logger.info("  [%s] %d / %d", phase, completed, total)
            ingest_last_log[0] = completed

    async with async_session_maker() as db:
        count = await ingest_parcels(gdf, jur_id, db, progress_callback=on_ingest_progress)
        await db.commit()

    logger.info(
        "Ingested %d parcels in %.1f min. Philadelphia is ready.",
        count,
        (time.monotonic() - ingest_start) / 60,
    )

    # Confirm final count
    async with async_session_maker() as db:
        total_in_db = await db.scalar(
            select(func.count(Parcel.id)).where(Parcel.jurisdiction_id == jur_id)
        )
    logger.info("DB check: %d parcels in DB for Philadelphia", total_in_db)


if __name__ == "__main__":
    asyncio.run(main())
