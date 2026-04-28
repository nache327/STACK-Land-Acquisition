from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_step import JobStep
from app.models.parcel import Parcel
from app.models.zoning_record import EnrichmentCache, ZoningOverlay, ZoningRule
from app.services.job_tracking import now_utc, truncate_error

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(hours=24)


def _parcel_city(parcel: Parcel) -> str:
    if parcel.city:
        return parcel.city
    if parcel.address and "," in parcel.address:
        return parcel.address.split(",")[-2].strip()
    return "unknown"


def _parcel_state(parcel: Parcel) -> str | None:
    return parcel.state


async def lookup_zoning_for_parcel(parcel: Parcel) -> dict[str, Any] | None:
    """Fast deterministic lookup.

    This intentionally prefers already-owned parcel attributes. If a future
    authoritative service is available, swap it in here without changing the
    feasibility pipeline.
    """
    if not parcel.zoning_code:
        return None
    return {
        "city": _parcel_city(parcel),
        "state": _parcel_state(parcel),
        "zone_code": parcel.zoning_code,
        "density": None,
        "max_units": None,
        "min_lot_size": None,
        "setbacks": None,
        "height_limit": None,
        "source": "parcel_ingest",
        "confidence": 0.75,
        "raw": {
            "parcel_id": parcel.id,
            "apn": parcel.apn,
            "zoning_code": parcel.zoning_code,
            "zone_class": parcel.zone_class.value if parcel.zone_class else None,
        },
    }


async def _upsert_enrichment_cache(
    db: AsyncSession,
    parcel_id: int,
    zoning_status: str,
    raw_json: dict[str, Any] | None = None,
) -> None:
    stmt = pg_insert(EnrichmentCache).values(
        parcel_id=parcel_id,
        zoning_status=zoning_status,
        raw_json=raw_json or {},
        last_updated=now_utc(),
    ).on_conflict_do_update(
        index_elements=[EnrichmentCache.parcel_id],
        set_={
            "zoning_status": zoning_status,
            "raw_json": raw_json or {},
            "last_updated": now_utc(),
        },
    )
    await db.execute(stmt)


async def ingest_zoning_for_parcel_db(
    parcel_id: int,
    db: AsyncSession,
    attempt: int = 1,
) -> bool:
    logger.info("ZONING INGEST STARTED for parcel %s (attempt=%s)", parcel_id, attempt)
    started = time.perf_counter()
    step = JobStep(
        job_id=None,
        step="zoning_ingest",
        status="running",
        attempt=attempt,
        started_at=now_utc(),
        step_metadata={"parcel_id": parcel_id},
    )
    db.add(step)
    await db.flush()

    try:
        parcel = await db.get(Parcel, parcel_id)
        if parcel is None:
            raise ValueError(f"Parcel {parcel_id} not found")

        result = await lookup_zoning_for_parcel(parcel)
        if result is None:
            await _upsert_enrichment_cache(
                db,
                parcel_id,
                "missing",
                {"reason": "parcel has no zoning_code"},
            )
            step.status = "success"
            step.step_metadata = {"parcel_id": parcel_id, "zoning_status": "missing"}
            logger.info("ZONING INGEST COMPLETED for parcel %s (status=missing)", parcel_id)
            return False

        rule_result = await db.execute(
            select(ZoningRule).where(
                ZoningRule.city == result["city"],
                ZoningRule.zone_code == result["zone_code"],
            )
        )
        rule = rule_result.scalar_one_or_none()
        if rule is None:
            rule = ZoningRule(
                city=result["city"],
                zone_code=result["zone_code"],
                density=result["density"],
                max_units=result["max_units"],
                min_lot_size=result["min_lot_size"],
                setbacks=result["setbacks"],
                height_limit=result["height_limit"],
                source=result["source"],
                confidence=result["confidence"],
            )
            db.add(rule)
            await db.flush()

        overlay = ZoningOverlay(
            parcel_id=parcel_id,
            zoning_rule_id=rule.id,
            source_type="authoritative" if result["source"] != "fallback" else "fallback",
            raw_data=result["raw"],
        )
        db.add(overlay)
        await _upsert_enrichment_cache(db, parcel_id, "found", result["raw"])

        step.status = "success"
        step.step_metadata = {
            "parcel_id": parcel_id,
            "zoning_status": "found",
            "zoning_rule_id": str(rule.id),
        }
        logger.info(
            "ZONING INGEST COMPLETED for parcel %s (status=found, rule=%s)",
            parcel_id,
            rule.id,
        )
        return True
    except Exception as exc:
        step.status = "failure"
        step.error = truncate_error(exc)
        await _upsert_enrichment_cache(
            db,
            parcel_id,
            "missing",
            {"error": truncate_error(exc)},
        )
        logger.error(
            "ZONING INGEST FAILED for parcel %s: %s",
            parcel_id,
            truncate_error(exc),
        )
        raise
    finally:
        finished = now_utc()
        step.finished_at = finished
        step.duration_ms = int((time.perf_counter() - started) * 1000)
        await db.flush()


async def should_reuse_zoning_cache(db: AsyncSession, parcel_id: int) -> bool:
    result = await db.execute(
        select(EnrichmentCache)
        .where(EnrichmentCache.parcel_id == parcel_id)
        .order_by(EnrichmentCache.last_updated.desc())
        .limit(1)
    )
    cache = result.scalar_one_or_none()
    if cache is None:
        return False
    return cache.last_updated >= now_utc() - CACHE_TTL and cache.zoning_status == "found"


async def get_zoning_from_db(parcel_id: int, db: AsyncSession) -> dict[str, Any] | None:
    result = await db.execute(
        select(ZoningOverlay, ZoningRule, EnrichmentCache)
        .join(ZoningRule, ZoningOverlay.zoning_rule_id == ZoningRule.id)
        .outerjoin(EnrichmentCache, EnrichmentCache.parcel_id == ZoningOverlay.parcel_id)
        .where(ZoningOverlay.parcel_id == parcel_id)
        .order_by(ZoningOverlay.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is not None:
        overlay, rule, cache = row
        if cache is None or cache.last_updated >= now_utc() - CACHE_TTL:
            return {
                "rule": rule,
                "overlay": overlay,
                "cache": cache,
            }

    from app.services.job_queue import enqueue_zoning_ingest

    enqueue_zoning_ingest(parcel_id)
    cache_result = await db.execute(
        select(EnrichmentCache).where(EnrichmentCache.parcel_id == parcel_id).limit(1)
    )
    if cache_result.scalar_one_or_none() is None:
        await _upsert_enrichment_cache(db, parcel_id, "pending", {"reason": "zoning ingest queued"})
        await db.flush()
    return None


async def enqueue_missing_zoning_for_jurisdiction(
    jurisdiction_id: Any,
    db: AsyncSession,
    limit: int = 1000,
) -> int:
    from app.services.job_queue import enqueue_zoning_ingest

    result = await db.execute(
        select(Parcel.id)
        .outerjoin(ZoningOverlay, ZoningOverlay.parcel_id == Parcel.id)
        .where(
            Parcel.jurisdiction_id == jurisdiction_id,
            ZoningOverlay.id.is_(None),
        )
        .limit(limit)
    )
    parcel_ids = [row[0] for row in result.all()]
    for parcel_id in parcel_ids:
        enqueue_zoning_ingest(parcel_id)
        await _upsert_enrichment_cache(
            db,
            parcel_id,
            "pending",
            {"reason": "jurisdiction pipeline queued zoning ingest"},
        )
    await db.flush()
    return len(parcel_ids)
