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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "filter name conflict") from exc
    await db.refresh(f)
    return f


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
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=500, ge=1, le=10_000),
    db: AsyncSession = Depends(get_db),
) -> list[ParcelBuyboxScore]:
    """Top-N scored parcels in a jurisdiction.

    Useful for the dashboard's initial paint — gets us a leaderboard
    without round-tripping per parcel.
    """
    if filter_id is None:
        filter_id = await _resolve_default_filter_id(db, SELF_STORAGE_USE_CASE_ID)
        if filter_id is None:
            raise HTTPException(404, "no default filter configured")

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
