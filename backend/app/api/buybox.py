"""
Server-side buy-box API.

Endpoints (all scoped to the Default Organization until real auth lands):

  GET    /api/buybox-filters
  POST   /api/buybox-filters
  PATCH  /api/buybox-filters/{filter_id}
  DELETE /api/buybox-filters/{filter_id}
  GET    /api/parcels/{parcel_id}/score?filter_id=...
  GET    /api/jurisdictions/{jurisdiction_id}/scores?filter_id=...&min_score=...

The frontend reads scores from these endpoints to replace the placeholder
client-side `lib/compositeScore.ts` formula. Saved filters move out of
localStorage into `buybox_filters`, scoped per (organization, use_case).
"""
from __future__ import annotations

import uuid

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._auth import require_secret
from app.db import get_db
from app.models.buybox_filter import BuyboxFilter
from app.models.parcel_buybox_score import ParcelBuyboxScore
from app.models.use_case import UseCase
from app.schemas.buybox import (
    BuyboxFilterCreate,
    BuyboxFilterRead,
    BuyboxFilterUpdate,
    ParcelScoreRead,
)

router = APIRouter(tags=["buybox"])


# Hardcoded for the bootstrap phase. Real auth will replace these with
# session-derived values.
DEFAULT_ORG_ID            = uuid.UUID("00000000-0000-0000-0000-000000000001")
SELF_STORAGE_USE_CASE_ID  = uuid.UUID("00000000-0000-0000-0000-000000000002")


# ─── Filter CRUD ──────────────────────────────────────────────────────────

@router.get("/buybox-filters", response_model=list[BuyboxFilterRead])
async def list_filters(
    use_case_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[BuyboxFilter]:
    """List buy-box filters for the default org, optionally scoped to a use case."""
    stmt = select(BuyboxFilter).where(BuyboxFilter.organization_id == DEFAULT_ORG_ID)
    if use_case_id is not None:
        stmt = stmt.where(BuyboxFilter.use_case_id == use_case_id)
    stmt = stmt.order_by(
        BuyboxFilter.is_default.desc(),
        BuyboxFilter.updated_at.desc(),
    )
    result = await db.execute(stmt)
    return list(result.scalars())


@router.post("/buybox-filters", response_model=BuyboxFilterRead, status_code=201)
async def create_filter(
    payload: BuyboxFilterCreate,
    db: AsyncSession = Depends(get_db),
) -> BuyboxFilter:
    use_case_id = payload.use_case_id or SELF_STORAGE_USE_CASE_ID

    # Confirm the use_case exists and is either system-wide or owned by org.
    uc = await db.scalar(select(UseCase).where(UseCase.id == use_case_id))
    if uc is None:
        raise HTTPException(404, f"use_case {use_case_id} not found")
    if uc.organization_id is not None and uc.organization_id != DEFAULT_ORG_ID:
        raise HTTPException(403, "use_case belongs to a different organization")

    # If marking this filter as default, demote any existing default first.
    if payload.is_default:
        await _demote_existing_default(db, use_case_id)

    new = BuyboxFilter(
        organization_id=DEFAULT_ORG_ID,
        use_case_id=use_case_id,
        name=payload.name,
        filter_json=payload.filter_json,
        is_default=payload.is_default,
        daily_email_enabled=payload.daily_email_enabled,
        daily_email_top_n=payload.daily_email_top_n,
    )
    db.add(new)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "filter name already exists for this use case") from exc
    await db.refresh(new)
    return new


@router.patch("/buybox-filters/{filter_id}", response_model=BuyboxFilterRead)
async def update_filter(
    filter_id: uuid.UUID,
    payload: BuyboxFilterUpdate,
    db: AsyncSession = Depends(get_db),
) -> BuyboxFilter:
    f = await db.scalar(
        select(BuyboxFilter).where(
            and_(BuyboxFilter.id == filter_id,
                 BuyboxFilter.organization_id == DEFAULT_ORG_ID)
        )
    )
    if f is None:
        raise HTTPException(404, "filter not found")

    if payload.is_default is True and not f.is_default:
        await _demote_existing_default(db, f.use_case_id)
    if payload.name is not None:
        f.name = payload.name
    if payload.filter_json is not None:
        f.filter_json = payload.filter_json
    if payload.is_default is not None:
        f.is_default = payload.is_default
    if payload.daily_email_enabled is not None:
        f.daily_email_enabled = payload.daily_email_enabled
    if payload.daily_email_top_n is not None:
        f.daily_email_top_n = payload.daily_email_top_n

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "filter name conflict") from exc
    await db.refresh(f)
    return f


@router.post(
    "/buybox-filters/_run-digest",
    dependencies=[Depends(require_secret)],
)
async def run_digest_now(
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manual-trigger the daily digest worker. Used for smoke tests
    before cron is wired up; safe to leave enabled because the worker
    is idempotent (notified_at + 23h gate).

    ``?force=true`` bypasses the 23h cooldown so manual smoke tests can
    re-fire within the same day. Intended for manual testing only — do
    not wire this flag into cron. The per-parcel notified_at gate still
    applies, so force-running does not re-email parcels that already
    went out for that filter."""
    from app.workers.daily_email import run_once
    from app.config import settings as _settings

    enabled_total = await db.scalar(
        select(func.count(BuyboxFilter.id)).where(
            BuyboxFilter.daily_email_enabled.is_(True)
        )
    )
    result = await run_once(force=force)
    return {
        **result,
        "email_enabled_filters_in_db": int(enabled_total or 0),
        "resend_configured": "yes" if _settings.resend_enabled else "no",
        "recipient_configured": "yes" if _settings.digest_default_recipient else "no",
    }


@router.post(
    "/buybox-filters/{filter_id}/_clear-cooldown",
    dependencies=[Depends(require_secret)],
)
async def clear_digest_cooldown(
    filter_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Null the filter's ``last_email_sent_at`` so the next scheduled
    cron run isn't blocked by the 23h cooldown.

    Use this when a manual ``force=true`` digest poisoned the cooldown
    (legacy issue, since fixed) or any time the operator wants the next
    cron to fire regardless of when the last email actually went out.

    Per-parcel ``notified_at`` is NOT touched — listings that have been
    notified stay notified so the cron doesn't re-email the same
    parcels. Only the filter-level cooldown gate is cleared.
    """
    f = await db.scalar(
        select(BuyboxFilter).where(
            and_(
                BuyboxFilter.id == filter_id,
                BuyboxFilter.organization_id == DEFAULT_ORG_ID,
            )
        )
    )
    if f is None:
        raise HTTPException(404, "filter not found")
    previous = f.last_email_sent_at
    f.last_email_sent_at = None
    await db.commit()
    return {
        "filter_id": str(filter_id),
        "filter_name": f.name,
        "previous_last_email_sent_at": previous.isoformat() if previous else None,
        "cleared": True,
    }


@router.post(
    "/buybox-filters/_score-jurisdiction/{jurisdiction_id}",
    dependencies=[Depends(require_secret)],
)
async def run_auto_score_now(
    jurisdiction_id: uuid.UUID,
    filter_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int | None]:
    """Manual-trigger auto-scoring for a jurisdiction. By default scores
    against the org's default self_storage filter; pass ?filter_id=...
    to score against a specific one. Returns diagnostic counts so we
    can see why a 0-result happened (no parcels vs. no default filter)."""
    from app.services.buybox_scoring import score_jurisdiction
    import json as _json

    parcel_count = await db.scalar(
        text("SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = :jid").bindparams(
            jid=jurisdiction_id
        )
    )

    if filter_id is None:
        f = await db.scalar(
            select(BuyboxFilter).where(
                and_(
                    BuyboxFilter.organization_id == DEFAULT_ORG_ID,
                    BuyboxFilter.use_case_id == SELF_STORAGE_USE_CASE_ID,
                    BuyboxFilter.is_default.is_(True),
                )
            )
        )
        if f is None:
            return {
                "parcels_scored": 0,
                "parcel_count": parcel_count,
                "filter_id": None,
                "note": "no default BuyboxFilter for (default org × self_storage)",
            }
        filter_id = f.id
        filter_json = f.filter_json
    else:
        f = await db.scalar(select(BuyboxFilter).where(BuyboxFilter.id == filter_id))
        if f is None:
            raise HTTPException(404, "filter not found")
        filter_json = f.filter_json

    if isinstance(filter_json, str):
        filter_json = _json.loads(filter_json)

    n = await score_jurisdiction(jurisdiction_id, filter_id, filter_json or {})
    return {
        "parcels_scored": n,
        "parcel_count": parcel_count,
        "filter_id": str(filter_id),
    }


# Job state for _score-all lives in Redis (see services/job_state_store.py).
# Earlier versions used a module-level dict — a Railway deploy mid-run
# wiped state and the status endpoint returned 404 even though the work
# had succeeded server-side. Redis survives deploys and is shared if we
# ever scale to multiple instances.


@router.post(
    "/buybox-filters/{filter_id}/_score-all",
    status_code=202,
    dependencies=[Depends(require_secret)],
)
async def score_filter_across_all_jurisdictions(
    filter_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bootstrap a non-default filter by scoring every parcel in every
    jurisdiction against it. Runs as a background task; returns 202
    immediately with a ``job_id``. Poll
    ``GET /api/buybox-filters/_score-all-status/{job_id}`` for progress.

    The pipeline's per-ingest auto-scorer only runs the *default* filter
    for (org × use_case), so a newly-created filter like "Hot deals" has
    zero rows in parcel_buybox_scores until either a fresh jurisdiction
    is ingested or this endpoint is called.

    Idempotent: ``score_jurisdiction`` upserts via
    ``ON CONFLICT ... DO UPDATE`` on the (parcel_id, buybox_filter_id)
    PK, so re-running is safe and simply refreshes scores against the
    current filter_json + matcher logic.

    Per-jurisdiction failures are caught and reported in
    ``state.errors[]``; the loop continues so a single bad jurisdiction
    can't strand a bootstrap run.

    Why async: a single county can take 30-60s; a full sweep across 65+
    jurisdictions exceeds Railway's proxy timeout. Prior sync version
    returned HTTP 000 on curl while the work continued server-side —
    confusing for operators and impossible to verify completion.
    """
    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    f = await db.scalar(
        select(BuyboxFilter).where(
            and_(
                BuyboxFilter.id == filter_id,
                BuyboxFilter.organization_id == DEFAULT_ORG_ID,
            )
        )
    )
    if f is None:
        raise HTTPException(404, "filter not found")

    filter_json = f.filter_json
    if isinstance(filter_json, str):
        filter_json = _json.loads(filter_json)
    filter_json = filter_json or {}
    filter_name = f.name  # snapshot before session closes

    job_id = str(uuid.uuid4())
    state: dict[str, Any] = {
        "job_id": job_id,
        # Two-phase status so the operator can tell why "processed" is
        # 0 right after the POST returns: "enumerating" means we're
        # still figuring out which jurisdictions to score; "running"
        # means the per-jurisdiction loop is live.
        "status": "enumerating",
        "filter_id": str(filter_id),
        "filter_name": filter_name,
        "started_at": _dt.now(_tz.utc).isoformat(),
        "finished_at": None,
        "jurisdictions_total": None,  # populated by bg task once enumerated
        "jurisdictions_processed": 0,
        "parcels_scored": 0,
        "errors": [],
    }
    from app.services.job_state_store import set_job_state
    await set_job_state(job_id, state)

    async def _bg() -> None:
        import logging as _logging
        _log = _logging.getLogger(__name__)
        from app.db import async_session_maker
        from app.services.buybox_scoring import score_jurisdiction
        from app.services.job_state_store import set_job_state as _save

        try:
            # SELECT DISTINCT jurisdiction_id FROM parcels was the 50s
            # offender on the sync path. Move it inside the bg task so
            # the HTTP POST returns in <1s. The cost is that "running"
            # state isn't true until the enumeration finishes — the
            # status field reports "enumerating" during that window.
            async with async_session_maker() as bg_db:
                jids_result = await bg_db.execute(
                    text("SELECT DISTINCT jurisdiction_id FROM parcels "
                         "WHERE jurisdiction_id IS NOT NULL")
                )
                jurisdiction_ids = [row[0] for row in jids_result.all()]
            state["jurisdictions_total"] = len(jurisdiction_ids)
            state["status"] = "running"
            await _save(job_id, state)

            for jid in jurisdiction_ids:
                try:
                    n = await score_jurisdiction(jid, filter_id, filter_json)
                    state["parcels_scored"] += n
                    state["jurisdictions_processed"] += 1
                except Exception as e:  # noqa: BLE001 — surface, keep loop alive
                    _log.exception(
                        "score_jurisdiction failed for %s under filter %s",
                        jid, filter_id,
                    )
                    state["errors"].append({
                        "jurisdiction_id": str(jid),
                        "error": str(e),
                    })
                # Persist progress after each jurisdiction so the status
                # endpoint reflects work as it lands. Sliding 24h TTL
                # means a multi-hour run won't get evicted.
                await _save(job_id, state)
            state["status"] = "completed"
            _log.info(
                "score-all job=%s complete: filter=%s jurisdictions=%d/%d "
                "parcels_scored=%d errors=%d",
                job_id, filter_name,
                state["jurisdictions_processed"], len(jurisdiction_ids),
                state["parcels_scored"], len(state["errors"]),
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("score-all job=%s failed: %s", job_id, exc)
            state["status"] = "failed"
            state["errors"].append({"jurisdiction_id": None, "error": str(exc)})
        finally:
            state["finished_at"] = _dt.now(_tz.utc).isoformat()
            await _save(job_id, state)

    background_tasks.add_task(_bg)
    return {"job_id": job_id, "status": "enumerating"}


@router.get("/buybox-filters/_score-all-status/{job_id}")
async def score_all_status(job_id: str) -> dict[str, Any]:
    """Return the current state of an in-flight or completed _score-all
    job. 404 when the job_id is unknown (key missing or 24h TTL
    expired). Backed by Redis so it survives Railway restarts."""
    from app.services.job_state_store import get_job_state
    state = await get_job_state(job_id)
    if state is None:
        raise HTTPException(404, "score-all job not found (may have expired)")
    return state


@router.delete("/buybox-filters/{filter_id}", status_code=204)
async def delete_filter(
    filter_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        delete(BuyboxFilter).where(
            and_(BuyboxFilter.id == filter_id,
                 BuyboxFilter.organization_id == DEFAULT_ORG_ID)
        )
    )
    if result.rowcount == 0:
        raise HTTPException(404, "filter not found")
    await db.commit()


# ─── Score reads ──────────────────────────────────────────────────────────

@router.get(
    "/parcels/{parcel_id}/score",
    response_model=ParcelScoreRead,
)
async def get_parcel_score(
    parcel_id: int,
    filter_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ParcelBuyboxScore:
    """Read the precomputed score for a parcel under a given filter.
    If filter_id is omitted, returns the score under the default filter
    for the self_storage use case under the default org."""
    if filter_id is None:
        filter_id = await _resolve_default_filter_id(db, SELF_STORAGE_USE_CASE_ID)
        if filter_id is None:
            raise HTTPException(404, "no default filter configured")

    s = await db.scalar(
        select(ParcelBuyboxScore).where(
            and_(ParcelBuyboxScore.parcel_id == parcel_id,
                 ParcelBuyboxScore.buybox_filter_id == filter_id)
        )
    )
    if s is None:
        raise HTTPException(404, "no score for this parcel + filter")
    return s


@router.get(
    "/jurisdictions/{jurisdiction_id}/scores",
    response_model=list[ParcelScoreRead],
)
async def list_scores_for_jurisdiction(
    jurisdiction_id: uuid.UUID,
    filter_id: uuid.UUID | None = Query(default=None),
    use_case_id: uuid.UUID | None = Query(default=None),
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=500, ge=1, le=10_000),
    db: AsyncSession = Depends(get_db),
) -> list[ParcelBuyboxScore]:
    """Top-N scored parcels in a jurisdiction.

    Useful for the dashboard's initial paint — gets us a leaderboard
    without round-tripping per parcel.

    ``filter_id`` wins if given. Otherwise the default filter for
    ``use_case_id`` (or the self_storage use case when that's also omitted)
    is resolved — this is how the dashboard's asset toggle fetches LGC vs
    self_storage scores without knowing the filter ids.
    """
    if filter_id is None:
        filter_id = await _resolve_default_filter_id(
            db, use_case_id or SELF_STORAGE_USE_CASE_ID
        )
        if filter_id is None:
            # No default filter for this org × use case. Used to 404, which
            # crashed the dashboard's react-query path. Return an empty
            # list instead so the UI just shows no score badges.
            return []

    # Join through parcels to filter by jurisdiction.
    sql = text(
        """
        SELECT pbs.parcel_id, pbs.buybox_filter_id, pbs.score,
               pbs.tier, pbs.factors, pbs.computed_at
        FROM parcel_buybox_scores pbs
        JOIN parcels p ON p.id = pbs.parcel_id
        WHERE p.jurisdiction_id = :jid
          AND pbs.buybox_filter_id = :fid
          AND pbs.score >= :min_score
        ORDER BY pbs.score DESC, pbs.parcel_id
        LIMIT :lim
        """
    )
    result = await db.execute(
        sql,
        {"jid": jurisdiction_id, "fid": filter_id, "min_score": min_score, "lim": limit},
    )
    return [ParcelBuyboxScore(**dict(row._mapping)) for row in result]


# ─── Helpers ──────────────────────────────────────────────────────────────

async def _resolve_default_filter_id(
    db: AsyncSession, use_case_id: uuid.UUID
) -> uuid.UUID | None:
    return await db.scalar(
        select(BuyboxFilter.id).where(
            and_(
                BuyboxFilter.organization_id == DEFAULT_ORG_ID,
                BuyboxFilter.use_case_id == use_case_id,
                BuyboxFilter.is_default.is_(True),
            )
        )
    )


async def _demote_existing_default(
    db: AsyncSession, use_case_id: uuid.UUID
) -> None:
    """Unset is_default on the current default for (org, use_case) so the
    partial-unique index doesn't reject the new default."""
    await db.execute(
        update(BuyboxFilter)
        .where(
            and_(
                BuyboxFilter.organization_id == DEFAULT_ORG_ID,
                BuyboxFilter.use_case_id == use_case_id,
                BuyboxFilter.is_default.is_(True),
            )
        )
        .values(is_default=False)
    )
    # Flush so the unique index sees the demotion before the insert/update.
    await db.flush()
