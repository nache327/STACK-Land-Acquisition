"""Operational debug endpoints — recent jobs, env, queue health."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.job import Job
from app.models.job_step import JobStep
from app.models.jurisdiction import Jurisdiction

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/env")
async def debug_env() -> dict:
    return {
        "environment": settings.environment,
        "database_url": settings.database_url_sanitized,
        "redis_url": settings.redis_url_sanitized,
    }


@router.get("/jobs")
async def debug_jobs(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    jobs_result = await db.execute(
        select(Job).order_by(Job.created_at.desc()).limit(limit)
    )
    jobs = list(jobs_result.scalars().all())
    if not jobs:
        return []

    job_ids = [job.id for job in jobs]
    steps_result = await db.execute(
        select(JobStep)
        .where(JobStep.job_id.in_(job_ids))
        .order_by(JobStep.created_at.asc())
    )
    steps_by_job: dict[str, list[dict]] = {}
    for step in steps_result.scalars().all():
        steps_by_job.setdefault(str(step.job_id), []).append(
            {
                "id": step.id,
                "step": step.step,
                "status": step.status,
                "attempt": step.attempt,
                "started_at": step.started_at,
                "finished_at": step.finished_at,
                "duration_ms": step.duration_ms,
                "error": step.error,
                "metadata": step.step_metadata,
            }
        )

    return [
        {
            "id": str(job.id),
            "status": job.status.value if hasattr(job.status, "value") else job.status,
            "jurisdiction_input": job.jurisdiction_input,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "queued_at": job.queued_at,
            "finished_at": job.finished_at,
            "error_message": job.error_message,
            "progress": job.progress,
            "steps": steps_by_job.get(str(job.id), []),
        }
        for job in jobs
    ]


@router.post("/fix-zoning/{jurisdiction_id}")
async def fix_zoning(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bypass the job queue and directly run the zoning district download + spatial backfill.

    Use this to fix parcels.zoning_code = NULL without waiting for the queue.
    """
    result = await db.execute(
        select(Jurisdiction).where(Jurisdiction.id == jurisdiction_id)
    )
    jurisdiction = result.scalar_one_or_none()
    if jurisdiction is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    zoning_endpoint = jurisdiction.zoning_endpoint
    if not zoning_endpoint:
        raise HTTPException(
            status_code=422,
            detail=f"Jurisdiction '{jurisdiction.name}' has no zoning_endpoint configured",
        )

    from app.services.arcgis_query import download_all_features
    from app.services.spatial_backfill import backfill_parcel_zoning_from_districts
    from app.services.zoning_ingestion import ingest_zoning_districts
    from app.services.zoning_system import bulk_ingest_zoning_for_jurisdiction

    zgdf = await download_all_features(zoning_endpoint, where="1=1")
    districts_ingested = await ingest_zoning_districts(zgdf, jurisdiction_id, db)
    await db.commit()

    parcels_updated = await backfill_parcel_zoning_from_districts(jurisdiction_id, db)
    await db.commit()

    overlays_created = await bulk_ingest_zoning_for_jurisdiction(jurisdiction_id, db)
    await db.commit()

    return {
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": jurisdiction.name,
        "districts_ingested": districts_ingested,
        "parcels_updated": parcels_updated,
        "overlays_created": overlays_created,
    }
