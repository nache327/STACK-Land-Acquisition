"""
Phase 2 bootstrap — NJ-adjacent counties:
  - Westchester County, NY  (NYS ITS public service, ~258K parcels)
  - Nassau County, NY       (county-hosted via NYS GPO, ~420K parcels)
  - Fairfield County, CT    (CT statewide CAMA + Parcel Layer 2024, 23-town
                             Town_Name filter, ~275K parcels)

Same pattern as scripts/ingest_ny_pa_bootstrap.py — creates a Job row per
jurisdiction and runs run_job_pipeline() against the production DB. Each
jurisdiction key maps to a KNOWN_JURISDICTIONS entry registered in
app/services/pipeline.py.

Usage (from backend/):
    python scripts/ingest_phase2_ny_ct.py
    python scripts/ingest_phase2_ny_ct.py --jurisdiction "Westchester County, NY"
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
    "Westchester County, NY",
    "Nassau County, NY",
    "Fairfield County, CT",
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
        help='Full jurisdiction name (e.g., "Westchester County, NY"). Repeat for multiple.',
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    targets = args.jurisdiction or DEFAULT_JURISDICTIONS
    asyncio.run(main(targets))
