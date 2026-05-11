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


@dramatiq.actor(
    max_retries=2,
    min_backoff=30_000,
    max_backoff=300_000,
    time_limit=30 * 60 * 1000,
)
def process_pipeline_job(job_id: str) -> None:
    from app.services.pipeline import run_job_pipeline

    asyncio.run(run_job_pipeline(uuid.UUID(job_id)))


def enqueue_pipeline_job(job_id: uuid.UUID) -> None:
    process_pipeline_job.send(str(job_id))


@dramatiq.actor(max_retries=1, min_backoff=2_000, max_backoff=10_000, time_limit=5 * 60 * 1000)
def process_zoning_ingest(parcel_id: int) -> None:
    from app.services.zoning_system import ingest_zoning_for_parcel_db

    async def _run() -> None:
        # Must create a fresh engine per asyncio.run() call — the shared engine's
        # internal asyncio locks are bound to the process's main event loop, which
        # is destroyed and recreated each time asyncio.run() is called from a
        # Dramatiq worker thread, causing "bound to a different event loop" errors.
        # Use the shared `make_engine` so this engine inherits the asyncpg `init`
        # hook that forces default_transaction_read_only=off on each new
        # connection — without it, Supabase pgBouncer can hand us a connection
        # that ReadOnlySQLTransactionError-fails the first INSERT.
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from app.db import make_engine

        engine = make_engine()
        local_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with local_session() as db:
                try:
                    await ingest_zoning_for_parcel_db(parcel_id, db)
                    await db.commit()
                except Exception:
                    try:
                        await db.commit()
                    except Exception:
                        await db.rollback()
                    raise
        finally:
            await engine.dispose()

    asyncio.run(_run())


def enqueue_zoning_ingest(parcel_id: int) -> None:
    process_zoning_ingest.send(parcel_id)
