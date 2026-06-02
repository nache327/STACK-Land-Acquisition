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
    # 60 min so the largest jurisdictions (NYC MapPLUTO: 856k parcels at
    # ~6 min download + 16 min ingest + 5 min zoning + 5 min overlays ≈
    # 32 min total) finish in one pipeline run instead of being killed at
    # 30 min mid-overlay and needing manual /run-bulk-zoning-overlays.
    time_limit=60 * 60 * 1000,
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


@dramatiq.actor(
    # Tract-clustered precompute on a 1500-tract county is ~5-10 min;
    # 30-min ceiling gives headroom for slow days and biggest counties.
    max_retries=1,
    min_backoff=30_000,
    max_backoff=120_000,
    time_limit=30 * 60 * 1000,
)
def process_ring_metrics_precompute(jurisdiction_id: str) -> None:
    """Worker actor that fills parcel_ring_metrics for a jurisdiction.

    Used by the pipeline's post-ingest hook so the dashboard's ring data is
    ready before the operator opens the page. The admin endpoint runs the
    same service directly via BackgroundTasks (so it can write Redis-backed
    job state for polling); this actor is fire-and-forget."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from app.db import make_engine
    from app.services.ring_metrics_precompute import (
        precompute_ring_metrics_for_jurisdiction,
    )
    from app.services.buybox_scoring import auto_score_jurisdiction

    async def _run() -> None:
        # Fresh engine per asyncio.run() — see process_zoning_ingest for the
        # explanation of why the shared engine doesn't work from a Dramatiq
        # worker thread.
        engine = make_engine()
        sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        jid = uuid.UUID(jurisdiction_id)
        try:
            async with sessionmaker() as db:
                await precompute_ring_metrics_for_jurisdiction(jid, db)
        finally:
            await engine.dispose()

        # Re-score AFTER ring-metrics are populated. The pipeline's own
        # auto_score runs near the end of ingest, but this precompute actor
        # runs in a separate process and frequently finishes its Mapbox pass
        # AFTER that scoring already read parcel_ring_metrics — so the buy-box
        # scores were computed against NULL demographics/wealth-density. A
        # re-score here guarantees the persisted scores reflect the warm ring
        # cache regardless of which process won the race. Non-fatal: a scoring
        # gap (e.g. no default filter) shouldn't fail the precompute. Uses its
        # own raw-asyncpg connection (auto_score_jurisdiction self-manages).
        try:
            rescored = await auto_score_jurisdiction(jid)
            logger.info(
                "ring_metrics_precompute: re-scored %d parcels for %s after precompute",
                rescored, jurisdiction_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ring_metrics_precompute: post-precompute re-score failed "
                "(non-fatal) for %s: %s",
                jurisdiction_id, exc,
            )

    asyncio.run(_run())


def enqueue_ring_metrics_precompute(jurisdiction_id: uuid.UUID) -> None:
    process_ring_metrics_precompute.send(str(jurisdiction_id))
