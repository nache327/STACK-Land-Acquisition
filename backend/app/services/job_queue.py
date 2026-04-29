from __future__ import annotations

import asyncio
import logging
import uuid

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.config import settings

logger = logging.getLogger(__name__)

logger.info("Connected to Redis at %s (env=%s)", settings.redis_url_sanitized, settings.environment)

redis_broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(redis_broker)


@dramatiq.actor(max_retries=0, time_limit=30 * 60 * 1000)
def process_pipeline_job(job_id: str) -> None:
    from app.services.pipeline import run_job_pipeline

    asyncio.run(run_job_pipeline(uuid.UUID(job_id)))


def enqueue_pipeline_job(job_id: uuid.UUID) -> None:
    process_pipeline_job.send(str(job_id))


@dramatiq.actor(max_retries=1, min_backoff=2_000, max_backoff=10_000, time_limit=5 * 60 * 1000)
def process_zoning_ingest(parcel_id: int) -> None:
    from app.db import async_session_maker
    from app.services.zoning_system import ingest_zoning_for_parcel_db

    async def _run() -> None:
        async with async_session_maker() as db:
            try:
                await ingest_zoning_for_parcel_db(parcel_id, db)
                await db.commit()
            except Exception:
                # Persist the failure step/cache update before Dramatiq retries.
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()
                raise

    asyncio.run(_run())


def enqueue_zoning_ingest(parcel_id: int) -> None:
    process_zoning_ingest.send(parcel_id)
