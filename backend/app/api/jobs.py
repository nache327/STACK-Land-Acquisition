"""
POST /api/jobs        — create a new search job
GET  /api/jobs/:id   — poll job status
"""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import BackgroundTasks
from app.db import get_db, async_session_maker
from app.models.job import Job, JobStatus
from app.models.job_step import JobArtifact, JobStep
from app.models.jurisdiction import Jurisdiction
from app.services.overlays import apply_aadt_overlay
from app.schemas.job import JobAdminRead, JobArtifactRead, JobCreate, JobRead, JobStepRead
from app.services.job_queue import enqueue_pipeline_job
from app.services.job_tracking import (
    ACTIVE_JOB_STATUSES,
    active_job_for_dedupe,
    normalize_dedupe_key,
    now_utc,
)

router = APIRouter(tags=["jobs"])


@router.post("/jobs", response_model=JobRead, status_code=201)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
) -> Job:
    # If the jurisdiction name matches an already-indexed city, return the most
    # recent ready job for it rather than re-running the full pipeline.
    name_query = payload.jurisdiction.strip().split(",")[0].strip().lower()
    existing_jur = await db.execute(
        select(Jurisdiction).where(
            text("LOWER(name) = :n")
        ).params(n=name_query)
    )
    jurisdiction = existing_jur.scalar_one_or_none()

    if not payload.force and jurisdiction is not None and jurisdiction.last_indexed_at is not None:
        # Find the most recent ready job for this jurisdiction
        existing_job = await db.execute(
            select(Job)
            .where(
                Job.status == JobStatus.ready,
                text("(progress->>'jurisdiction_id') = :jid").params(jid=str(jurisdiction.id)),
            )
            .order_by(Job.updated_at.desc())
            .limit(1)
        )
        ready_job = existing_job.scalar_one_or_none()
        if ready_job is not None:
            return ready_job

    dedupe_key = normalize_dedupe_key(
        payload.jurisdiction,
        list(payload.target_uses),
        payload.ordinance_url,
    )
    if not payload.force:
        active_job = await active_job_for_dedupe(db, dedupe_key)
        if active_job is not None:
            return active_job

    job = Job(
        jurisdiction_input=payload.jurisdiction,
        ordinance_url=payload.ordinance_url,
        target_uses=payload.target_uses,
        status=JobStatus.queued,
        queued_at=now_utc(),
        force=payload.force,
        dedupe_key=dedupe_key if not payload.force else f"{dedupe_key}|force:{uuid.uuid4()}",
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    await db.commit()  # must commit before background task reads this row

    enqueue_pipeline_job(job.id)

    return job


@router.get("/admin/jobs", response_model=list[JobRead])
async def list_admin_jobs(
    status: JobStatus | None = Query(default=None),
    jurisdiction: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    stale_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if jurisdiction:
        stmt = stmt.where(Job.jurisdiction_input.ilike(f"%{jurisdiction}%"))
    if active_only:
        stmt = stmt.where(Job.status.in_(ACTIVE_JOB_STATUSES))
    if stale_only:
        cutoff = now_utc() - timedelta(minutes=10)
        stmt = stmt.where(Job.status.in_(ACTIVE_JOB_STATUSES), Job.locked_at < cutoff)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/admin/jobs/{job_id}", response_model=JobAdminRead)
async def get_admin_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobAdminRead:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    steps = (
        await db.execute(
            select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.created_at.asc())
        )
    ).scalars().all()
    artifacts = (
        await db.execute(
            select(JobArtifact)
            .where(JobArtifact.job_id == job_id)
            .order_by(JobArtifact.created_at.asc())
        )
    ).scalars().all()
    return JobAdminRead(job=job, steps=list(steps), artifacts=list(artifacts))


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/steps", response_model=list[JobStepRead])
async def get_job_steps(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[JobStep]:
    if await db.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    result = await db.execute(
        select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.created_at.asc())
    )
    return list(result.scalars().all())


async def _run_aadt_backfill(jurisdiction_id: uuid.UUID) -> None:
    import logging
    log = logging.getLogger(__name__)
    try:
        async with async_session_maker() as db:
            updated = await apply_aadt_overlay(jurisdiction_id, db)
            await db.commit()
            log.info("AADT backfill complete: %d parcels updated for %s", updated, jurisdiction_id)
    except Exception as exc:
        log.error("AADT backfill failed for %s: %s", jurisdiction_id, exc)


@router.post("/jobs/{job_id}/backfill-aadt", status_code=202)
async def backfill_aadt(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.jurisdiction_id is None:
        raise HTTPException(status_code=400, detail="Job has no jurisdiction")

    jid = job.jurisdiction_id
    background_tasks.add_task(_run_aadt_backfill, jid)
    return {"status": "started", "jurisdiction_id": str(jid)}


@router.get("/jobs/{job_id}/artifacts", response_model=list[JobArtifactRead])
async def get_job_artifacts(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[JobArtifact]:
    if await db.get(Job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    result = await db.execute(
        select(JobArtifact).where(JobArtifact.job_id == job_id).order_by(JobArtifact.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel an in-flight job.

    Returns a plain dict rather than a JobRead-shaped response. The full ORM
    object includes relationships (steps, artifacts) whose lazy-load contract
    isn't compatible with FastAPI's response_model validation in the
    cancellation path — previous behaviour was a ResponseValidationError 500
    even though the state mutation succeeded.
    """
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    terminal = {JobStatus.ready, JobStatus.failed, JobStatus.cancelled}
    if job.status in terminal:
        return {
            "job_id": str(job.id),
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "cancel_requested_at": job.cancel_requested_at.isoformat() if job.cancel_requested_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "already_terminal": True,
        }
    job.cancel_requested_at = now_utc()
    job.status = JobStatus.cancelled
    job.finished_at = now_utc()
    job.locked_by = None
    job.locked_at = None
    await db.flush()
    await db.commit()
    return {
        "job_id": str(job.id),
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "cancel_requested_at": job.cancel_requested_at.isoformat() if job.cancel_requested_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "already_terminal": False,
    }


@router.post("/jobs/{job_id}/retry", response_model=JobRead)
async def retry_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in {JobStatus.failed, JobStatus.cancelled}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be retried")
    job.status = JobStatus.retrying
    job.error_message = None
    job.cancel_requested_at = None
    job.finished_at = None
    job.queued_at = now_utc()
    job.locked_by = None
    job.locked_at = None
    await db.flush()
    await db.commit()
    enqueue_pipeline_job(job.id)
    await db.refresh(job)
    return job


@router.post("/jobs/{job_id}/force-rerun", response_model=JobRead, status_code=201)
async def force_rerun_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Job:
    original = await db.get(Job, job_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Job not found")
    dedupe_key = normalize_dedupe_key(
        original.jurisdiction_input or "",
        list(original.target_uses or []),
        original.ordinance_url,
    )
    job = Job(
        jurisdiction_input=original.jurisdiction_input,
        ordinance_url=original.ordinance_url,
        target_uses=original.target_uses,
        status=JobStatus.queued,
        queued_at=now_utc(),
        force=True,
        dedupe_key=f"{dedupe_key}|force:{uuid.uuid4()}",
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    await db.commit()
    enqueue_pipeline_job(job.id)
    return job
