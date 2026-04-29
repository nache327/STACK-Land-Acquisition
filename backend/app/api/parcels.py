"""
GET /api/jurisdictions/:id/parcels — filtered parcel list (Phase 2+)
GET /api/parcels/:id               — single parcel detail (drawer)
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.parcel import Parcel
from app.models.zone_use_matrix import ZoneUseMatrix, UsePermission
from app.schemas.parcel import (
    CandidateParcelSearchRequest,
    CandidateParcelSearchResponse,
    ParcelDetail,
    ParcelListResponse,
    ParcelRead,
)
from app.services.candidate_search import search_candidate_parcels
from app.services.zoning_system import get_zoning_from_db

router = APIRouter(tags=["parcels"])


@router.post("/parcels/search", response_model=CandidateParcelSearchResponse)
async def candidate_parcel_search(
    payload: CandidateParcelSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> CandidateParcelSearchResponse:
    return await search_candidate_parcels(payload, db)


_storage_perm_expr = case(
    (
        or_(
            ZoneUseMatrix.self_storage == UsePermission.permitted,
            ZoneUseMatrix.mini_warehouse == UsePermission.permitted,
            ZoneUseMatrix.luxury_garage_condo == UsePermission.permitted,
        ),
        "permitted",
    ),
    (
        or_(
            ZoneUseMatrix.self_storage == UsePermission.conditional,
            ZoneUseMatrix.mini_warehouse == UsePermission.conditional,
            ZoneUseMatrix.luxury_garage_condo == UsePermission.conditional,
        ),
        "conditional",
    ),
    (
        and_(
            ZoneUseMatrix.self_storage == UsePermission.prohibited,
            ZoneUseMatrix.mini_warehouse == UsePermission.prohibited,
        ),
        "prohibited",
    ),
    (
        or_(
            ZoneUseMatrix.self_storage == UsePermission.unclear,
            ZoneUseMatrix.mini_warehouse == UsePermission.unclear,
        ),
        "unclear",
    ),
    (ZoneUseMatrix.zone_code.isnot(None), "prohibited"),
    else_="unclassified",
).label("storage_permission")

_zum_join = and_(
    ZoneUseMatrix.jurisdiction_id == Parcel.jurisdiction_id,
    ZoneUseMatrix.zone_code == Parcel.zoning_code,
)


@router.get("/jurisdictions/{jurisdiction_id}/parcels", response_model=ParcelListResponse)
async def list_parcels(
    jurisdiction_id: uuid.UUID,
    zones: Optional[list[str]] = Query(None),
    zone_classes: Optional[list[str]] = Query(None),
    storage_permissions: Optional[list[str]] = Query(None),
    min_acres: Optional[float] = Query(None, ge=0),
    max_acres: Optional[float] = Query(None, ge=0),
    exclude_flood: bool = Query(False),
    exclude_wetland: bool = Query(False),
    vacant_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    filters = [Parcel.jurisdiction_id == jurisdiction_id]

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

    having_storage = None
    if storage_permissions:
        having_storage = _storage_perm_expr.in_(storage_permissions)

    base_q = (
        select(Parcel, _storage_perm_expr)
        .outerjoin(ZoneUseMatrix, _zum_join)
        .where(and_(*filters))
    )

    if having_storage is not None:
        base_q = base_q.where(having_storage)

    count_q = select(func.count()).select_from(base_q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    q = base_q.order_by(Parcel.acres.desc().nullslast()).offset(offset).limit(page_size)
    result = await db.execute(q)
    rows = result.all()

    items = [
        ParcelRead.model_validate(row[0]).model_copy(update={"storage_permission": row[1]})
        for row in rows
    ]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


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
    return {
        str(row.zone_class.value if hasattr(row.zone_class, "value") else row.zone_class): row.cnt
        for row in result.all()
    }


@router.get("/parcels/{parcel_id}", response_model=ParcelDetail)
async def get_parcel(
    parcel_id: int,
    db: AsyncSession = Depends(get_db),
) -> Parcel:
    parcel = await db.get(Parcel, parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return parcel


@router.get("/parcel/{parcel_id}/zoning")
@router.get("/parcels/{parcel_id}/zoning")
async def get_parcel_zoning(
    parcel_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    parcel = await db.get(Parcel, parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    zoning = await get_zoning_from_db(parcel_id, db)
    await db.commit()
    if zoning is None:
        return {
            "parcel_id": parcel_id,
            "zoning_status": "pending",
            "rule": None,
            "overlay": None,
            "message": "Zoning data is being ingested",
        }
    rule = zoning["rule"]
    overlay = zoning["overlay"]
    cache = zoning["cache"]
    return {
        "parcel_id": parcel_id,
        "zoning_status": cache.zoning_status if cache else "found",
        "rule": {
            "id": str(rule.id),
            "city": rule.city,
            "zone_code": rule.zone_code,
            "density": rule.density,
            "max_units": rule.max_units,
            "min_lot_size": rule.min_lot_size,
            "setbacks": rule.setbacks,
            "height_limit": rule.height_limit,
            "source": rule.source,
            "confidence": rule.confidence,
            "created_at": rule.created_at,
        },
        "overlay": {
            "id": str(overlay.id),
            "source_type": overlay.source_type,
            "raw_data": overlay.raw_data,
            "created_at": overlay.created_at,
        },
        "enrichment": {
            "slope": cache.slope if cache else None,
            "flood_zone": cache.flood_zone if cache else None,
            "raw_json": cache.raw_json if cache else None,
            "last_updated": cache.last_updated if cache else None,
        },
    }
