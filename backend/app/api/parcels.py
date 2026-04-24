"""
GET /api/jurisdictions/:id/parcels — filtered parcel list (Phase 2+)
GET /api/parcels/:id               — single parcel detail (drawer)
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.parcel import Parcel
from app.schemas.parcel import (
    CandidateParcelSearchRequest,
    CandidateParcelSearchResponse,
    ParcelDetail,
    ParcelListResponse,
)
from app.services.candidate_search import search_candidate_parcels

router = APIRouter(tags=["parcels"])


@router.post("/parcels/search", response_model=CandidateParcelSearchResponse)
async def candidate_parcel_search(
    payload: CandidateParcelSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> CandidateParcelSearchResponse:
    return await search_candidate_parcels(payload, db)


@router.get("/jurisdictions/{jurisdiction_id}/parcels", response_model=ParcelListResponse)
async def list_parcels(
    jurisdiction_id: uuid.UUID,
    zones: Optional[list[str]] = Query(None),
    zone_classes: Optional[list[str]] = Query(None),
    min_acres: Optional[float] = Query(None, ge=0),
    max_acres: Optional[float] = Query(None, ge=0),
    exclude_flood: bool = Query(False),
    exclude_wetland: bool = Query(False),
    vacant_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    filters = []
    filters.append(Parcel.jurisdiction_id == jurisdiction_id)

    if zones:
        filters.append(Parcel.zoning_code.in_(zones))
    if zone_classes:
        filters.append(Parcel.zone_class.in_(zone_classes))
    if min_acres is not None:
        filters.append(Parcel.acres >= min_acres)
    if max_acres is not None:
        filters.append(Parcel.acres <= max_acres)
    if exclude_flood:
        filters.append(Parcel.in_flood_zone.is_(False))
    if exclude_wetland:
        filters.append(Parcel.in_wetland.is_(False))
    if vacant_only:
        filters.append(Parcel.has_structure.is_(False))

    count_q = select(func.count()).select_from(Parcel).where(and_(*filters))
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    q = (
        select(Parcel)
        .where(and_(*filters))
        .order_by(Parcel.acres.desc().nullslast())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(q)
    parcels = result.scalars().all()

    return {"items": parcels, "total": total, "page": page, "page_size": page_size}


@router.get("/jurisdictions/{jurisdiction_id}/parcels/zone-summary")
async def get_zone_summary(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return {zone_code: parcel_count} for all zones in the jurisdiction."""
    result = await db.execute(
        select(Parcel.zoning_code, func.count().label("cnt"))
        .where(
            Parcel.jurisdiction_id == jurisdiction_id,
            Parcel.zoning_code.isnot(None),
        )
        .group_by(Parcel.zoning_code)
        .order_by(func.count().desc())
    )
    return {row.zoning_code: row.cnt for row in result.all()}


@router.get("/jurisdictions/{jurisdiction_id}/parcels/zone-class-summary")
async def get_zone_class_summary(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return {zone_class: parcel_count} for all classified parcels in the jurisdiction."""
    result = await db.execute(
        select(Parcel.zone_class, func.count().label("cnt"))
        .where(
            Parcel.jurisdiction_id == jurisdiction_id,
            Parcel.zone_class.isnot(None),
        )
        .group_by(Parcel.zone_class)
        .order_by(func.count().desc())
    )
    return {str(row.zone_class.value if hasattr(row.zone_class, "value") else row.zone_class): row.cnt for row in result.all()}


@router.get("/parcels/{parcel_id}", response_model=ParcelDetail)
async def get_parcel(
    parcel_id: int,
    db: AsyncSession = Depends(get_db),
) -> Parcel:
    parcel = await db.get(Parcel, parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return parcel
