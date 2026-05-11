"""Operational debug endpoints — recent jobs, env, queue health."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db, async_session_maker
from app.models.job import Job
from app.models.job_step import JobStep
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.models.zoning_district import ZoningDistrict
from app.version import get_pipeline_version

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/env")
async def debug_env() -> dict:
    return {
        "environment": settings.environment,
        "database_url": settings.database_url_sanitized,
        "redis_url": settings.redis_url_sanitized,
        "pipeline_version": get_pipeline_version(),
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


@router.post("/run-bulk-zoning-overlays/{jurisdiction_id}")
async def run_bulk_zoning_overlays(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run only the bulk_ingest_zoning_for_jurisdiction step.

    For jurisdictions where parcels already have zoning_code populated but
    zoning_overlays rows are missing (e.g. fix-zoning's HTTP request died
    after the heavy spatial backfill committed but before this final step
    ran). bulk_ingest_zoning_for_jurisdiction is fast (two SQL passes with
    a 60s statement_timeout cap), so this endpoint comfortably fits inside
    Railway's HTTP window.
    """
    from app.services.zoning_system import bulk_ingest_zoning_for_jurisdiction

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    overlays_created = await bulk_ingest_zoning_for_jurisdiction(jurisdiction_id, db)
    await db.commit()
    return {
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": j.name,
        "overlays_created": overlays_created,
    }


@router.post("/fix-zoning-all")
async def fix_zoning_all() -> StreamingResponse:
    """Run fix-zoning for every jurisdiction that has a zoning_endpoint and unzoned parcels.

    Streams NDJSON results one line per city as each completes, keeping the
    connection alive past Railway's 5-minute HTTP timeout.
    """

    async def _stream():
        from app.services.arcgis_query import download_all_features
        from app.services.spatial_backfill import backfill_parcel_zoning_from_districts
        from app.services.zoning_ingestion import ingest_zoning_districts
        from app.services.zoning_system import bulk_ingest_zoning_for_jurisdiction

        async with async_session_maker() as db:
            result = await db.execute(
                select(Jurisdiction)
                .where(Jurisdiction.zoning_endpoint.isnot(None))
                .order_by(Jurisdiction.name)
            )
            jurisdictions = list(result.scalars().all())

        yield json.dumps({"status": "starting", "total": len(jurisdictions)}) + "\n"

        for jur in jurisdictions:
            jid = jur.id
            name = jur.name

            async with async_session_maker() as db:
                try:
                    # Skip if already healthy: districts exist + no unzoned parcels
                    zd_count = await db.scalar(
                        select(func.count(ZoningDistrict.id)).where(ZoningDistrict.jurisdiction_id == jid)
                    )
                    unzoned = await db.scalar(
                        select(func.count(Parcel.id)).where(
                            Parcel.jurisdiction_id == jid,
                            or_(Parcel.zoning_code.is_(None), Parcel.zoning_code == ""),
                        )
                    )
                    if (zd_count or 0) > 0 and (unzoned or 0) == 0:
                        yield json.dumps({"jurisdiction": name, "skipped": True, "reason": "already healthy"}) + "\n"
                        continue

                    zgdf = await download_all_features(jur.zoning_endpoint, where="1=1")
                    districts_ingested = await ingest_zoning_districts(zgdf, jid, db)
                    await db.commit()

                    parcels_updated = await backfill_parcel_zoning_from_districts(jid, db)
                    await db.commit()

                    overlays_created = await bulk_ingest_zoning_for_jurisdiction(jid, db)
                    await db.commit()

                    yield json.dumps({
                        "jurisdiction": name,
                        "skipped": False,
                        "districts_ingested": districts_ingested,
                        "parcels_updated": parcels_updated,
                        "overlays_created": overlays_created,
                    }) + "\n"

                except Exception as exc:
                    yield json.dumps({"jurisdiction": name, "error": str(exc)}) + "\n"

        yield json.dumps({"status": "done"}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@router.get("/alembic-status")
async def debug_alembic_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Return the current alembic head recorded in the DB + the head on disk.

    Useful for diagnosing the kind of schema-vs-code drift that broke
    parcel queries after the 0018 deploy. If `db_head` != `disk_head`,
    alembic upgrade hasn't run successfully and the API is serving code
    that expects columns the DB doesn't have yet.
    """
    from sqlalchemy import text as _text
    try:
        row = (await db.execute(_text("SELECT version_num FROM alembic_version"))).fetchone()
        db_head = row[0] if row else None
    except Exception as exc:
        db_head = f"ERR: {exc}"

    # Disk head — read the highest numeric prefix from versions/.
    import re
    from pathlib import Path
    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    disk_revs: list[str] = []
    for p in versions.glob("*.py"):
        m = re.search(r'^revision\s*(?::[^=]+)?\s*=\s*["\']([^"\']+)["\']', p.read_text(), re.M)
        if m:
            disk_revs.append(m.group(1))
    return {
        "db_head": db_head,
        "disk_revisions": sorted(disk_revs),
    }


@router.post("/alembic-upgrade")
async def debug_alembic_upgrade() -> dict:
    """Run alembic upgrade head from inside the API process.

    Idempotent — if the DB is already at head, this is a no-op. Use when
    Railway's container-start `alembic upgrade head` step failed silently
    (the `&&` in the Dockerfile CMD short-circuits without affecting the
    uvicorn process, so the API comes up against a stale schema).
    """
    import io
    import sys
    from contextlib import redirect_stdout, redirect_stderr
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend_dir / "alembic.ini"))
    # Use the sync URL — alembic uses psycopg2 / not asyncpg.
    cfg.set_main_option("sqlalchemy.url", settings.sync_database_url)
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))

    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            command.upgrade(cfg, "head")
        success = True
        error = None
    except Exception as exc:
        success = False
        error = f"{type(exc).__name__}: {exc}"

    return {
        "success": success,
        "error": error,
        "stdout": buf_out.getvalue()[-4000:],
        "stderr": buf_err.getvalue()[-4000:],
    }
