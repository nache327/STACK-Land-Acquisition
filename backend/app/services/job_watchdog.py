from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.services.job_queue import enqueue_pipeline_job
from app.services.job_tracking import ACTIVE_JOB_STATUSES, now_utc, truncate_error

# Aligned with the Dramatiq pipeline actor's time_limit (60 min, job_queue.py)
# plus a heartbeat margin. Catch #12 fix: the old 25-min cutoff was SHORTER than
# the 60-min job budget, so recover_stale_jobs re-enqueued a still-running
# pipeline from discover_layers (Montgomery PA pass-1->pass-2; Bergen 65min/0-row
# stall). A job is not "dead" until Dramatiq itself kills it at 60 min.
STALE_AFTER_SECONDS = 70 * 60
MAX_ATTEMPTS = 3


async def recover_stale_jobs(stale_after_seconds: int = STALE_AFTER_SECONDS) -> int:
    cutoff = now_utc() - timedelta(seconds=stale_after_seconds)
    recovered = 0
    async with async_session_maker() as db:
        result = await db.execute(
            select(Job).where(
                Job.status.in_(ACTIVE_JOB_STATUSES),
                Job.locked_at.isnot(None),
                Job.locked_at < cutoff,
            )
        )
        jobs = result.scalars().all()
        for job in jobs:
            if job.cancel_requested_at is not None:
                job.status = JobStatus.cancelled
                job.finished_at = now_utc()
                job.locked_by = None
                job.locked_at = None
            elif (job.attempts or 0) < MAX_ATTEMPTS:
                job.status = JobStatus.retrying
                job.locked_by = None
                job.locked_at = None
                enqueue_pipeline_job(job.id)
            else:
                job.status = JobStatus.failed
                job.error_message = truncate_error(
                    f"Job stale for more than {stale_after_seconds} seconds"
                )
                job.finished_at = now_utc()
                job.locked_by = None
                job.locked_at = None
            recovered += 1
        await db.commit()
    return recovered
