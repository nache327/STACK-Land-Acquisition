"""
Phase 3 bootstrap — DC/Mid-Atlantic counties:
  - Fairfax County, VA      (county AGOL Parcels_with_Address_points, ~392K)
  - Loudoun County, VA      (logis.loudoun.gov LandRecords MapServer/5, ~132K)
  - Montgomery County, MD   (MD iMAP statewide, JURSCODE='MONT', ~290K)
  - Howard County, MD       (MD iMAP statewide, JURSCODE='HOWA', ~100K)
  - Montgomery County, PA   (gis.montcopa.org Parcels/FeatureServer/10, ~310K)

Same pattern as scripts/ingest_phase2_ny_ct.py — creates a Job row per
jurisdiction and runs run_job_pipeline() against the production DB. Each
jurisdiction key maps to a KNOWN_JURISDICTIONS entry in pipeline.py.

Usage (from backend/):
    python scripts/ingest_phase3_dc_midatlantic.py
    python scripts/ingest_phase3_dc_midatlantic.py --jurisdiction "Fairfax County, VA"
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


DEFAULT_JURISDICTIONS = [
    "Fairfax County, VA",
    "Loudoun County, VA",
    "Montgomery County, MD",
    "Howard County, MD",
    "Montgomery County, PA",
]


async def seed_jurisdiction(name: str) -> None:
    async with async_session_maker() as db:
        job = Job(
            jurisdiction_input=name,
            status=JobStatus.pending,
            target_uses=["any"],
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)
        await db.commit()
        logger.info("Created Job %s for %r", job.id, name)

    # run_job_pipeline opens its own AsyncSession — safe after commit above.
    await run_job_pipeline(job.id)


async def main(jurisdictions: list[str]) -> None:
    for name in jurisdictions:
        try:
            logger.info("── Seeding %s ──", name)
            await seed_jurisdiction(name)
        except Exception as exc:
            logger.exception("Failed to seed %s: %s", name, exc)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--jurisdiction", action="append",
        help='Full jurisdiction name (e.g., "Fairfax County, VA"). Repeat for multiple.',
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    targets = args.jurisdiction or DEFAULT_JURISDICTIONS
    asyncio.run(main(targets))
