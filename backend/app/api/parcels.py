"""
GET /api/jurisdictions/:id/parcels — filtered parcel list (Phase 2+)
GET /api/parcels/:id               — single parcel detail (drawer)
"""
import hashlib
import json as _json
import os
import time as _time
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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


# ── /parcels/search response cache ───────────────────────────────────────────
#
# Mirrors the (jid, captured_at)-keyed memo pattern PR #201 added for
# /jurisdictions/{id}/parcels/map. The search endpoint has more cache-key
# variety than the bulk map endpoint (filter combinations, bbox windows,
# page/sort) so the cache key is a SHA256 over the canonical request
# payload + the latest `coverage_snapshots.captured_at` for the
# jurisdiction. When the audit refresh advances captured_at the key
# rotates and the next request rebuilds.
#
# Stored as already-serialized JSON bytes — cache hits skip the
# Postgres round-trip AND Pydantic's serialization.
#
# Cache-Control on a POST response is mostly cosmetic (HTTP caches
# don't cache POSTs by default), but Vercel's edge cache may honor it
# and a future migration to GET would pick it up for free.
_PARCELS_SEARCH_CACHE: "OrderedDict[str, tuple[float, bytes]]" = OrderedDict()
_PARCELS_SEARCH_CACHE_TTL_SECONDS = 300.0
_PARCELS_SEARCH_CACHE_MAX_ENTRIES = int(
    os.environ.get("_PARCELS_SEARCH_CACHE_MAX_ENTRIES", "64")
)
_PARCELS_SEARCH_CACHE_CONTROL = "public, s-maxage=60, stale-while-revalidate=300"


def _parcels_search_cache_get(key: str) -> bytes | None:
    entry = _PARCELS_SEARCH_CACHE.get(key)
    if entry is None:
        return None
    inserted_at, payload = entry
    if _time.monotonic() - inserted_at > _PARCELS_SEARCH_CACHE_TTL_SECONDS:
        _PARCELS_SEARCH_CACHE.pop(key, None)
        return None
    _PARCELS_SEARCH_CACHE.move_to_end(key)
    return payload


def _parcels_search_cache_set(key: str, payload: bytes) -> None:
    _PARCELS_SEARCH_CACHE[key] = (_time.monotonic(), payload)
    _PARCELS_SEARCH_CACHE.move_to_end(key)
    while len(_PARCELS_SEARCH_CACHE) > _PARCELS_SEARCH_CACHE_MAX_ENTRIES:
        _PARCELS_SEARCH_CACHE.popitem(last=False)


def _parcels_search_cache_clear() -> None:
    """Test helper; not exposed via HTTP."""
    _PARCELS_SEARCH_CACHE.clear()


def _parcels_search_cache_key(
    payload: CandidateParcelSearchRequest, captured_at_iso: str | None
) -> str:
    """SHA256 over canonical JSON of (payload, captured_at_iso).

    `model_dump(mode='json')` gives a JSON-serializable dict with stable
    field ordering driven by the Pydantic model; sort_keys forces
    determinism across dict insertion-order variation. The hash is short
    enough to use as a dict key with no collision risk for ~64 entries.
    """
    canonical = _json.dumps(
        {
            "payload": payload.model_dump(mode="json"),
            "captured_at": captured_at_iso,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post("/parcels/search", response_model=CandidateParcelSearchResponse)
async def candidate_parcel_search(
    payload: CandidateParcelSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Run the candidate search; serve from the in-process memo on hit.

    The memo key folds in the latest `coverage_snapshots.captured_at`
    for the jurisdiction so an audit refresh implicitly invalidates
    every cached entry for that jurisdiction. Hits surface
    `X-Cache: HIT`; misses `X-Cache: MISS`. The Cache-Control header
    is set on both for the (mostly cosmetic on POST) edge-cache path.
    """
    captured_at_row = await db.execute(
        text(
            "SELECT MAX(captured_at) AS ts FROM coverage_snapshots "
            "WHERE jurisdiction_id = :jid"
        ),
        {"jid": payload.jurisdiction_id},
    )
    captured_at = captured_at_row.scalar_one_or_none()
    captured_at_key = captured_at.isoformat() if captured_at is not None else None
    cache_key = _parcels_search_cache_key(payload, captured_at_key)

    cached = _parcels_search_cache_get(cache_key)
    if cached is not None:
        return Response(
            content=cached,
            media_type="application/json",
            headers={
                "Cache-Control": _PARCELS_SEARCH_CACHE_CONTROL,
                "X-Cache": "HIT",
            },
        )

    result = await search_candidate_parcels(payload, db)
    # model_dump_json honors the union'd items field — full or slim,
    # whichever the service returned. The bytes are what the cache
    # stores; subsequent hits skip both the SQL and this dump.
    body = result.model_dump_json().encode("utf-8")
    _parcels_search_cache_set(cache_key, body)

    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Cache-Control": _PARCELS_SEARCH_CACHE_CONTROL,
            "X-Cache": "MISS",
        },
    )


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
    # NJ MOD-IV land-use-class fallback. Fires ONLY when the parcel has
    # no zoning_code (so it never overrides actual zoning data). Used to
    # surface candidates in counties whose parcel ingest lost the zoning
    # field — Bergen NJ is the current case (273k of 281k parcels have
    # zoning_code IS NULL but a populated MOD-IV class from the NJOGIS
    # composite backfill). Maps published classes to a conservative
    # storage_permission so the candidate filter has something to work
    # with. Real per-municipality zoning supersedes this once available.
    (
        and_(
            Parcel.zoning_code.is_(None),
            Parcel.land_use_code == "4B",
        ),
        "permitted",
    ),
    (
        and_(
            Parcel.zoning_code.is_(None),
            Parcel.land_use_code.in_(["4A", "1"]),
        ),
        "conditional",
    ),
    (
        and_(
            Parcel.zoning_code.is_(None),
            Parcel.land_use_code.in_(["3A", "3B"]),
        ),
        "unclear",
    ),
    else_="unclassified",
).label("storage_permission")

_zum_join = and_(
    ZoneUseMatrix.jurisdiction_id == Parcel.jurisdiction_id,
    ZoneUseMatrix.zone_code == Parcel.zoning_code,
    # Skip tombstoned rows so they don't classify parcels. The CASE
    # falls through to the MOD-IV fallback / "unclassified" branch
    # the same way it does when no matrix row exists at all.
    ZoneUseMatrix.deleted_at.is_(None),
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

import asyncio  # noqa: E402

from pydantic import BaseModel  # noqa: E402  (kept local to the endpoint)
from app.config import settings  # noqa: E402


# Cap concurrent value-density requests so the SQLAlchemy pool
# (5 + 10 overflow = 15) isn't exhausted by burst-precompute. The
# frontend's precompute pass kicks off ~16 simultaneous ring fetches
# per CONCURRENCY=4 cohort; without this gate 5 of every 20 calls
# returned 500 'QueuePool limit of size 5 overflow 10 reached'.
_value_density_sem = asyncio.Semaphore(8)


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
) -> _ValueDensityResponse:
    """Count residential parcels above $1M / $2M / $5M inside a polygon.

    The polygon is typically a drive-time isochrone ring generated by
    the frontend via Mapbox. When ``parcel_id`` + ``drive_time_minutes``
    are supplied, the result is upserted into ``parcel_ring_metrics``
    keyed by that pair so subsequent identical requests skip the spatial
    query.

    Returns ``{homes_over_1m, homes_over_2m, homes_over_5m, cached}``.

    Concurrency note: the semaphore wraps BOTH the session acquisition
    and the body. The previous version took the session via FastAPI's
    Depends(get_db) which fires before the function body — so the pool
    was already exhausted by the time the semaphore could gate anything.
    """
    from app.db import async_session_maker

    async with _value_density_sem:
        async with async_session_maker() as db:
            return await _value_density_impl(payload, db)


async def _value_density_impl(
    payload: "_ValueDensityRequest", db: AsyncSession
) -> "_ValueDensityResponse":
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


# ─── Drive-time ring demographics cache ──────────────────────────────────
#
# Shared server-side cache of per-parcel drive-time ring metrics, persisted
# to parcel_ring_metrics. The dashboard precompute (Mapbox isochrone +
# Census ACS) is otherwise client-side and per-user, so every reload / new
# user recomputes from scratch. With write-through + bulk read, a city is
# computed once and every later load (any user) reads it back near-instantly.
#
# Demographics are written by the bulk-upsert below; wealth-density
# homes_over_* stay on the value-density path above. See
# app/models/parcel_ring_metric.py — the table was built for this; only the
# demographic write-through was missing.

_RING_METRICS_TTL_DAYS = 90
_VALID_DRIVE_TIMES = (2, 5, 10, 15)

# Cap concurrent bulk-upserts so burst write-through from the precompute
# doesn't exhaust the connection pool. Mirrors _value_density_sem; each POST
# is a single batched statement holding one session briefly.
_ring_demo_sem = asyncio.Semaphore(4)


class _RingDemoItem(BaseModel):
    parcel_id: int
    drive_time_minutes: int
    population: int | None = None
    median_hhi: float | None = None
    median_home_value: float | None = None
    hnw_households: int | None = None


class _RingDemoBulkRequest(BaseModel):
    items: list[_RingDemoItem]


class _RingDemoBulkResponse(BaseModel):
    upserted: int


@router.post("/parcels/ring-metrics/bulk", response_model=_RingDemoBulkResponse)
async def upsert_ring_demographics(
    payload: _RingDemoBulkRequest,
) -> _RingDemoBulkResponse:
    """Bulk-upsert per-parcel drive-time ring DEMOGRAPHICS into
    parcel_ring_metrics (write-through from the dashboard precompute).

    Writes ONLY the demographic columns + computed_at. The wealth-density
    ``homes_over_*`` columns are intentionally never named here, so a
    concurrent value-density upsert for the same (parcel_id, drive_time)
    is preserved; brand-new rows simply leave them NULL (tolerated by the
    value-density fast-path and the buybox scoring LEFT JOIN).
    """
    from app.db import async_session_maker

    rows = [
        {
            "pid": it.parcel_id,
            "dt": it.drive_time_minutes,
            "pop": it.population,
            "hhi": it.median_hhi,
            "hv": it.median_home_value,
            "hnw": it.hnw_households,
        }
        for it in payload.items
        if it.drive_time_minutes in _VALID_DRIVE_TIMES
    ]
    if not rows:
        return _RingDemoBulkResponse(upserted=0)

    async with _ring_demo_sem:
        async with async_session_maker() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO parcel_ring_metrics
                      (parcel_id, drive_time_minutes, population, median_hhi,
                       median_home_value, hnw_households)
                    VALUES (:pid, :dt, :pop, :hhi, :hv, :hnw)
                    ON CONFLICT (parcel_id, drive_time_minutes) DO UPDATE
                      SET population        = EXCLUDED.population,
                          median_hhi        = EXCLUDED.median_hhi,
                          median_home_value = EXCLUDED.median_home_value,
                          hnw_households    = EXCLUDED.hnw_households,
                          computed_at       = NOW()
                    """
                ),
                rows,
            )
            await db.commit()
    return _RingDemoBulkResponse(upserted=len(rows))


class _RingMetricRow(BaseModel):
    parcel_id: int
    drive_time_minutes: int
    population: int | None = None
    median_hhi: float | None = None
    median_home_value: float | None = None
    hnw_households: int | None = None
    homes_over_1m: int | None = None
    homes_over_2m: int | None = None
    homes_over_5m: int | None = None
    computed_at: datetime


class _RingMetricsResponse(BaseModel):
    rows: list[_RingMetricRow]


@router.get(
    "/jurisdictions/{jurisdiction_id}/ring-metrics",
    response_model=_RingMetricsResponse,
)
async def list_ring_metrics(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> _RingMetricsResponse:
    """All non-stale cached ring metrics for a jurisdiction's parcels.

    The dashboard calls this once on load to seed its precompute and skip
    re-fetching parcels that are already cached (TTL: 90 days). Rows are a
    flat (parcel_id, drive_time) list; the frontend groups them into the
    4-ring shape.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RING_METRICS_TTL_DAYS)
    result = await db.execute(
        text(
            """
            SELECT prm.parcel_id, prm.drive_time_minutes,
                   prm.population, prm.median_hhi, prm.median_home_value,
                   prm.hnw_households,
                   prm.homes_over_1m, prm.homes_over_2m, prm.homes_over_5m,
                   prm.computed_at
            FROM parcel_ring_metrics prm
            JOIN parcels p ON p.id = prm.parcel_id
            WHERE p.jurisdiction_id = :jid
              AND prm.computed_at >= :cutoff
            ORDER BY prm.parcel_id, prm.drive_time_minutes
            """
        ),
        {"jid": str(jurisdiction_id), "cutoff": cutoff},
    )

    def _f(v: object) -> float | None:
        return float(v) if v is not None else None  # Numeric -> float | None

    rows = [
        _RingMetricRow(
            parcel_id=m["parcel_id"],
            drive_time_minutes=m["drive_time_minutes"],
            population=m["population"],
            median_hhi=_f(m["median_hhi"]),
            median_home_value=_f(m["median_home_value"]),
            hnw_households=m["hnw_households"],
            homes_over_1m=m["homes_over_1m"],
            homes_over_2m=m["homes_over_2m"],
            homes_over_5m=m["homes_over_5m"],
            computed_at=m["computed_at"],
        )
        for m in (row._mapping for row in result)
    ]
    return _RingMetricsResponse(rows=rows)
