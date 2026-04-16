"""
POST /api/jobs        — create a new search job
GET  /api/jobs/:id   — poll job status
"""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.job import Job, JobStatus
from app.schemas.job import JobCreate, JobRead
from app.services.pipeline import run_job_pipeline

router = APIRouter(tags=["jobs"])


@router.post("/jobs", response_model=JobRead, status_code=201)
async def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Job:
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
