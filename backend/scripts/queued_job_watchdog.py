"""Fail if recently queued jobs are stuck in a non-terminal state."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.models.jurisdiction import Jurisdiction

TERMINAL_STATUSES = (JobStatus.ready, JobStatus.failed, JobStatus.cancelled)


def _jurisdiction_label(
    name: str | None,
    state: str | None,
    jurisdiction_input: str | None,
) -> str:
    if name and state:
        return f"{name}, {state}"
    if name:
        return name
    if jurisdiction_input:
        return jurisdiction_input
    return "unknown jurisdiction"


async def find_stuck_jobs() -> list[tuple[str, str]]:
    now = datetime.now(timezone.utc)
    older_than = now - timedelta(minutes=10)
    newer_than = now - timedelta(days=7)

    stmt = (
        select(
            Job.id,
            Job.jurisdiction_input,
            Jurisdiction.name,
            Jurisdiction.state,
        )
        .outerjoin(Jurisdiction, Job.jurisdiction_id == Jurisdiction.id)
        .where(
            Job.status.notin_(TERMINAL_STATUSES),
            Job.queued_at.is_not(None),
            Job.queued_at < older_than,
            Job.queued_at >= newer_than,
        )
        .order_by(Job.queued_at.asc())
    )

    async with async_session_maker() as db:
        result = await db.execute(stmt)
        return [
            (
                _jurisdiction_label(name, state, jurisdiction_input),
                str(job_id),
            )
            for job_id, jurisdiction_input, name, state in result.all()
        ]


async def main() -> int:
    try:
        stuck_jobs = await find_stuck_jobs()
    except Exception as exc:
        print(f"queued-job watchdog query failed: {exc}", file=sys.stderr)
        return 2

    if stuck_jobs:
        print("Stuck queued jobs:", file=sys.stderr)
        for jurisdiction, job_id in stuck_jobs:
            print(f"{jurisdiction}: {job_id}", file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
