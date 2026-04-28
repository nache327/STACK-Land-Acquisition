from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.models.job_step import JobArtifact, JobStep

TERMINAL_JOB_STATUSES = {JobStatus.ready, JobStatus.failed, JobStatus.cancelled}
ACTIVE_JOB_STATUSES = {
    JobStatus.pending,
    JobStatus.queued,
    JobStatus.running,
    JobStatus.retrying,
    JobStatus.discovering_layers,
    JobStatus.downloading_parcels,
    JobStatus.ingesting_parcels,
    JobStatus.downloading_zoning,
    JobStatus.pending_zoning,
    JobStatus.parsing_ordinance,
    JobStatus.running_overlays,
}


class JobCancelled(RuntimeError):
    """Raised when a worker reaches a cancellation boundary."""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_dedupe_key(
    jurisdiction: str,
    target_uses: list[str] | None = None,
    ordinance_url: str | None = None,
) -> str:
    uses = ",".join(sorted(target_uses or []))
    jurisdiction_key = " ".join(jurisdiction.strip().lower().split())
    ordinance_key = (ordinance_url or "").strip().lower()
    return f"jurisdiction:{jurisdiction_key}|uses:{uses}|ordinance:{ordinance_key}"


def truncate_error(exc: BaseException | str, max_length: int = 2000) -> str:
    message = str(exc)
    if len(message) <= max_length:
        return message
    return f"{message[:max_length]}... [truncated]"


async def active_job_for_dedupe(
    db: AsyncSession,
    dedupe_key: str,
) -> Job | None:
    # Mirror the partial index predicate `uq_jobs_active_dedupe_key`
    # (dedupe_key IS NOT NULL AND finished_at IS NULL) so the read
    # path uses the same definition of "active" as the write path.
    result = await db.execute(
        select(Job)
        .where(
            Job.dedupe_key == dedupe_key,
            Job.finished_at.is_(None),
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_job_step(
    db: AsyncSession,
    job: Job | None,
    step: str,
    metadata: dict[str, Any] | None = None,
) -> JobStep:
    conditions = [JobStep.step == step]
    if job is not None:
        conditions.append(JobStep.job_id == job.id)
    elif metadata and "parcel_id" in metadata:
        conditions.append(JobStep.step_metadata["parcel_id"].astext == str(metadata["parcel_id"]))
    attempt_result = await db.execute(select(func.count(JobStep.id)).where(*conditions))
    attempt = int(attempt_result.scalar_one() or 0) + 1
    record = JobStep(
        job_id=job.id if job is not None else None,
        step=step,
        status="running",
        attempt=attempt,
        started_at=now_utc(),
        step_metadata=metadata or {},
    )
    db.add(record)
    await db.flush()
    return record


async def complete_job_step(
    db: AsyncSession,
    step: JobStep,
    metadata: dict[str, Any] | None = None,
) -> None:
    finished_at = now_utc()
    step.status = "completed"
    step.finished_at = finished_at
    if step.started_at is not None:
        step.duration_ms = int((finished_at - step.started_at).total_seconds() * 1000)
    if metadata:
        step.step_metadata = {**(step.step_metadata or {}), **metadata}
    await db.flush()


async def fail_job_step(
    db: AsyncSession,
    step: JobStep,
    error: BaseException | str,
    metadata: dict[str, Any] | None = None,
    status: str = "failed",
) -> None:
    finished_at = now_utc()
    step.status = status
    step.finished_at = finished_at
    if step.started_at is not None:
        step.duration_ms = int((finished_at - step.started_at).total_seconds() * 1000)
    step.error = truncate_error(error)
    if metadata:
        step.step_metadata = {**(step.step_metadata or {}), **metadata}
    await db.flush()


async def add_job_artifact(
    db: AsyncSession,
    job: Job,
    step: str,
    artifact_type: str,
    metadata: dict[str, Any] | None = None,
    storage_uri: str | None = None,
) -> JobArtifact:
    artifact = JobArtifact(
        job_id=job.id,
        step=step,
        artifact_type=artifact_type,
        artifact_metadata=metadata or {},
        storage_uri=storage_uri,
    )
    db.add(artifact)
    await db.flush()
    return artifact


async def check_cancelled(db: AsyncSession, job: Job) -> None:
    await db.refresh(job)
    if job.cancel_requested_at is not None:
        job.status = JobStatus.cancelled
        job.finished_at = now_utc()
        job.locked_by = None
        job.locked_at = None
        await db.flush()
        raise JobCancelled(f"Job {job.id} was cancelled")


async def mark_job_failed(db: AsyncSession, job_id: uuid.UUID, exc: BaseException | str) -> None:
    await db.rollback()
    job = await db.get(Job, job_id)
    if job is None:
        return
    running_steps = await db.execute(
        select(JobStep).where(
            JobStep.job_id == job_id,
            JobStep.status == "running",
        )
    )
    for step in running_steps.scalars().all():
        await fail_job_step(db, step, exc)
    job.status = JobStatus.failed
    job.error_message = truncate_error(exc)
    job.finished_at = now_utc()
    job.locked_by = None
    job.locked_at = None
    await db.commit()
