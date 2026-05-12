"""
GET /api/jurisdictions/:id/parcels — filtered parcel list (Phase 2+)
GET /api/parcels/:id               — single parcel detail (drawer)
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_, select, text
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


# ─── Wealth-density endpoint ──────────────────────────────────────────────
#
# Returns the count of residential parcels in a polygon whose total
# assessed value is at least 1M / 2M / 5M. Backs the "Wealth density"
# buy-box sliders. Result is upserted into parcel_ring_metrics so a
# repeat call for the same (parcel_id, drive_time_minutes) is cached.

from pydantic import BaseModel  # noqa: E402  (kept local to the endpoint)
from app.config import settings  # noqa: E402


class _ValueDensityRequest(BaseModel):
    polygon: dict  # GeoJSON geometry (Polygon or MultiPolygon)
    parcel_id: int | None = None
    drive_time_minutes: int | None = None


class _ValueDensityResponse(BaseModel):
    homes_over_1m: int
    homes_over_2m: int
    homes_over_5m: int
    cached: bool


@router.post("/parcels/value-density", response_model=_ValueDensityResponse)
async def value_density(
    payload: _ValueDensityRequest,
    db: AsyncSession = Depends(get_db),
) -> _ValueDensityResponse:
    """Count residential parcels above $1M / $2M / $5M inside a polygon.

    The polygon is typically a drive-time isochrone ring generated by
    the frontend via Mapbox. When ``parcel_id`` + ``drive_time_minutes``
    are supplied, the result is upserted into ``parcel_ring_metrics``
    keyed by that pair so subsequent identical requests skip the spatial
    query.

    Returns ``{homes_over_1m, homes_over_2m, homes_over_5m, cached}``.
    """
    import json as _json

    # Fast-path: if the caller passed parcel_id + drive_time and the
    # row is already populated, skip the spatial query.
    if payload.parcel_id is not None and payload.drive_time_minutes is not None:
        cached = (await db.execute(
            text(
                """
                SELECT homes_over_1m, homes_over_2m, homes_over_5m
                FROM parcel_ring_metrics
                WHERE parcel_id = :pid AND drive_time_minutes = :dt
                """
            ),
            {"pid": payload.parcel_id, "dt": payload.drive_time_minutes},
        )).fetchone()
        if cached is not None and cached[0] is not None:
            return _ValueDensityResponse(
                homes_over_1m=cached[0] or 0,
                homes_over_2m=cached[1] or 0,
                homes_over_5m=cached[2] or 0,
                cached=True,
            )

    # Use the shared SQLAlchemy session/pool. The earlier version opened
    # a fresh asyncpg connection per call which exhausted Supabase's
    # connection limit under burst load (16+ concurrent ring fetches
    # from the precompute) and 500'd. Pool handles that automatically;
    # this query is a single SELECT + UPSERT, well under any reasonable
    # statement_timeout.
    polygon_json = _json.dumps(payload.polygon)
    row = (await db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE assessed_value >= 1000000)::int AS o1,
              COUNT(*) FILTER (WHERE assessed_value >= 2000000)::int AS o2,
              COUNT(*) FILTER (WHERE assessed_value >= 5000000)::int AS o5
            FROM parcels
            WHERE is_residential IS TRUE
              AND assessed_value IS NOT NULL
              AND ST_Within(centroid, ST_GeomFromGeoJSON(:poly))
            """
        ),
        {"poly": polygon_json},
    )).fetchone()
    o1 = (row.o1 if row else 0) or 0
    o2 = (row.o2 if row else 0) or 0
    o5 = (row.o5 if row else 0) or 0

    if payload.parcel_id is not None and payload.drive_time_minutes is not None:
        await db.execute(
            text(
                """
                INSERT INTO parcel_ring_metrics
                  (parcel_id, drive_time_minutes, homes_over_1m, homes_over_2m, homes_over_5m)
                VALUES (:pid, :dt, :o1, :o2, :o5)
                ON CONFLICT (parcel_id, drive_time_minutes) DO UPDATE
                  SET homes_over_1m = EXCLUDED.homes_over_1m,
                      homes_over_2m = EXCLUDED.homes_over_2m,
                      homes_over_5m = EXCLUDED.homes_over_5m,
                      computed_at   = NOW()
                """
            ),
            {
                "pid": payload.parcel_id,
                "dt": payload.drive_time_minutes,
                "o1": o1, "o2": o2, "o5": o5,
            },
        )
        await db.commit()

    return _ValueDensityResponse(
        homes_over_1m=o1, homes_over_2m=o2, homes_over_5m=o5, cached=False,
    )


# ─── Admin: backfill assessed_value + is_residential ─────────────────────
#
# One-shot HTTP wrapper around scripts/backfill_assessed_value.py. Lets us
# kick off the backfill from a curl after the migration deploys — no
# Railway shell access required.

@router.post("/parcels/_backfill-assessed-value")
async def backfill_assessed_value(
    state: str = Query(..., description="Two-letter state code (required)"),
    dry_run: bool = Query(default=False),
    batch_size: int = Query(default=5000, ge=100, le=20_000),
    start_id: int = Query(default=0, ge=0, description="Resume cursor; use last_id from previous call"),
    max_batches: int = Query(default=1, ge=1, le=20, description="Batches per HTTP call (each ~3s)"),
) -> dict:
    """Populate parcels.assessed_value + is_residential from parcels.raw.

    **Cursor-based**: each call runs at most ``max_batches`` batches of
    ``batch_size`` rows starting after ``start_id``, then returns the
    ``last_id`` so the caller can resume. Keeps each HTTP request inside
    Railway's reverse-proxy window. Idempotent — only touches rows where
    assessed_value OR is_residential is still NULL.

    Loop the caller side: while ``done`` is false, re-call with
    ``start_id = last_id``.
    """
    import asyncpg
    import json as _json
    from app.services.parcel_value_mapper import map_value_and_residential
    from app.config import settings as _settings

    state_u = state.upper()
    session_url = _settings.database_url.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    conn = await asyncpg.connect(
        session_url, statement_cache_size=0, command_timeout=120,
    )
    scanned = 0
    with_value = 0
    residential = 0
    last_id = start_id
    batches_done = 0
    done = False
    try:
        await conn.execute("SET statement_timeout = 0")
        for _ in range(max_batches):
            rows = await conn.fetch(
                """
                SELECT p.id, p.raw
                FROM parcels p
                JOIN jurisdictions j ON j.id = p.jurisdiction_id
                WHERE j.state = $1
                  AND p.id > $2
                  AND p.raw IS NOT NULL
                  AND (p.assessed_value IS NULL OR p.is_residential IS NULL)
                ORDER BY p.id
                LIMIT $3
                """,
                state_u, last_id, batch_size,
            )
            if not rows:
                done = True
                break

            updates: list[tuple[int, float | None, bool | None]] = []
            for r in rows:
                scanned += 1
                raw = r["raw"]
                if not isinstance(raw, dict):
                    try:
                        raw = _json.loads(raw) if raw else None
                    except Exception:
                        raw = None
                val, is_res = map_value_and_residential(state_u, raw or {})
                if val is not None:
                    with_value += 1
                if is_res is True:
                    residential += 1
                updates.append((r["id"], val, is_res))

            last_id = rows[-1]["id"]
            batches_done += 1
            if not dry_run:
                await conn.executemany(
                    """
                    UPDATE parcels
                    SET assessed_value = $2,
                        is_residential = $3
                    WHERE id = $1
                    """,
                    updates,
                )
    finally:
        await conn.close()

    return {
        "state": state_u,
        "dry_run": dry_run,
        "start_id": start_id,
        "last_id": last_id,
        "scanned": scanned,
        "with_value": with_value,
        "residential": residential,
        "batches_done": batches_done,
        "done": done,
    }
