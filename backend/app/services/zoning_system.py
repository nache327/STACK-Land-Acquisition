from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_step import JobStep
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.models.zoning_record import EnrichmentCache, ZoningOverlay, ZoningRule
from app.services.job_tracking import now_utc, truncate_error

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(hours=24)


def _strip_state_suffix(name: str) -> str:
    """Drop a trailing ', XX' state code so 'Salt Lake City, UT' → 'Salt Lake City'."""
    if "," not in name:
        return name.strip()
    head, tail = name.rsplit(",", 1)
    tail = tail.strip()
    if len(tail) == 2 and tail.isalpha() and tail.isupper():
        return head.strip()
    return name.strip()


async def _resolve_city(parcel: Parcel, db: AsyncSession) -> str:
    """Jurisdiction-first city resolution.

    Order of precedence:
        1. parcel.city  (already backfilled from jurisdictions.name)
        2. jurisdictions.name via parcel.jurisdiction_id
        3. address parsing  — only as a last resort, since address strings
           come from messy upstream parcel sources and frequently misclassify
           a county as a city.
        4. literal "unknown"
    """
    if parcel.city:
        return _strip_state_suffix(parcel.city)
    if parcel.jurisdiction_id is not None:
        jurisdiction = await db.get(Jurisdiction, parcel.jurisdiction_id)
        if jurisdiction and jurisdiction.name:
            return _strip_state_suffix(jurisdiction.name)
    if parcel.address and "," in parcel.address:
        return parcel.address.split(",")[-2].strip()
    return "unknown"


async def _resolve_state(parcel: Parcel, db: AsyncSession) -> str | None:
    if parcel.state:
        return parcel.state
    if parcel.jurisdiction_id is not None:
        jurisdiction = await db.get(Jurisdiction, parcel.jurisdiction_id)
        if jurisdiction and jurisdiction.state:
            return jurisdiction.state
    return None


async def lookup_zoning_for_parcel(
    parcel: Parcel,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """Fast deterministic lookup.

    This intentionally prefers already-owned parcel attributes. If a future
    authoritative service is available, swap it in here without changing the
    feasibility pipeline.
    """
    if not parcel.zoning_code:
        return None
    return {
        "city": await _resolve_city(parcel, db),
        "state": await _resolve_state(parcel, db),
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

        result = await lookup_zoning_for_parcel(parcel, db)
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


async def bulk_ingest_zoning_for_jurisdiction(
    jurisdiction_id: Any,
    db: AsyncSession,
) -> int:
    """Bulk-create ZoningRules + ZoningOverlays from parcel.zoning_code in two SQL passes.

    Returns the number of ZoningOverlays inserted. Replaces the per-parcel
    Dramatiq worker path so the pipeline never enters pending_zoning limbo.
    """
    jid = str(jurisdiction_id)

    # Cap the INSERT statements so lock contention never hangs the pipeline.
    await db.execute(text("SET LOCAL statement_timeout = '60s'"))
    # Fail fast if we can't acquire a row lock — don't wait 60s for a stale connection to release.
    await db.execute(text("SET LOCAL lock_timeout = '5s'"))

    # Fast skip: if every zoned parcel already has an overlay, nothing to do.
    zoned_count = await db.scalar(text(
        "SELECT COUNT(*) FROM parcels "
        "WHERE jurisdiction_id = CAST(:jid AS uuid) "
        "AND zoning_code IS NOT NULL AND zoning_code != ''"
    ), {"jid": jid})
    if not zoned_count:
        logger.info("No zoned parcels for jurisdiction %s — skipping bulk zoning", jurisdiction_id)
        return 0

    overlay_count = await db.scalar(text(
        "SELECT COUNT(o.id) FROM zoning_overlays o "
        "JOIN parcels p ON p.id = o.parcel_id "
        "WHERE p.jurisdiction_id = CAST(:jid AS uuid)"
    ), {"jid": jid})
    if overlay_count and overlay_count >= zoned_count * 0.99:
        logger.info(
            "Bulk zoning already complete for %s (%d overlays / %d zoned parcels) — skipping",
            jurisdiction_id, overlay_count, zoned_count,
        )
        return 0

    try:
        # Step 1: ensure a ZoningRule row exists for every distinct (city, zone_code) pair
        await db.execute(text("""
            INSERT INTO zoning_rules (id, city, zone_code, source, confidence)
            SELECT
                gen_random_uuid(),
                COALESCE(NULLIF(TRIM(p.city), ''), 'unknown') AS city,
                p.zoning_code,
                'parcel_ingest',
                0.75
            FROM parcels p
            WHERE p.jurisdiction_id = CAST(:jid AS uuid)
              AND p.zoning_code IS NOT NULL
              AND p.zoning_code != ''
            GROUP BY COALESCE(NULLIF(TRIM(p.city), ''), 'unknown'), p.zoning_code
            ON CONFLICT (city, zone_code) DO NOTHING
        """), {"jid": jid})

        # Step 2: insert ZoningOverlays for every parcel that has a zoning_code but no overlay yet
        overlay_result = await db.execute(text("""
            INSERT INTO zoning_overlays (id, parcel_id, zoning_rule_id, source_type, raw_data)
            SELECT
                gen_random_uuid(),
                p.id,
                r.id,
                'authoritative',
                jsonb_build_object('parcel_id', p.id, 'apn', p.apn, 'zoning_code', p.zoning_code)
            FROM parcels p
            JOIN zoning_rules r
                ON r.city = COALESCE(NULLIF(TRIM(p.city), ''), 'unknown')
               AND r.zone_code = p.zoning_code
            LEFT JOIN zoning_overlays o ON o.parcel_id = p.id
            WHERE p.jurisdiction_id = CAST(:jid AS uuid)
              AND p.zoning_code IS NOT NULL
              AND p.zoning_code != ''
              AND o.id IS NULL
        """), {"jid": jid})
        overlays_inserted = overlay_result.rowcount
    except Exception as exc:
        # LockNotAvailable (55P03) or statement timeout — prior run's overlays are still intact.
        logger.warning(
            "bulk_ingest_zoning lock/timeout for %s — skipping inserts: %s",
            jurisdiction_id, exc,
        )
        await db.rollback()
        return 0

    # Step 3: mark parcels without zoning_code as "missing" in enrichment_cache
    # so enqueue_missing_zoning_for_jurisdiction doesn't queue them as workers
    await db.execute(text("""
        INSERT INTO enrichment_cache (id, parcel_id, zoning_status, raw_json, last_updated)
        SELECT
            gen_random_uuid(),
            p.id,
            'missing',
            '{"reason": "no zoning_code in parcel data"}'::jsonb,
            NOW()
        FROM parcels p
        LEFT JOIN enrichment_cache ec ON ec.parcel_id = p.id
        WHERE p.jurisdiction_id = CAST(:jid AS uuid)
          AND (p.zoning_code IS NULL OR p.zoning_code = '')
          AND ec.id IS NULL
        ON CONFLICT (parcel_id) DO NOTHING
    """), {"jid": jid})

    logger.info(
        "Bulk zoning ingest for jurisdiction %s: inserted %d ZoningOverlays",
        jurisdiction_id, overlays_inserted,
    )
    return overlays_inserted
