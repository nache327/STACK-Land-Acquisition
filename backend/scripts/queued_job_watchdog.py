from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from app.db import async_session_maker, engine
from app.models.job import Job, JobStatus
from app.models.jurisdiction import Jurisdiction
from app.services.job_tracking import now_utc

DEFAULT_STALE_AFTER_MINUTES = 10


@dataclass(frozen=True)
class StuckQueuedJob:
    id: str
    jurisdiction: str
    queued_at: datetime | None
    age_minutes: int | None


async def find_stuck_queued_jobs(stale_after_minutes: int) -> list[StuckQueuedJob]:
    cutoff = now_utc() - timedelta(minutes=stale_after_minutes)
    age_anchor = func.coalesce(Job.queued_at, Job.created_at)

    async with async_session_maker() as db:
        result = await db.execute(
            select(
                Job.id,
                Job.jurisdiction_input,
                Job.queued_at,
                Job.created_at,
                Jurisdiction.name,
                Jurisdiction.state,
            )
            .outerjoin(Jurisdiction, Job.jurisdiction_id == Jurisdiction.id)
            .where(
                Job.status == JobStatus.queued,
                Job.finished_at.is_(None),
                age_anchor < cutoff,
            )
            .order_by(age_anchor.asc())
        )
        rows = result.all()

    stuck: list[StuckQueuedJob] = []
    checked_at = now_utc()
    for row in rows:
        jurisdiction = _format_jurisdiction(
            jurisdiction_input=row.jurisdiction_input,
            jurisdiction_name=row.name,
            jurisdiction_state=row.state,
        )
        anchor = row.queued_at or row.created_at
        age_minutes = None
        if anchor is not None:
            age_minutes = int((checked_at - anchor).total_seconds() // 60)
        stuck.append(
            StuckQueuedJob(
                id=str(row.id),
                jurisdiction=jurisdiction,
                queued_at=row.queued_at,
                age_minutes=age_minutes,
            )
        )
    return stuck


def _format_jurisdiction(
    *,
    jurisdiction_input: str | None,
    jurisdiction_name: str | None,
    jurisdiction_state: str | None,
) -> str:
    if jurisdiction_name and jurisdiction_state:
        return f"{jurisdiction_name}, {jurisdiction_state}"
    if jurisdiction_name:
        return jurisdiction_name
    if jurisdiction_input:
        return jurisdiction_input
    return "(unknown)"


def print_stuck_jobs(stuck_jobs: list[StuckQueuedJob], stale_after_minutes: int) -> None:
    print(
        f"queued-job watchdog found {len(stuck_jobs)} queued job(s) older than "
        f"{stale_after_minutes} minutes:",
        file=sys.stderr,
    )
    for job in stuck_jobs:
        queued_at = job.queued_at.isoformat() if job.queued_at else "(null)"
        age = f"{job.age_minutes}m" if job.age_minutes is not None else "unknown"
        print(
            f"  job_id={job.id} jurisdiction={job.jurisdiction!r} "
            f"queued_at={queued_at} age={age}",
            file=sys.stderr,
        )


async def run(stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES) -> int:
    try:
        stuck_jobs = await find_stuck_queued_jobs(stale_after_minutes)
    except Exception as exc:
        print(f"queued-job watchdog query failed: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()

    if not stuck_jobs:
        print(
            f"queued-job watchdog OK: no queued jobs older than {stale_after_minutes} minutes",
            file=sys.stderr,
        )
        return 0

    print_stuck_jobs(stuck_jobs, stale_after_minutes)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail when queued jobs are stuck.")
    parser.add_argument(
        "--stale-after-minutes",
        type=int,
        default=DEFAULT_STALE_AFTER_MINUTES,
        help="Queued jobs older than this threshold are reported as stuck.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(run(args.stale_after_minutes)))


if __name__ == "__main__":
    main()
