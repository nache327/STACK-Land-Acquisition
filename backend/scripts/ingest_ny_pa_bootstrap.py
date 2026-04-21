"""
Seed the NY + PA presets by creating Job rows and running the full pipeline
(parcels + zoning districts + overlays) for each.

Usage (from backend/):
    python scripts/ingest_ny_pa_bootstrap.py
    python scripts/ingest_ny_pa_bootstrap.py --city "New York, NY"
    python scripts/ingest_ny_pa_bootstrap.py --city "Philadelphia, PA"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.services.pipeline import run_job_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


DEFAULT_CITIES = [
    "New York, NY",
    "Philadelphia, PA",
]


async def seed_city(city: str) -> None:
    async with async_session_maker() as db:
        job = Job(
            jurisdiction_input=city,
            status=JobStatus.pending,
            target_uses=["any"],
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        await db.commit()
        logger.info("Created Job %s for %r", job.id, city)

    # Pipeline opens its own session — safe after commit
    await run_job_pipeline(job.id)


async def main(cities: list[str]) -> None:
    for city in cities:
        try:
            logger.info("── Seeding %s ──", city)
            await seed_city(city)
        except Exception as exc:
            logger.exception("Failed to seed %s: %s", city, exc)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--city", action="append",
        help='City name (e.g., "New York, NY"). Repeat to seed multiple.',
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cities = args.city or DEFAULT_CITIES
    asyncio.run(main(cities))
