from __future__ import annotations

import json
from typing import Any

from sqlalchemy import and_, asc, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parcel import Parcel
from app.models.zone_use_matrix import UsePermission, ZoneUseMatrix
from app.schemas.parcel import (
    CandidateParcelRow,
    CandidateParcelSearchRequest,
    CandidateParcelSearchResponse,
    ParcelSearchSort,
    TargetUse,
)


TARGET_USE_COLUMN = {
    TargetUse.self_storage: ZoneUseMatrix.self_storage,
}

_PERMISSION_LABEL = case(
    (ZoneUseMatrix.self_storage == UsePermission.permitted, "permitted"),
    (ZoneUseMatrix.self_storage == UsePermission.conditional, "conditional"),
    (ZoneUseMatrix.self_storage == UsePermission.prohibited, "prohibited"),
    (ZoneUseMatrix.self_storage == UsePermission.unclear, "unclear"),
    else_="unclassified",
)

_GARAGE_PERM_LABEL = case(
    (ZoneUseMatrix.luxury_garage_condo == UsePermission.permitted, "permitted"),
    (ZoneUseMatrix.luxury_garage_condo == UsePermission.conditional, "conditional"),
    (ZoneUseMatrix.luxury_garage_condo == UsePermission.prohibited, "prohibited"),
    (ZoneUseMatrix.luxury_garage_condo == UsePermission.unclear, "unclear"),
    else_="unclassified",
)


def _sort_clause(sort: ParcelSearchSort) -> tuple[Any, ...]:
    if sort == ParcelSearchSort.acres_asc:
        return (asc(Parcel.acres).nullslast(), asc(Parcel.id))
    if sort == ParcelSearchSort.apn_asc:
        return (asc(Parcel.apn), asc(Parcel.id))
    if sort == ParcelSearchSort.address_asc:
        return (asc(Parcel.address).nullslast(), asc(Parcel.id))
    return (desc(Parcel.acres).nullslast(), asc(Parcel.id))


def _build_violation_reasons(
    *,
    storage_allowed: bool,
    storage_conditional: bool,
    has_structure: bool | None,
    in_flood_zone: bool,
    in_wetland: bool,
) -> list[str]:
    reasons: list[str] = []
    if not storage_allowed and not storage_conditional:
        reasons.append("zoning_not_allowed")
    if has_structure is True:
        reasons.append("has_structure")
    elif has_structure is None:
        reasons.append("vacancy_unknown")
    if in_flood_zone:
        reasons.append("in_flood_zone")
    if in_wetland:
        reasons.append("in_wetland")
    return reasons


async def search_candidate_parcels(
    payload: CandidateParcelSearchRequest,
    db: AsyncSession,
) -> CandidateParcelSearchResponse:
    target_column = TARGET_USE_COLUMN[payload.target_use]
    permission_join = and_(
        ZoneUseMatrix.jurisdiction_id == Parcel.jurisdiction_id,
        ZoneUseMatrix.zone_code == Parcel.zoning_code,
    )

    conditions: list[Any] = [
        Parcel.jurisdiction_id == payload.jurisdiction_id,
    ]

    filters = payload.filters
    if filters.zones:
        conditions.append(Parcel.zoning_code.in_(filters.zones))
    if filters.zone_classes:
        conditions.append(Parcel.zone_class.in_(filters.zone_classes))
    if filters.storage_permissions:
        # Map frontend strings to UsePermission enum values for the filter
        perm_map = {
            "permitted": UsePermission.permitted,
            "conditional": UsePermission.conditional,
            "prohibited": UsePermission.prohibited,
            "unclear": UsePermission.unclear,
        }
        mapped = [perm_map[p] for p in filters.storage_permissions if p in perm_map]
        if "unclassified" in filters.storage_permissions:
            # unclassified = no zone_use_matrix row at all
            conditions.append(
                or_(target_column.in_(mapped), target_column.is_(None))
                if mapped else target_column.is_(None)
            )
        elif mapped:
            conditions.append(target_column.in_(mapped))
    if filters.min_acres is not None:
        conditions.append(Parcel.acres >= filters.min_acres)
    if filters.max_acres is not None:
        conditions.append(Parcel.acres <= filters.max_acres)
    if filters.vacant_only:
        conditions.append(Parcel.has_structure.is_(False))
    if filters.exclude_flood:
        conditions.append(Parcel.in_flood_zone.is_(False))
    if filters.exclude_wetland:
        conditions.append(Parcel.in_wetland.is_(False))

    if payload.search:
        query = payload.search.strip()
        if query:
            search_value = f"%{query}%"
            conditions.append(
                or_(
                    Parcel.apn.ilike(search_value),
                    Parcel.address.ilike(search_value),
                )
            )

    if payload.bbox:
        xmin, ymin, xmax, ymax = payload.bbox
        bbox = func.ST_MakeEnvelope(xmin, ymin, xmax, ymax, 4326)
        conditions.append(func.ST_Intersects(Parcel.geom, bbox))

    count_stmt = (
        select(func.count())
        .select_from(Parcel)
        .outerjoin(ZoneUseMatrix, permission_join)
        .where(*conditions)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (payload.page - 1) * payload.page_size
    row_stmt = (
        select(
            Parcel.id.label("parcel_id"),
            Parcel.apn,
            Parcel.address,
            Parcel.acres,
            Parcel.zoning_code,
            Parcel.zone_class,
            Parcel.in_flood_zone,
            Parcel.in_wetland,
            Parcel.has_structure,
            target_column.label("target_permission"),
            _PERMISSION_LABEL.label("storage_permission"),
            _GARAGE_PERM_LABEL.label("garage_permission"),
            func.ST_AsGeoJSON(
                func.ST_SimplifyPreserveTopology(Parcel.geom, 0.00001)
            ).label("geom"),
        )
        .select_from(Parcel)
        .outerjoin(ZoneUseMatrix, permission_join)
        .where(*conditions)
        .order_by(*_sort_clause(payload.sort))
        .offset(offset)
        .limit(payload.page_size)
    )

    result = await db.execute(row_stmt)
    items: list[CandidateParcelRow] = []
    for row in result:
        permission = row.target_permission
        if hasattr(permission, "value"):
            permission = permission.value
        storage_allowed = permission == UsePermission.permitted.value
        storage_conditional = permission == UsePermission.conditional.value
        violation_reasons = _build_violation_reasons(
            storage_allowed=storage_allowed,
            storage_conditional=storage_conditional,
            has_structure=row.has_structure,
            in_flood_zone=row.in_flood_zone,
            in_wetland=row.in_wetland,
        )
        geom = json.loads(row.geom) if row.geom else None
        items.append(
            CandidateParcelRow(
                parcel_id=row.parcel_id,
                apn=row.apn,
                address=row.address,
                acres=float(row.acres) if row.acres is not None else None,
                zoning_code=row.zoning_code,
                zone_class=row.zone_class,
                storage_permission=row.storage_permission,
                garage_permission=row.garage_permission,
                storage_allowed=storage_allowed,
                storage_conditional=storage_conditional,
                in_flood_zone=row.in_flood_zone,
                in_wetland=row.in_wetland,
                has_structure=row.has_structure,
                is_viable=len(violation_reasons) == 0,
                violation_reasons=violation_reasons,
                geom=geom,
            )
        )

    return CandidateParcelSearchResponse(
        items=items,
        total=total,
        page=payload.page,
        page_size=payload.page_size,
    )
