"""Close jobs that are stuck in `queued` because no worker ever claimed them.

WHY this exists (2026-10-09): `job_watchdog.recover_stale_jobs` only rescues
jobs with a non-NULL `locked_at` — i.e. ones a worker claimed and then dropped.
A job that was enqueued but never claimed (broker restart, worker scaled to
zero, Dramatiq message lost) keeps `locked_at IS NULL` forever, so nothing
rescues it and nothing closes it. `queued_job_watchdog` then reports it as
stuck on every 10-minute tick, permanently.

One such row — "1709 Whitehorse Avenue, Hamilton Township, NJ", queued
2026-08-10 — is what put the ops cron into a nonzero exit on every tick, and
Railway emails the account owner on every nonzero exit of a cron service.

Deliberately NOT automatic. Failing a user's job is a judgement call: it is only
safe once you have confirmed the worker is not simply backed up. Run the
dry-run, look at the ages, then `--apply`.

    python scripts/expire_orphaned_queued_jobs.py                 # dry-run
    python scripts/expire_orphaned_queued_jobs.py --apply
    python scripts/expire_orphaned_queued_jobs.py --older-than-hours 48 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.db import async_session_maker, engine  # noqa: E402
from app.models.job import Job, JobStatus  # noqa: E402
from app.services.job_tracking import now_utc, truncate_error  # noqa: E402

DEFAULT_OLDER_THAN_HOURS = 24


async def _orphaned(older_than_hours: int) -> list[Job]:
    """Queued, never claimed by a worker, and older than the cutoff."""
    cutoff = now_utc() - timedelta(hours=older_than_hours)
    age_anchor = func.coalesce(Job.queued_at, Job.created_at)
    async with async_session_maker() as db:
        result = await db.execute(
            select(Job)
            .where(
                Job.status == JobStatus.queued,
                Job.finished_at.is_(None),
                Job.locked_at.is_(None),  # never claimed — recover_stale_jobs can't see it
                age_anchor < cutoff,
            )
            .order_by(age_anchor.asc())
        )
        return list(result.scalars().all())


async def run(older_than_hours: int, apply: bool) -> int:
    try:
        jobs = await _orphaned(older_than_hours)
        if not jobs:
            print(f"no queued jobs orphaned for more than {older_than_hours}h")
            return 0

        now = now_utc()
        for job in jobs:
            anchor = job.queued_at or job.created_at
            age_h = int((now - anchor).total_seconds() // 3600) if anchor else None
            print(
                f"  job_id={job.id} age={age_h}h "
                f"jurisdiction={job.jurisdiction_input!r} queued_at={job.queued_at}"
            )

        if not apply:
            print(f"\n{len(jobs)} orphaned job(s) — dry-run, nothing written. Re-run with --apply.")
            return 0

        async with async_session_maker() as db:
            for job in jobs:
                fresh = await db.get(Job, job.id)
                # Re-check under the write session: a worker may have claimed it
                # between the read above and now.
                if fresh is None or fresh.status != JobStatus.queued or fresh.locked_at is not None:
                    print(f"  skip {job.id}: no longer an orphaned queued job")
                    continue
                fresh.status = JobStatus.failed
                fresh.error_message = truncate_error(
                    f"Orphaned in queue for more than {older_than_hours}h — no worker ever "
                    "claimed it. Expired by expire_orphaned_queued_jobs.py; re-submit to retry."
                )
                fresh.finished_at = now_utc()
            await db.commit()
        print(f"\nexpired {len(jobs)} orphaned queued job(s)")
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--older-than-hours", type=int, default=DEFAULT_OLDER_THAN_HOURS)
    ap.add_argument("--apply", action="store_true", help="write; default is dry-run")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.older_than_hours, args.apply)))


if __name__ == "__main__":
    main()
