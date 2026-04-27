"""
POST /api/jobs        — create a new search job
GET  /api/jobs/:id   — poll job status
"""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.job import Job, JobStatus
from app.models.jurisdiction import Jurisdiction
from app.schemas.job import JobCreate, JobRead
from app.services.pipeline import run_job_pipeline

router = APIRouter(tags=["jobs"])


@router.post("/jobs", response_model=JobRead, status_code=201)
async def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Job:
    # Unless force=True, check if this city is already indexed and return
    # the existing ready job — avoids a full re-download on every search.
    # Use LIKE prefix match so "Draper" matches "Draper City, UT" and
    # include state so "Salem, UT" doesn't collide with "Salem, OR".
    parts = payload.jurisdiction.strip().split(",")
    city_part = parts[0].strip().lower()
    state_part = parts[1].strip().upper() if len(parts) > 1 else None

    if state_part:
        existing_jur = await db.execute(
            select(Jurisdiction).where(
                text("LOWER(name) LIKE :city AND UPPER(name) LIKE :state")
            ).params(city=f"{city_part}%", state=f"%{state_part}%")
        )
    else:
        existing_jur = await db.execute(
            select(Jurisdiction).where(
                text("LOWER(name) LIKE :city")
            ).params(city=f"{city_part}%")
        )
    jurisdiction = existing_jur.scalar_one_or_none()

    if jurisdiction is not None:
        # Always block duplicate concurrent runs — return active job if one exists.
        active_job = await db.execute(
            select(Job)
            .where(
                Job.status.not_in([JobStatus.ready, JobStatus.failed]),
                text("(progress->>'jurisdiction_id') = :jid").params(jid=str(jurisdiction.id)),
            )
            .order_by(Job.updated_at.desc())
            .limit(1)
        )
        running_job = active_job.scalar_one_or_none()
        if running_job is not None:
            return running_job

        # Unless force=True, return the most recent ready job (skip re-download).
        if not payload.force and jurisdiction.last_indexed_at is not None:
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

    job = Job(
        jurisdiction_input=payload.jurisdiction,
        ordinance_url=payload.ordinance_url,
        target_uses=payload.target_uses,
        status=JobStatus.pending,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    await db.commit()  # must commit before background task reads this row

    # Fire the pipeline as a background task.
    # The task creates its own DB session so it is safe after the request ends.
    background_tasks.add_task(run_job_pipeline, job.id)

    return job


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Job:
    job = await db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
