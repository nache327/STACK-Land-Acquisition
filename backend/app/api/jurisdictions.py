"""
GET  /api/jurisdictions                         — list known jurisdictions
GET  /api/jurisdictions/:id                     — single jurisdiction
GET  /api/jurisdictions/:id/zones               — zone→use matrix
GET  /api/jurisdictions/:id/zones/:code         — single zone row (for Layer 3 verification)
PATCH /api/jurisdictions/:id/zones/:code        — human override
GET  /api/jurisdictions/:id/parcels/map         — GeoJSON FeatureCollection for MapLibre
POST /api/jurisdictions/_cleanup-empty          — admin: dedupe empty jurisdictions
"""
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field


class _MunicipalDiscoveryBody(BaseModel):
    municipality_names: list[str] | None = None


class _MunicipalIngestBody(BaseModel):
    source_ids: list[uuid.UUID]


class _SourceReviewBody(BaseModel):
    """Body for POST /_sources/{id}/_review — generalizes /verify with
    reject + needs_review + unverify actions."""
    action: Literal["verify", "reject", "needs_review", "unverify"]
    notes: str | None = None
    rejected_reason: str | None = None  # required if action == "reject"


class _BulkReviewBody(BaseModel):
    """Body for POST /_sources/_bulk-review — batch verify/reject for
    operators clearing a queue of obvious matches/junk."""
    action: Literal["verify", "reject", "needs_review"]
    source_ids: list[uuid.UUID] = Field(..., max_length=50)
    rejected_reason: str | None = None
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._auth import require_secret
from app.config import settings
from app.db import get_db
from app.models.job import Job
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.models.zone_use_matrix import ZoneUseMatrix, ClassificationSource
from app.models.zoning_district import ZoningDistrict
from app.schemas.jurisdiction import JurisdictionList, JurisdictionRead
from app.schemas.zone_use_matrix import (
    ZoneMatrixResponse,
    ZoneUseMatrixCreate,
    ZoneUseMatrixRead,
    ZoneUseMatrixUpdate,
)

router = APIRouter(tags=["jurisdictions"])


@router.get("/jurisdictions", response_model=JurisdictionList)
async def list_jurisdictions(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Jurisdiction).order_by(Jurisdiction.name))
    jurisdictions = result.scalars().all()
    return {"items": jurisdictions, "total": len(jurisdictions)}


@router.get("/jurisdictions/{jurisdiction_id}", response_model=JurisdictionRead)
async def get_jurisdiction(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Jurisdiction:
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    return j


@router.get("/jurisdictions/{jurisdiction_id}/feature-flags")
async def get_feature_flags(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-jurisdiction feature availability flags consumed by the dashboard.

    Currently exposes:

    * ``wealth_density_available`` — true when at least one parcel in this
      jurisdiction has ``assessed_value`` populated. When false, the
      "Wealth density" sliders should be disabled in the UI (UT cities
      via UGRC publish no assessor money fields, so the field is null
      everywhere and dragging the slider above 0 would hide every parcel).
    """
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    has_assessed = await db.scalar(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM parcels "
            "  WHERE jurisdiction_id = :jid AND assessed_value IS NOT NULL "
            "  LIMIT 1"
            ")"
        ).bindparams(jid=jurisdiction_id)
    )

    return {
        "jurisdiction_id": str(jurisdiction_id),
        "wealth_density_available": bool(has_assessed),
    }


@router.get("/jurisdictions/{jurisdiction_id}/zones", response_model=ZoneMatrixResponse)
async def get_zone_matrix(
    jurisdiction_id: uuid.UUID,
    municipality: str | None = Query(
        default=None,
        description=(
            "Scope to ONE municipality's own verdict rows (strict "
            "municipality = <city>). REQUIRED for sane review of a "
            "county-as-jurisdiction (county_gis): without it the response mixes "
            "every town's zones AND county-default (NULL-municipality bootstrap) "
            "rows, so a single-town ordinance review hits false "
            "'mismatch'/'missing' positives. This is the REVIEW set (the town's "
            "own ordinance-derived rows) — intentionally NOT the buybox "
            "'municipality = <city> OR NULL' scoring set, since county defaults "
            "aren't that town's ordinance and would re-introduce the very false "
            "positives this filter removes."
        ),
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where = [
        ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
        ZoneUseMatrix.deleted_at.is_(None),
    ]
    if municipality is not None:
        where.append(ZoneUseMatrix.municipality == municipality)
    result = await db.execute(
        select(ZoneUseMatrix).where(*where).order_by(ZoneUseMatrix.zone_code)
    )
    zones = result.scalars().all()
    return {"zones": zones, "unknown_zones": [], "parser_warnings": []}


@router.get("/jurisdictions/{jurisdiction_id}/_parcel-cities")
async def get_parcel_cities(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Distinct, non-null parcels.city values for this jurisdiction, in the
    EXACT casing stored on parcels.

    This is the canonical option-set for the Zoning Verifier's municipality
    selector. Because the buybox scoring join is a case-sensitive
    `municipality = p.city`, a human verdict MUST carry a municipality that
    exactly matches one of these strings — anything else silently scores 0
    parcels (see project_municipality_city_case_sensitive) or, when NULL,
    fans the verdict out county-wide (project_verifier_writes_null_municipality).
    Returning the list straight from parcels guarantees the selector can only
    emit a value the scorer will actually match.

    `single_town` is true when the jurisdiction resolves to exactly one town
    (0 or 1 distinct city) — the caller can auto-select it. When 0 distinct
    non-null cities exist, `parcels.city` is unpopulated for this jurisdiction
    (a single-place ingest); the correct municipality there is NULL, not a
    fabricated name, so `cities` is empty and the caller should NOT force a
    selection.
    """
    result = await db.execute(
        text(
            "SELECT DISTINCT city FROM parcels "
            "WHERE jurisdiction_id = :jid AND city IS NOT NULL "
            "ORDER BY city"
        ),
        {"jid": str(jurisdiction_id)},
    )
    cities = [row[0] for row in result.all()]
    return {
        "cities": cities,
        "single_town": len(cities) <= 1,
        "city_unpopulated": len(cities) == 0,
    }


@router.post(
    "/jurisdictions/{jurisdiction_id}/zones",
    response_model=ZoneUseMatrixRead,
    status_code=201,
)
async def create_zone(
    jurisdiction_id: uuid.UUID,
    payload: ZoneUseMatrixCreate,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    # Conflict check must include municipality — (jur, zone_code, NULL)
    # county-default and (jur, zone_code, "Somerville borough") township
    # row coexist legally; only an exact triple-match is a duplicate.
    # Tombstoned rows DON'T count — operator may POST to revive a slot
    # they previously soft-deleted; the partial unique index makes that
    # safe by allowing coexistence of tombstoned + active rows.
    conflict_where = [
        ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
        ZoneUseMatrix.zone_code == payload.zone_code,
        ZoneUseMatrix.deleted_at.is_(None),
    ]
    if payload.municipality is None:
        conflict_where.append(ZoneUseMatrix.municipality.is_(None))
    else:
        conflict_where.append(ZoneUseMatrix.municipality == payload.municipality)
    existing = await db.execute(select(ZoneUseMatrix).where(*conflict_where))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Zone already exists")
    zone = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        **payload.model_dump(),
    )
    db.add(zone)
    await db.flush()
    await db.refresh(zone)
    return zone


def _zone_select_where(
    jurisdiction_id: uuid.UUID, zone_code: str, municipality: str | None,
) -> list:
    """Build the WHERE clauses for selecting one zone_use_matrix row.

    municipality=None matches the NULL-municipality (county-default)
    row, not "any row." Callers that want a township-specific row must
    pass that township's name explicitly. This mirrors the uniqueness
    semantics: (jur, code, NULL) and (jur, code, "X") are distinct.

    Also filters out tombstoned (soft-deleted) rows — GET/PATCH must
    not see them. matrix_bootstrap.bootstrap_zone_use_matrix() has its
    own existence check that DOES include tombstones.
    """
    clauses = [
        ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
        ZoneUseMatrix.zone_code == zone_code,
        ZoneUseMatrix.deleted_at.is_(None),
    ]
    if municipality is None:
        clauses.append(ZoneUseMatrix.municipality.is_(None))
    else:
        clauses.append(ZoneUseMatrix.municipality == municipality)
    return clauses


@router.get(
    "/jurisdictions/{jurisdiction_id}/zones/{zone_code}",
    response_model=ZoneUseMatrixRead,
)
async def get_zone(
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    municipality: str | None = None,
    fallback_default: bool = False,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    # Default (PATCH-compatible) semantics: exact (jur, code, municipality)
    # triplet, where municipality=None means the NULL county-default row only.
    if not (fallback_default and municipality is not None):
        result = await db.execute(
            select(ZoneUseMatrix).where(
                *_zone_select_where(jurisdiction_id, zone_code, municipality)
            )
        )
        zone = result.scalar_one_or_none()
        if zone is None:
            raise HTTPException(status_code=404, detail="Zone not found")
        return zone

    # Read semantics for verification/scoring: prefer the municipality-scoped
    # row, fall back to the NULL county-default. Mirrors the buybox scorer's
    # LATERAL (buybox_scoring._select_parcels_sql) so the Zoning Verification
    # box reads the SAME row the Site Score did. municipality is passed verbatim
    # (parcels.city) — the join is case-sensitive by design.
    result = await db.execute(
        select(ZoneUseMatrix)
        .where(
            ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
            ZoneUseMatrix.zone_code == zone_code,
            ZoneUseMatrix.deleted_at.is_(None),
            or_(
                ZoneUseMatrix.municipality == municipality,
                ZoneUseMatrix.municipality.is_(None),
            ),
        )
        # NULL-municipality sorts last, so a township-specific row wins.
        .order_by(ZoneUseMatrix.municipality.is_(None).asc())
        .limit(1)
    )
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


async def _apply_zone_update(
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    municipality: str | None,
    payload: ZoneUseMatrixUpdate,
    db: AsyncSession,
) -> ZoneUseMatrix:
    """Shared PATCH logic: locate the (jur, zone_code, municipality) active row
    and apply the human override. Used by both the path-param route and the
    query-param route (the latter handles zone codes containing '/', e.g.
    'B/R', 'SC/HD', which can't ride in a path segment)."""
    result = await db.execute(
        select(ZoneUseMatrix).where(
            *_zone_select_where(jurisdiction_id, zone_code, municipality)
        )
    )
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(zone, field, value)
    zone.human_reviewed = True
    zone.classification_source = ClassificationSource.human
    await db.flush()
    await db.refresh(zone)
    return zone


@router.patch(
    "/jurisdictions/{jurisdiction_id}/zones/{zone_code}",
    response_model=ZoneUseMatrixRead,
)
async def update_zone(
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    payload: ZoneUseMatrixUpdate,
    municipality: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    return await _apply_zone_update(jurisdiction_id, zone_code, municipality, payload, db)


@router.patch(
    "/jurisdictions/{jurisdiction_id}/zone",
    response_model=ZoneUseMatrixRead,
)
async def update_zone_by_query(
    jurisdiction_id: uuid.UUID,
    payload: ZoneUseMatrixUpdate,
    zone_code: str,
    municipality: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    """Query-param variant of PATCH update_zone. zone_code rides as a query
    parameter instead of a path segment, so codes containing '/' (B/R, SC/HD,
    APT/TH) can be updated — the path route 404s on those because the slash is
    parsed as a path separator."""
    return await _apply_zone_update(jurisdiction_id, zone_code, municipality, payload, db)


@router.delete(
    "/jurisdictions/{jurisdiction_id}/zones/{zone_code}",
    status_code=204,
)
async def soft_delete_zone(
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    municipality: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a zone_use_matrix row by setting deleted_at = now().

    Why not hard DELETE: matrix_bootstrap.bootstrap_zone_use_matrix()
    re-inserts NULL-municipality rows for any zone_code missing from
    the matrix. Hard-deleted rows get resurrected within ~30 min.
    Soft-deleted rows stay gone because the bootstrap's existence
    check INCLUDES tombstones.

    Returns 404 if no matching active row exists. The matching uses
    the same triplet semantics as PATCH (municipality=None matches
    the NULL-municipality row only). Already-tombstoned rows return
    404 — they were already deleted.
    """
    from datetime import datetime as _dt, timezone as _tz
    result = await db.execute(
        select(ZoneUseMatrix).where(
            *_zone_select_where(jurisdiction_id, zone_code, municipality)
        )
    )
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    zone.deleted_at = _dt.now(_tz.utc)
    await db.flush()
    return None


@router.post(
    "/jurisdictions/{jurisdiction_id}/_crosswalk-cities",
    dependencies=[Depends(require_secret)],
)
async def crosswalk_cities_into_county(
    jurisdiction_id: uuid.UUID,
    seed_stubs: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Copy sibling per-city zone matrices into this county jurisdiction.

    For a county-as-jurisdiction (parcel_source='county_gis'), this finds
    every sibling jurisdiction in the same (state, county) and copies its
    active NULL-municipality zone_use_matrix rows into the county
    jurisdiction tagged with municipality = <stripped city name>. The
    municipality-aware LATERAL join in buybox_scoring will then resolve
    each parcel to its own city's matrix.

    Idempotent. Human edits on the county are protected by the same
    WHERE guard the pipeline uses (human_reviewed=False AND
    classification_source != 'human').

    Returns a summary including `unmatched_cities` (crosswalked names
    that don't appear in parcels.city) and `parcel_cities_without_zoning`
    (cities present in parcel data with no sibling matrix to copy from)
    so name-normalization gaps surface instead of silently leaving
    parcels on the NULL county-default row.

    With `?seed_stubs=true`, also inserts placeholder rows for every
    (city, zone_code) pair where the city has parcels but no sibling
    matrix — `classification_source='inherited_pending'`, all permissions
    unclear. The stubs become editable in the verifier and are replaced
    by a real matrix when one becomes available on a later crosswalk run.
    """
    from app.services.zone_matrix_crosswalk import crosswalk_county_from_cities

    try:
        return await crosswalk_county_from_cities(jurisdiction_id, db, seed_stubs=seed_stubs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/jurisdictions/{jurisdiction_id}/_precompute-ring-metrics",
    status_code=202,
    dependencies=[Depends(require_secret)],
)
async def precompute_ring_metrics(
    jurisdiction_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cities: str | None = None,
) -> dict:
    """Pre-warm parcel_ring_metrics for every parcel in this jurisdiction.

    Returns 202 + job_id immediately; runs in a BackgroundTask so the
    HTTP request doesn't time out on county-sized jurisdictions
    (SLCo: ~10 min to populate 1.6M cache rows). Poll
    ``GET /jurisdictions/_precompute-ring-metrics-status/{job_id}`` for
    progress, backed by Redis (survives Railway restarts, 24h TTL).

    Mirrors the _score-all pattern in buybox.py. The pipeline's
    post-ingest hook also enqueues this (via the Dramatiq actor in
    job_queue.py) so a fresh county ingest auto-warms the cache
    without an operator click; this endpoint is for manual re-warm or
    initial bootstrap on existing jurisdictions.

    Idempotent: the underlying UPSERT refreshes demographic columns
    only, preserving any concurrent value-density write.
    """
    from datetime import datetime as _dt, timezone as _tz
    from app.config import settings as _settings
    from app.services.job_state_store import set_job_state

    if not _settings.mapbox_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "MAPBOX_TOKEN not configured. Set it in the backend env to "
                "enable server-side ring-metric precompute."
            ),
        )

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    job_id = str(uuid.uuid4())
    state: dict = {
        "job_id": job_id,
        "kind": "ring_metrics_precompute",
        "status": "queued",
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": j.name,
        "started_at": _dt.now(_tz.utc).isoformat(),
        "finished_at": None,
        "tracts_computed": 0,
        "tracts_total": None,
        "parcels_written": 0,
        "mapbox_calls": 0,
        "error": None,
    }
    await set_job_state(job_id, state)

    async def _bg() -> None:
        import logging as _logging
        _log = _logging.getLogger(__name__)
        from app.db import async_session_maker
        from app.services.job_state_store import set_job_state as _save
        from app.services.ring_metrics_precompute import (
            precompute_ring_metrics_for_jurisdiction,
        )

        state["status"] = "running"
        await _save(job_id, state)

        async def _on_progress(event: str, done: int, total: int) -> None:
            state["tracts_computed"] = done
            state["tracts_total"] = total
            await _save(job_id, state)

        # Optional city-scoped precompute (comma-separated) — runs ring for just
        # those cities' parcels/tracts inside a large county jid, avoiding the
        # gated county-scale Mapbox cost. bbox is auto-derived from those parcels.
        _cities = [c.strip() for c in cities.split(",")] if cities else None
        try:
            async with async_session_maker() as bg_db:
                summary = await precompute_ring_metrics_for_jurisdiction(
                    jurisdiction_id, bg_db, on_progress=_on_progress, cities=_cities,
                )
            state["tracts_computed"] = summary["tracts_computed"]
            state["tracts_total"] = summary["tracts_computed"]  # final total
            state["parcels_written"] = summary["parcels_written"]
            state["mapbox_calls"] = summary["mapbox_calls"]
            state["elapsed_seconds"] = summary["elapsed_seconds"]
            state["status"] = "completed"
            _log.info(
                "precompute-ring-metrics job=%s complete: jurisdiction=%s "
                "tracts=%d parcels=%d elapsed=%.1fs",
                job_id, j.name, summary["tracts_computed"],
                summary["parcels_written"], summary["elapsed_seconds"],
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("precompute-ring-metrics job=%s failed: %s", job_id, exc)
            state["status"] = "failed"
            state["error"] = str(exc)
        finally:
            state["finished_at"] = _dt.now(_tz.utc).isoformat()
            await _save(job_id, state)

    background_tasks.add_task(_bg)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jurisdictions/_precompute-ring-metrics-status/{job_id}")
async def precompute_ring_metrics_status(job_id: str) -> dict:
    """Return the current state of an in-flight or completed precompute job.
    404 when the job_id is unknown or its 24h TTL has expired."""
    from app.services.job_state_store import get_job_state
    state = await get_job_state(job_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail="precompute job not found (may have expired)",
        )
    return state


@router.post(
    "/jurisdictions/{jurisdiction_id}/_precompute-ring-metrics-worker",
    status_code=202,
    dependencies=[Depends(require_secret)],
)
async def precompute_ring_metrics_worker(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enqueue ring-metrics precompute via the Dramatiq WORKER path.

    Canonical for county-sized (>5 min) precompute. The sibling
    `_precompute-ring-metrics` endpoint runs the job in a FastAPI
    BackgroundTask on the WEB dyno, which a web restart/deploy kills
    silently — orphaning its Redis job-state at status="running"
    (observed: Bergen 2026-06-11 stalled 65+ min, parcels_written=0;
    a re-run via this contract-free path also risks it). This variant
    enqueues to the Dramatiq worker service, which is built for long
    jobs and survives web-dyno churn. See discipline-catch #12 in the
    ops ledger.

    The worker path writes NO Redis job-state, so there is no
    status endpoint to poll; monitor via the parcel_ring_metrics row
    count for the jurisdiction or the worker-service logs. Idempotent:
    the underlying UPSERT refreshes demographic columns only.
    """
    from app.config import settings as _settings

    if not _settings.mapbox_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "MAPBOX_TOKEN not configured. Set it in the backend env to "
                "enable ring-metric precompute."
            ),
        )
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    from app.services.job_queue import enqueue_ring_metrics_precompute

    enqueue_ring_metrics_precompute(jurisdiction_id)
    return {
        "status": "enqueued",
        "path": "worker",
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": j.name,
    }


@router.post(
    "/jurisdictions/{jurisdiction_id}/_match-listings-worker",
    status_code=202,
    dependencies=[Depends(require_secret)],
)
async def match_listings_worker(
    jurisdiction_id: uuid.UUID,
    source: str = "costar",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enqueue the listing match+alert cascade via the Dramatiq WORKER path.

    Canonical for county-sized CoStar ingests. The upload endpoint
    (`POST /listings/upload`) and `_debug-rematch` run the same cascade in a
    FastAPI BackgroundTask on the WEB dyno — which web restart / dyno contention
    kills silently, leaving listings ingested but unmatched (observed: Montgomery
    MD, 224 listings, 0 geocoded/matched for 8+ min under load even after a
    rematch). This variant enqueues to the Dramatiq worker service, built for long
    jobs and immune to web-dyno churn. See discipline-catch #25 (same family as
    #12 precompute, new job class).

    Fire-and-forget: no Redis job-state, so monitor via the matched_parcel_id /
    geocoded_lat counts on forsale_listings. Idempotent (matches only NULL
    match_method rows)."""
    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    from app.services.job_queue import enqueue_listing_match

    enqueue_listing_match(jurisdiction_id, source)
    return {
        "status": "enqueued",
        "path": "worker",
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": j.name,
        "source": source,
    }


@router.post(
    "/jurisdictions/{jurisdiction_id}/_backfill-has-structure-from-lir",
    status_code=202,
    dependencies=[Depends(require_secret)],
)
async def backfill_has_structure_from_lir(
    jurisdiction_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Populate `parcels.has_structure` from AGRC LIR PROP_CLASS.

    Returns 202 + job_id immediately; runs in a BackgroundTask because
    the full SLCo fetch takes ~17 min with AGRC's 6000-units/minute
    rate limit and exceeds Railway's 15-min HTTP proxy timeout. Poll
    `GET /jurisdictions/_backfill-has-structure-from-lir-status/{job_id}`
    for progress, backed by Redis (24h TTL, survives Railway restarts).

    Mirrors the _precompute-ring-metrics async pattern. Spatial-joins
    LIR PROP_CLASS polygons → parcel centroids via the ST_Subdivide +
    temp-GiST pattern. Idempotent (only fills NULL slots, never
    overwrites an existing has_structure value).

    Currently registered LIR layers: Salt Lake / Davis / Weber / Utah
    counties (see _LIR_URLS in lir_has_structure_backfill.py).
    """
    from datetime import datetime as _dt, timezone as _tz
    from app.services.job_state_store import set_job_state

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    job_id = str(uuid.uuid4())
    state: dict = {
        "job_id": job_id,
        "kind": "lir_has_structure_backfill",
        "status": "queued",
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": j.name,
        "started_at": _dt.now(_tz.utc).isoformat(),
        "finished_at": None,
        "error": None,
    }
    await set_job_state(job_id, state)

    async def _bg() -> None:
        import logging as _logging
        _log = _logging.getLogger(__name__)
        from app.db import async_session_maker
        from app.services.job_state_store import set_job_state as _save
        from app.services.lir_has_structure_backfill import (
            backfill_has_structure_for_jurisdiction,
            LirFetchDiagnostic,
        )

        state["status"] = "running"
        await _save(job_id, state)

        try:
            async with async_session_maker() as bg_db:
                summary = await backfill_has_structure_for_jurisdiction(
                    jurisdiction_id, bg_db,
                )
            # Copy summary fields into the polling state so progress is visible.
            for k in (
                "lir_features_fetched", "lir_features_built",
                "lir_features_vacant", "lir_features_ambiguous",
                "parcels_updated_built", "parcels_updated_vacant",
                "prop_class_breakdown", "elapsed_seconds",
            ):
                if k in summary:
                    state[k] = summary[k]
            state["status"] = "completed"
            _log.info(
                "lir-backfill job=%s complete: jurisdiction=%s "
                "built=%d vacant=%d elapsed=%.1fs",
                job_id, j.name,
                summary.get("parcels_updated_built", 0),
                summary.get("parcels_updated_vacant", 0),
                summary.get("elapsed_seconds", 0),
            )
        except LirFetchDiagnostic as e:
            state["status"] = "failed"
            state["error"] = f"LirFetchDiagnostic: {e}"
            _log.warning("lir-backfill job=%s LIR fetch failed: %s", job_id, e)
        except Exception as exc:  # noqa: BLE001
            _log.exception("lir-backfill job=%s failed: %s", job_id, exc)
            state["status"] = "failed"
            state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            state["finished_at"] = _dt.now(_tz.utc).isoformat()
            await _save(job_id, state)

    background_tasks.add_task(_bg)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jurisdictions/_backfill-has-structure-from-lir-status/{job_id}")
async def backfill_has_structure_status(job_id: str) -> dict:
    """Return the current state of an in-flight or completed LIR backfill.
    404 when the job_id is unknown or its 24h TTL has expired."""
    from app.services.job_state_store import get_job_state
    state = await get_job_state(job_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail="LIR backfill job not found (may have expired)",
        )
    return state


@router.post(
    "/_admin/optimize-parcels",
    dependencies=[Depends(require_secret)],
)
async def admin_optimize_parcels(db: AsyncSession = Depends(get_db)) -> dict:
    """One-shot: add the composite indexes the dashboard's jurisdiction-entry
    GROUP BY queries need, and ANALYZE the table. On county-sized
    jurisdictions (SLCo has 397k parcels) the /cities, /zone-summary, and
    /zone-class-summary endpoints sequential-scan + hash-aggregate without
    these, blowing the 30s request timeout. The composite indexes let the
    planner do index-only aggregates; the partial index makes the
    feature-flags assessed_value check an index-only existence probe.

    Indexes created (mirrors migrations 0037 + 0040):
      - ix_parcels_jurisdiction_city  (jurisdiction_id, city)
      - ix_parcels_jur_zoning_code    (jurisdiction_id, zoning_code)
      - ix_parcels_jur_zone_class     (jurisdiction_id, zone_class)
      - ix_parcels_jur_assessed       (jurisdiction_id) WHERE assessed_value IS NOT NULL

    Idempotent — IF NOT EXISTS on every index, ANALYZE is always safe.
    CREATE INDEX uses CONCURRENTLY so it doesn't lock writes; that requires
    AUTOCOMMIT, so we grab a raw connection from the engine and set
    isolation_level explicitly. ANALYZE then runs inline.
    """
    from app.db import engine
    _indexes = [
        ("ix_parcels_jurisdiction_city", "parcels (jurisdiction_id, city)"),
        ("ix_parcels_jur_zoning_code", "parcels (jurisdiction_id, zoning_code)"),
        ("ix_parcels_jur_zone_class", "parcels (jurisdiction_id, zone_class)"),
        (
            "ix_parcels_jur_assessed",
            "parcels (jurisdiction_id) WHERE assessed_value IS NOT NULL",
        ),
    ]
    out: dict = {"indexes_created": []}
    raw = await engine.connect()
    try:
        await raw.execution_options(isolation_level="AUTOCOMMIT")
        for name, definition in _indexes:
            await raw.execute(text(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {definition}"
            ))
            out["indexes_created"].append(name)
        await raw.execute(text("ANALYZE parcels"))
        out["analyzed"] = True
    finally:
        await raw.close()
    return out


@router.get("/jurisdictions/{jurisdiction_id}/_municipalities-health")
async def get_municipalities_health(
    jurisdiction_id: uuid.UUID,
    municipality: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-municipality coverage/health for a (county) jurisdiction.

    Returns each municipality's trustworthiness band + parcel/zoning/district
    stats, plus a rollup band-count summary. Pass ?municipality=Sandy to
    drill into one city. The service logic already existed
    (municipality_health.jurisdiction_municipalities_health) but had no
    route; this surfaces the per-city coverage the dashboard needs to show
    which cities of a county are operational vs. need work.
    """
    from app.services.municipality_health import jurisdiction_municipalities_health

    result = await jurisdiction_municipalities_health(
        jurisdiction_id, db, municipality=municipality
    )
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/jurisdictions/{jurisdiction_id}/_municipalities-remediation")
async def get_municipalities_remediation(
    jurisdiction_id: uuid.UUID,
    municipality: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-municipality health joined with an actionable remediation plan
    (what each below-bar city needs to reach operational). Delegates to
    municipality_remediation.jurisdiction_municipalities_remediation, which
    was likewise unrouted.
    """
    from app.services.municipality_remediation import (
        jurisdiction_municipalities_remediation,
    )

    result = await jurisdiction_municipalities_remediation(
        jurisdiction_id, db, municipality=municipality
    )
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post(
    "/jurisdictions/{jurisdiction_id}/_backfill-zoning-from-siblings",
    dependencies=[Depends(require_secret)],
)
async def backfill_zoning_from_siblings(
    jurisdiction_id: uuid.UUID,
    strategy: str = "apn",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Copy parcels.zoning_code from sibling per-city jurisdictions onto
    this county's parcels.

    Without this, the county-wide UGRC parcel ingest leaves zoning_code
    NULL (the county-wide pull of Parcels_SaltLake/FeatureServer/0
    doesn't carry the ZONING attribute the per-city pulls populate via
    spatial join to each city's zoning polygons). The LATERAL join in
    buybox_scoring then resolves every parcel to no matrix row — even
    after crosswalk runs, the per-city verdicts never fire.

    Strategies (query param ``?strategy=``):

    - ``apn`` (default): join on parcels.apn. Fast and unambiguous when
      both jurisdictions use the same APN namespace (UGRC ↔ UGRC).
    - ``spatial``: spatial-join the county parcel's centroid to the
      sibling parcel's polygon. Needed when the sibling jurisdiction
      uses a different ArcGIS endpoint with its own APN namespace
      (Draper City via services2.arcgis.com).
    - ``both``: APN match first, then spatial pass over remaining NULLs.

    Idempotent and NULL-only: never overwrites a parcel that already
    has a zoning_code.

    The implementation lives in ``app.services.sibling_backfill`` so the
    ingest pipeline can run the same logic automatically as a county-only
    post-ingest stage.
    """
    from app.services.sibling_backfill import (
        backfill_zoning_from_siblings as _backfill,
        NotACountyError,
    )

    try:
        return await _backfill(jurisdiction_id, db, strategy=strategy)
    except NotACountyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        # Unknown strategy or jurisdiction-not-found.
        detail = str(exc)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail)


class _CityCount(BaseModel):
    city: str
    parcel_count: int


@router.get(
    "/jurisdictions/{jurisdiction_id}/cities",
    response_model=list[_CityCount],
)
async def list_jurisdiction_cities(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[_CityCount]:
    """Distinct cities (parcels.city) within a jurisdiction, with parcel
    counts, for the dashboard city-drill-down dropdown. Most county
    jurisdictions span many cities; single-city jurisdictions return one
    row. NULL-city parcels are omitted."""
    result = await db.execute(
        select(Parcel.city, func.count().label("n"))
        .where(
            Parcel.jurisdiction_id == jurisdiction_id,
            Parcel.city.isnot(None),
        )
        .group_by(Parcel.city)
        .order_by(func.count().desc())
    )
    return [_CityCount(city=row.city, parcel_count=row.n) for row in result.all()]


# ── /parcels/map response cache ──────────────────────────────────────────────
#
# In-process TTL+LRU cache for the parcels/map FeatureCollection. The endpoint
# returns a single ~10-50 MB JSON blob for big counties (Bergen 281k, NYC
# 856k features); on a hot key the recompute cost is the dominant request
# latency. Each entry is keyed by `(jurisdiction_id, latest captured_at)` —
# whenever the audit refresh advances `captured_at`, the key changes and the
# new request gets a clean recompute. This is the "invalidate when audit
# refreshes" pattern the Phase-1 brief calls for, with the TTL as a safety
# net for environments where audits haven't run.
#
# Stored as bytes (already-serialized JSON) so cache hits skip both the
# Postgres round-trip and the Python-side json.dumps; the JSONResponse
# wrapper handles content negotiation. OrderedDict gives O(1) LRU eviction.
#
# Sized for ~75 jurisdictions × a small concurrent multiplier — 32 entries
# at typical 5-20 MB each is ~600 MB worst case; on Railway's 2 GB plan
# that's comfortable. Tune _PARCELS_MAP_CACHE_MAX_ENTRIES down if memory
# pressure shows up in deploy logs.
import json as _json
import time as _time
from collections import OrderedDict

_PARCELS_MAP_CACHE: "OrderedDict[tuple[uuid.UUID, str | None], tuple[float, bytes]]" = (
    OrderedDict()
)
_PARCELS_MAP_CACHE_TTL_SECONDS = 300.0
_PARCELS_MAP_CACHE_MAX_ENTRIES = 32
_PARCELS_MAP_CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=600"


def _parcels_map_cache_get(
    key: "tuple[uuid.UUID, str | None]",
) -> bytes | None:
    """Return cached payload bytes if present and not expired; else None.
    Moves the entry to the MRU end on hit."""
    entry = _PARCELS_MAP_CACHE.get(key)
    if entry is None:
        return None
    inserted_at, payload = entry
    if _time.monotonic() - inserted_at > _PARCELS_MAP_CACHE_TTL_SECONDS:
        _PARCELS_MAP_CACHE.pop(key, None)
        return None
    _PARCELS_MAP_CACHE.move_to_end(key)
    return payload


def _parcels_map_cache_set(
    key: "tuple[uuid.UUID, str | None]", payload: bytes
) -> None:
    _PARCELS_MAP_CACHE[key] = (_time.monotonic(), payload)
    _PARCELS_MAP_CACHE.move_to_end(key)
    while len(_PARCELS_MAP_CACHE) > _PARCELS_MAP_CACHE_MAX_ENTRIES:
        _PARCELS_MAP_CACHE.popitem(last=False)


def _parcels_map_cache_clear() -> None:
    """Test helper; not exposed via HTTP."""
    _PARCELS_MAP_CACHE.clear()


@router.get("/jurisdictions/{jurisdiction_id}/parcels/map")
async def get_parcels_map_layer(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Return all parcels for a jurisdiction as a GeoJSON FeatureCollection
    ready for MapLibre GL JS.

    Uses PostGIS ST_AsGeoJSON for efficient server-side serialization.
    Geometry is simplified to 6 decimal places (~0.1 m precision) to reduce
    payload size. Only parcels with valid geometries are included.

    Performance — Phase 1 (2026-06-08):
      1. `Cache-Control: public, s-maxage=300, stale-while-revalidate=600`
         lets the upstream CDN (or any HTTP cache between client and server)
         serve hot requests without hitting the origin. Parcels-with-zoning
         don't change mid-session; a 5-min freshness window is acceptable
         for the matrix-edit cadence.
      2. Server-side TTL+LRU memo keyed by `(jurisdiction_id, latest
         captured_at)`. The captured_at lookup is a cheap indexed SELECT;
         when the audit refresh advances the snapshot, the cache key
         changes and the next request rebuilds the FeatureCollection.
      3. Slim property set: only the fields the MapLibre paint pipeline
         actually reads (`zoning_code`, `zone_class`, `storage_permission`,
         plus the Feature-level `id` for click routing). The popup/drawer
         fetches heavy detail via `GET /api/parcels/{parcel_id}` on click.
         See PR body for the audit of which fields were dropped + why.
    """
    # captured_at lookup is cheap (~5 ms on an indexed `(jurisdiction_id,
    # captured_at DESC)` access path). If no snapshot exists yet, the key
    # falls back to `(jurisdiction_id, None)` and the TTL alone gates
    # invalidation.
    captured_at_row = await db.execute(
        text(
            "SELECT MAX(captured_at) AS ts FROM coverage_snapshots "
            "WHERE jurisdiction_id = :jid"
        ),
        {"jid": jurisdiction_id},
    )
    captured_at = captured_at_row.scalar_one_or_none()
    captured_at_key = captured_at.isoformat() if captured_at is not None else None
    cache_key = (jurisdiction_id, captured_at_key)

    cached = _parcels_map_cache_get(cache_key)
    if cached is not None:
        # Return pre-serialized bytes via the base Response — bypasses
        # JSONResponse's redundant json.dumps step on cache hit.
        from fastapi import Response as _Response
        return _Response(
            content=cached,
            media_type="application/geo+json",
            headers={
                "Cache-Control": _PARCELS_MAP_CACHE_CONTROL,
                "X-Cache": "HIT",
            },
        )

    sql = text("""
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(
                json_agg(
                    json_build_object(
                        'type',       'Feature',
                        'id',         p.id,
                        'geometry',   ST_AsGeoJSON(p.geom, 6)::json,
                        'properties', json_build_object(
                            'id',                p.id,
                            'zoning_code',       p.zoning_code,
                            'zone_class',        p.zone_class,
                            'storage_permission', CASE
                                -- Any use permitted — show green regardless of source
                                WHEN zum.self_storage = 'permitted'
                                  OR zum.mini_warehouse = 'permitted'
                                  OR zum.luxury_garage_condo = 'permitted'
                                THEN 'permitted'
                                -- Any use conditional — show amber regardless of source
                                WHEN zum.self_storage = 'conditional'
                                  OR zum.mini_warehouse = 'conditional'
                                  OR zum.luxury_garage_condo = 'conditional'
                                THEN 'conditional'
                                -- Both primary storage uses prohibited — show gray even if lgc is unclear
                                WHEN zum.self_storage = 'prohibited'
                                 AND zum.mini_warehouse = 'prohibited'
                                THEN 'prohibited'
                                -- Primary storage use is unclear — show purple
                                WHEN zum.self_storage = 'unclear'
                                  OR zum.mini_warehouse = 'unclear'
                                THEN 'unclear'
                                -- Zone in matrix, all uses explicitly prohibited
                                WHEN zum.zone_code IS NOT NULL THEN 'prohibited'
                                ELSE 'unclassified'
                            END
                        )
                    )
                    ORDER BY p.id
                ) FILTER (WHERE p.geom IS NOT NULL),
                '[]'::json
            )
        ) AS fc
        FROM parcels p
        LEFT JOIN zone_use_matrix zum
            ON  zum.jurisdiction_id = p.jurisdiction_id
            AND zum.zone_code       = p.zoning_code
            AND zum.deleted_at IS NULL
        WHERE p.jurisdiction_id = :jid
    """)

    result = await db.execute(sql, {"jid": jurisdiction_id})
    row = result.one_or_none()

    fc = row.fc if (row is not None and row.fc is not None) else {
        "type": "FeatureCollection",
        "features": [],
    }
    # Serialize once, cache the bytes, return them. Caching the rendered
    # bytes (not the Python dict) means cache hits skip both the DB query
    # and the json.dumps step.
    payload = _json.dumps(fc, separators=(",", ":")).encode("utf-8")
    _parcels_map_cache_set(cache_key, payload)

    return JSONResponse(
        content=fc,
        media_type="application/geo+json",
        headers={
            "Cache-Control": _PARCELS_MAP_CACHE_CONTROL,
            "X-Cache": "MISS",
        },
    )


# ─── Admin: cleanup empty / duplicate jurisdictions ──────────────────────────

# Deletes jurisdictions that have:
#   - parcels = 0
#   - zoning_districts = 0
#   - zone_use_matrix = 0
# AND match one of the cleanup heuristics (state="NE" typo, or name-based dup
# of another jurisdiction in the same county).
#
# Job rows pointing at a deleted jurisdiction are re-pointed to the canonical
# sibling when one exists; otherwise their jurisdiction_id is set to NULL via
# the FK's ondelete=SET NULL.

# Map from "empty city name" (state="NE" typo) to canonical NJ county row name.
# These city-keyed rows were created by the live discovery path that misparsed
# state from the input; the county-keyed rows are doing the actual work.
_NJ_NE_TYPO_TO_COUNTY = {
    "elizabeth":      "Union County, NJ",
    "paterson":       "Passaic County, NJ",
    "new brunswick":  "Middlesex County, NJ",
}

# City rows that should be merged into county-level NJ rows even though their
# state is correct. Marlboro is in Monmouth County which already has 251k
# parcels under the county-level row.
_NJ_CITY_TO_COUNTY = {
    "marlboro": "Monmouth County, NJ",
}


@router.post(
    "/admin/coverage/refresh",
    dependencies=[Depends(require_secret)],
)
async def admin_coverage_refresh(
    jurisdiction_id: uuid.UUID | None = Query(default=None),
    source: str = Query(default="manual"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run the coverage audit and persist snapshots.

    Optional `jurisdiction_id` scopes the refresh to one jurisdiction
    (fast — ~3s). Without it, all ~75 jurisdictions get a fresh snapshot
    (~2-3 min for a full sweep). `source` is a free-text tag stored on
    each row (e.g. 'manual', 'scheduled', 'post-ingest').

    Returns the count of rows written + the audit summary.

    HTTP status:
      200 — at least one snapshot written (full or partial success). A
            partial-success body still includes `snapshots_failed > 0`
            so the operator can see degradation without losing the
            full-sweep continuation behavior.
      502 — every snapshot attempt failed and nothing was written. Until
            2026-06-08 this case returned 200 with `snapshots_written:
            0` in the body — operators reading HTTP status missed it
            (Hunterdon fired 4 refreshes over 24h with `captured_at`
            unchanged because the audit SQL was hitting the asyncpg
            `command_timeout` and the response was silently swallowed
            into the body). Raising 502 surfaces the failure honestly.
    """
    from app.services.coverage_audit import refresh_all_snapshots
    result = await refresh_all_snapshots(db, jurisdiction_id=jurisdiction_id, source=source)
    written = int(result.get("snapshots_written", 0) or 0)
    failed = int(result.get("snapshots_failed", 0) or 0)
    if written == 0 and failed > 0:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "coverage refresh failed; no snapshots written",
                "result": result,
            },
        )
    return result


# Snapshot age past which the captured_at counts as "stale" in the
# failures lens. Slightly higher than the post-mutation freshness
# guarantee (~now) so a few days between operator-side sweeps don't
# spuriously flag every jurisdiction.
_SNAPSHOT_STALE_THRESHOLD_DAYS = 7


def _coverage_failure_reasons(s) -> list[str]:
    """Classify a CoverageSnapshot row into zero-or-more failure reason
    codes. Pure function over the snapshot's stored columns — no DB
    access. Each reason maps 1:1 to a concrete production correctness
    failure the operator should see in `/admin/coverage`.
    """
    from datetime import datetime, timezone, timedelta
    reasons: list[str] = []
    parcel_count = s.parcel_count or 0
    bind_pct = s.parcel_zoning_code_coverage_pct
    district_count = s.zoning_district_count or 0
    parcel_with_zoning = s.parcel_with_zoning_code_count or 0

    if district_count == 0 and parcel_count > 1000:
        reasons.append("no_zoning_districts")
    if district_count > 0 and bind_pct is not None and bind_pct < 0.30:
        reasons.append("spatial_join_incomplete")
    if (s.operational_readiness == "operational"
            and bind_pct is not None and bind_pct < 0.80):
        reasons.append("false_operational")
    if (s.operational_readiness == "partial"
            and "coverage_level_overstates_readiness" in (s.blocking_gaps or [])):
        reasons.append("coverage_level_overstates")
    if (parcel_with_zoning > 0 and district_count == 0
            and bind_pct is not None and bind_pct >= 0.80):
        reasons.append("parcel_source_only_bind")
    if s.captured_at is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=_SNAPSHOT_STALE_THRESHOLD_DAYS,
        )
        if s.captured_at < cutoff:
            reasons.append("snapshot_stale")
    return reasons


@router.get("/admin/coverage")
async def admin_coverage_get(db: AsyncSession = Depends(get_db)) -> dict:
    """Return the latest coverage snapshot per jurisdiction.

    Reads only from `coverage_snapshots` + a single aggregate over
    `zoning_sources` — sub-second response regardless of `parcels` /
    `zoning_overlays` table size. Run `POST /api/admin/coverage/refresh`
    to update snapshots.

    The `failures` array surfaces jurisdictions whose snapshot data
    indicates a correctness problem (no districts, spatial join
    incomplete, false-operational band, parcel-source-only bind,
    overstates readiness, snapshot stale). Sorted by parcel_count desc
    so big-impact failures sit on top.
    """
    from app.services.coverage_audit import latest_snapshots, source_distribution_for_all
    snaps = await latest_snapshots(db)
    source_dist = await source_distribution_for_all(db)

    failures = sorted(
        (
            {
                "jurisdiction_id": str(s.jurisdiction_id),
                "jurisdiction_name": s.jurisdiction_name,
                "reason": reason,
                "parcel_count": s.parcel_count or 0,
                "bind_pct": s.parcel_zoning_code_coverage_pct,
                "district_count": s.zoning_district_count or 0,
                "captured_at": s.captured_at.isoformat() if s.captured_at else None,
            }
            for s in snaps
            for reason in _coverage_failure_reasons(s)
        ),
        key=lambda r: (r["parcel_count"] or 0),
        reverse=True,
    )

    return {
        "count": len(snaps),
        "failures": failures,
        "jurisdictions": [
            {
                "jurisdiction_id": str(s.jurisdiction_id),
                "jurisdiction_name": s.jurisdiction_name,
                "state": s.state,
                "county": s.county,
                "coverage_level": s.coverage_level,
                "captured_at": s.captured_at.isoformat() if s.captured_at else None,
                "parcel_count": s.parcel_count,
                "parcel_with_zoning_code_count": s.parcel_with_zoning_code_count,
                "zoning_district_count": s.zoning_district_count,
                "matrix_zone_count": s.matrix_zone_count,
                "operational_readiness": s.operational_readiness,
                "blocking_gaps": s.blocking_gaps,
                "self_storage_classified_parcel_pct": s.self_storage_classified_parcel_pct,
                "parcel_zoning_code_coverage_pct": s.parcel_zoning_code_coverage_pct,
                "municipality_breakdown": s.municipality_breakdown,
                **(source_dist.get(str(s.jurisdiction_id)) or {
                    "source_count_total": 0,
                    "source_count_verified": 0,
                    "source_count_rejected": 0,
                    "source_count_pending": 0,
                    "source_confidence_distribution": {
                        "0-30": 0, "30-50": 0, "50-70": 0,
                        "70-90": 0, "90-100": 0,
                    },
                }),
            }
            for s in snaps
        ],
    }


@router.get("/admin/coverage/progression")
async def admin_coverage_progression(
    jurisdiction_id: uuid.UUID = Query(..., description="Jurisdiction to graph"),
    days: int = Query(default=30, ge=1, le=365, description="Lookback window"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Coverage time-series for one jurisdiction over the last N days.

    Returns each historical snapshot with parcel + district counts so
    operators can see ingest progression at a glance. Single indexed
    scan on coverage_snapshots — fast even at 30+ days × 75 jurisdictions.
    """
    from app.services.coverage_audit import progression_for_jurisdiction
    series = await progression_for_jurisdiction(db, jurisdiction_id, days=days)
    return {
        "jurisdiction_id": str(jurisdiction_id),
        "days": days,
        "snapshots": series,
    }


@router.post(
    "/jurisdictions/_cleanup-empty",
    dependencies=[Depends(require_secret)],
)
async def cleanup_empty_jurisdictions(
    confirm: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Identify and (optionally) delete empty / duplicate jurisdiction rows.

    Default is dry-run: returns the candidate rows without modifying anything.
    Pass ?confirm=true to actually delete.

    Heuristics:
      1. state='NE' rows (typo of NJ from live discovery) that have a clear
         county-level NJ row to redirect to.
      2. Name-based dups: city-level rows whose canonical county-level row
         exists and has data.
      3. Suffix-mismatch dups (e.g. 'Cedar Hills' vs 'Cedar Hills, UT').
    Only rows with parcels=0 + zoning_districts=0 + matrix=0 are eligible.
    """
    # Pull all jurisdictions plus their counts in one round trip.
    rows = (await db.execute(
        text(
            """
            SELECT
                j.id,
                j.name,
                j.state,
                j.county,
                COALESCE(p.cnt, 0)  AS parcels,
                COALESCE(zd.cnt, 0) AS zones,
                COALESCE(zm.cnt, 0) AS matrix
            FROM jurisdictions j
            LEFT JOIN (
                SELECT jurisdiction_id, COUNT(*) AS cnt
                FROM parcels GROUP BY jurisdiction_id
            ) p  ON p.jurisdiction_id = j.id
            LEFT JOIN (
                SELECT jurisdiction_id, COUNT(*) AS cnt
                FROM zoning_districts GROUP BY jurisdiction_id
            ) zd ON zd.jurisdiction_id = j.id
            LEFT JOIN (
                SELECT jurisdiction_id, COUNT(*) AS cnt
                FROM zone_use_matrix
                WHERE deleted_at IS NULL
                GROUP BY jurisdiction_id
            ) zm ON zm.jurisdiction_id = j.id
            """
        )
    )).mappings().all()

    # Key on (name, state). Build BOTH a dict (first match) and a list
    # grouping. The list lets us catch same-name dups where one row is
    # populated and the other is empty (e.g. two 'Lehi, UT' rows that
    # differ only by county — the pipeline's .first() lookup is
    # non-deterministic, so the empty row is a real footgun).
    by_name_state: dict[tuple[str, str], dict] = {}
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        key = (r["name"].strip().lower(), (r["state"] or "").upper())
        by_name_state.setdefault(key, r)
        groups.setdefault(key, []).append(r)

    candidates: list[dict] = []
    for r in rows:
        if r["parcels"] or r["zones"] or r["matrix"]:
            continue  # has real data, never auto-delete

        name_lc = r["name"].strip().lower()
        state = (r["state"] or "").upper()
        canonical_id = None
        canonical_name = None
        reason = None

        # 1. state='NE' typo
        if state == "NE" and name_lc in _NJ_NE_TYPO_TO_COUNTY:
            canon = _NJ_NE_TYPO_TO_COUNTY[name_lc]
            cr = by_name_state.get((canon.lower(), "NJ"))
            if cr and cr["parcels"]:
                canonical_id, canonical_name = cr["id"], cr["name"]
                reason = "state=NE typo; redirect to NJ county row"

        # 2. NJ city → county redirect
        if reason is None and state == "NJ" and name_lc in _NJ_CITY_TO_COUNTY:
            canon = _NJ_CITY_TO_COUNTY[name_lc]
            cr = by_name_state.get((canon.lower(), "NJ"))
            if cr and cr["parcels"]:
                canonical_id, canonical_name = cr["id"], cr["name"]
                reason = "city dup of populated NJ county row"

        # 3. Suffix-mismatch dup (e.g. 'Cedar Hills' vs 'Cedar Hills, UT')
        if reason is None and state and f", {state.lower()}" not in name_lc:
            cr = by_name_state.get((f"{name_lc}, {state.lower()}", state))
            if cr and cr["parcels"]:
                canonical_id, canonical_name = cr["id"], cr["name"]
                reason = "suffix-mismatch dup of populated row"

        # 4. Same-name-different-county dup. Look at every row sharing the
        # exact (name, state) pair; if at least one sibling has parcels,
        # this empty row is a duplicate footgun for the pipeline's
        # non-deterministic .first() lookup. Pick the populated sibling
        # with the most parcels as canonical.
        if reason is None:
            siblings = groups.get((name_lc, state), [])
            populated = [s for s in siblings if s["id"] != r["id"] and s["parcels"]]
            if populated:
                best = max(populated, key=lambda s: s["parcels"])
                canonical_id, canonical_name = best["id"], best["name"]
                reason = (
                    "same-name-different-county dup of populated row "
                    f"(empty row county={r['county']!r}, "
                    f"populated row county={best['county']!r})"
                )

        if reason is None:
            continue

        candidates.append({
            "id": str(r["id"]),
            "name": r["name"],
            "state": r["state"],
            "county": r["county"],
            "parcels": r["parcels"],
            "redirect_to_id": str(canonical_id) if canonical_id else None,
            "redirect_to_name": canonical_name,
            "reason": reason,
        })

    if not confirm:
        return {"dry_run": True, "candidates": candidates, "count": len(candidates)}

    # Live deletion: re-point jobs, then delete jurisdictions.
    deleted = 0
    for c in candidates:
        if c["redirect_to_id"]:
            await db.execute(
                update(Job)
                .where(Job.jurisdiction_id == uuid.UUID(c["id"]))
                .values(jurisdiction_id=uuid.UUID(c["redirect_to_id"]))
            )
        await db.execute(
            delete(Jurisdiction).where(Jurisdiction.id == uuid.UUID(c["id"]))
        )
        deleted += 1
    await db.commit()
    return {"dry_run": False, "deleted": deleted, "candidates": candidates}


# ─── Admin: discover candidate zoning sources (Phase C) ─────────────────────

@router.post(
    "/jurisdictions/{jurisdiction_id}/_discover-zoning",
    dependencies=[Depends(require_secret)],
)
async def discover_zoning(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Search ArcGIS Hub for candidate zoning sources for this jurisdiction.

    Returns a ranked list of up to 5 candidate FeatureServer/MapServer URLs
    with a confidence score and per-candidate reasoning. **Does not mutate
    the jurisdiction.** The operator reviews the candidates and then fires
    `POST /api/jurisdictions/{id}/_backfill-zoning?zoning_url=<picked>`
    with the URL they trust.

    Heuristics: positive/negative title keywords, polygon geometry,
    plausible feature count, field-name fragments that look zoning-shaped,
    and bbox overlap with the jurisdiction's persisted bbox.
    """
    from app.services.zoning_discovery import discover_zoning_for_jurisdiction
    result = await discover_zoning_for_jurisdiction(jurisdiction_id, db)
    return {
        "jurisdiction_id": result.jurisdiction_id,
        "jurisdiction_name": result.jurisdiction_name,
        "queried_with": result.queried_with,
        "candidates_total": result.candidates_total,
        "candidates": result.candidates,
    }


@router.get("/jurisdictions/{jurisdiction_id}/_sources")
async def list_zoning_sources(
    jurisdiction_id: uuid.UUID,
    status: str | None = Query(default=None,
        description="Filter by validation_status (pending|verified|rejected|needs_review|token_gated|empty)"),
    confidence_min: int | None = Query(default=None, ge=0, le=100,
        description="Only include sources with confidence_score >= this"),
    municipality: str | None = Query(default=None,
        description="Filter to a specific municipality_name (exact match)"),
    sort_by: str = Query(default="confidence",
        description="Sort by 'confidence' (default desc), 'municipality', or 'updated_at'"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List zoning_sources rows for this jurisdiction with filtering + sort.

    Used by the operator review workflow:
      - `?status=pending&confidence_min=70&sort_by=confidence` — shortlist
        of high-confidence candidates that haven't been triaged yet.
      - `?status=verified` — all verified sources ready for ingest.
      - `?status=rejected` — audit which URLs the operator has rejected.

    Each row includes `confidence_breakdown` (structured per-component
    score deltas from scoring v2) and `rejected_reason` for inspection.
    """
    from app.models.zoning_source import ZoningSource

    q = select(ZoningSource).where(ZoningSource.jurisdiction_id == jurisdiction_id)
    if status is not None:
        q = q.where(ZoningSource.validation_status == status)
    if confidence_min is not None:
        q = q.where(ZoningSource.confidence_score >= confidence_min)
    if municipality is not None:
        q = q.where(ZoningSource.municipality_name == municipality)

    if sort_by == "municipality":
        q = q.order_by(ZoningSource.municipality_name.asc().nulls_last(),
                       ZoningSource.confidence_score.desc().nulls_last())
    elif sort_by == "updated_at":
        q = q.order_by(ZoningSource.updated_at.desc())
    else:
        q = q.order_by(ZoningSource.confidence_score.desc().nulls_last())

    # Total count (before pagination) — useful for operator UIs to know
    # how many candidates remain after applying filters.
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()

    return {
        "jurisdiction_id": str(jurisdiction_id),
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "status": status,
            "confidence_min": confidence_min,
            "municipality": municipality,
            "sort_by": sort_by,
        },
        "sources": [
            {
                "id": str(r.id),
                "municipality_name": r.municipality_name,
                "zoning_endpoint": r.zoning_endpoint,
                "title": r.title,
                "source_type": r.source_type,
                "feature_count": r.feature_count,
                "geometry_type": r.geometry_type,
                "confidence_score": r.confidence_score,
                "confidence_label": r.confidence_label,
                "confidence_breakdown": r.confidence_breakdown,
                "validation_status": r.validation_status,
                "discovered_by": r.discovered_by,
                "reasons": r.reasons,
                "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
                "rejected_reason": r.rejected_reason,
                "notes": r.notes,
            }
            for r in rows
        ],
    }


@router.post(
    "/jurisdictions/{jurisdiction_id}/_sources/{source_id}/_review",
    dependencies=[Depends(require_secret)],
)
async def review_zoning_source(
    jurisdiction_id: uuid.UUID,
    source_id: uuid.UUID,
    body: _SourceReviewBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Operator review of a single discovered candidate.

    Actions:
      - 'verify'        → status=verified, label=verified, last_verified_at=now()
      - 'reject'        → status=rejected, rejected_reason=<from body>; URL
                          enters the cross-jurisdiction deny-list and gets
                          a -80 penalty on future scoring.
      - 'needs_review'  → status=needs_review (operator-deferred)
      - 'unverify'      → status=pending, label=discovered (escape hatch if
                          a verify was wrong; rejection can be similarly
                          undone by re-issuing 'unverify' then redoing
                          discovery).
    """
    from datetime import datetime, timezone
    from app.models.zoning_source import ZoningSource

    src = await db.get(ZoningSource, source_id)
    if src is None or src.jurisdiction_id != jurisdiction_id:
        raise HTTPException(404, "zoning_source not found")

    now = datetime.now(timezone.utc)
    if body.action == "verify":
        src.validation_status = "verified"
        src.confidence_label = "verified"
        src.last_verified_at = now
        src.rejected_reason = None
    elif body.action == "reject":
        src.validation_status = "rejected"
        src.confidence_label = "rejected"
        src.last_verified_at = None
        src.rejected_reason = body.rejected_reason or "operator rejected"
    elif body.action == "needs_review":
        src.validation_status = "needs_review"
    elif body.action == "unverify":
        src.validation_status = "pending"
        src.confidence_label = "discovered"
        src.last_verified_at = None
        src.rejected_reason = None

    if body.notes is not None:
        src.notes = body.notes
    src.updated_at = now

    await db.flush()
    await db.commit()
    return {
        "id": str(src.id),
        "action": body.action,
        "validation_status": src.validation_status,
        "confidence_label": src.confidence_label,
        "last_verified_at": src.last_verified_at.isoformat() if src.last_verified_at else None,
        "rejected_reason": src.rejected_reason,
    }


@router.post(
    "/jurisdictions/{jurisdiction_id}/_sources/{source_id}/verify",
    dependencies=[Depends(require_secret)],
)
async def verify_zoning_source(
    jurisdiction_id: uuid.UUID,
    source_id: uuid.UUID,
    validation_status: str = Query(default="verified"),
    notes: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Back-compat alias for the old /verify endpoint.

    Maps the old `?validation_status=X` query-param call to the new
    `_review` body schema. New integrations should use `_review` directly.
    """
    # Map the old taxonomy onto the new action.
    action_map = {
        "verified": "verify",
        "rejected": "reject",
        "pending": "unverify",
    }
    action = action_map.get(validation_status, "verify")
    body = _SourceReviewBody(action=action, notes=notes,
                              rejected_reason=None if action != "reject" else "legacy verify")
    return await review_zoning_source(
        jurisdiction_id=jurisdiction_id, source_id=source_id, body=body, db=db,
    )


@router.get("/jurisdictions/{jurisdiction_id}/_sources/{source_id}/_spatial-check")
async def spatial_check_source(
    jurisdiction_id: uuid.UUID,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Diagnose whether a candidate source's bbox overlaps the jurisdiction.

    Operators use this to explain why a verified-and-ingested source
    produced 0 spatial-join matches (e.g. New Milford CT layer was
    ingested into Bergen NJ — geometries stored correctly in WGS84 but
    100km north in the wrong state, so ST_Within returned 0 hits).

    Returns the layer's raw extent, its SRID, the reprojected WGS84
    extent, the jurisdiction bbox, and a verdict: good / partial / tiny
    / disjoint / unknown. The verdict drives the pre-flight gate in
    _ingest-municipal-zoning.
    """
    from app.models.zoning_source import ZoningSource
    from app.services.zoning_discovery import spatial_check_for_url
    src = await db.get(ZoningSource, source_id)
    if src is None or src.jurisdiction_id != jurisdiction_id:
        raise HTTPException(404, "zoning_source not found")
    if not src.zoning_endpoint:
        raise HTTPException(400, "source has no zoning_endpoint")
    juris = await db.get(Jurisdiction, jurisdiction_id)
    return {
        "source_id": str(source_id),
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": juris.name if juris else None,
        "zoning_endpoint": src.zoning_endpoint,
        **(await spatial_check_for_url(
            src.zoning_endpoint, juris.bbox if juris else None,
        )),
    }


@router.post(
    "/jurisdictions/{jurisdiction_id}/_sources/_bulk-review",
    dependencies=[Depends(require_secret)],
)
async def bulk_review_zoning_sources(
    jurisdiction_id: uuid.UUID,
    body: _BulkReviewBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Batch verify/reject/needs_review across up to 50 source IDs.

    Use for clear-bulk-reject (e.g. drop all generic-Zoning false-positives
    in one shot) or clear-bulk-verify after a scoring re-run surfaces
    several true positives.

    Each row is updated to the requested action with the same semantics
    as the single-row `_review` endpoint. Rows whose jurisdiction_id
    doesn't match the URL are silently skipped (returns updated_count).
    """
    from datetime import datetime, timezone
    from app.models.zoning_source import ZoningSource

    if not body.source_ids:
        return {"updated": 0, "skipped": 0}

    now = datetime.now(timezone.utc)

    # Build the UPDATE values based on action.
    values: dict = {"updated_at": now}
    if body.action == "verify":
        values.update({
            "validation_status": "verified",
            "confidence_label": "verified",
            "last_verified_at": now,
            "rejected_reason": None,
        })
    elif body.action == "reject":
        values.update({
            "validation_status": "rejected",
            "confidence_label": "rejected",
            "last_verified_at": None,
            "rejected_reason": body.rejected_reason or "operator bulk-rejected",
        })
    elif body.action == "needs_review":
        values.update({"validation_status": "needs_review"})

    result = await db.execute(
        update(ZoningSource)
        .where(ZoningSource.id.in_(body.source_ids))
        .where(ZoningSource.jurisdiction_id == jurisdiction_id)
        .values(**values)
    )
    await db.commit()
    updated = result.rowcount or 0
    return {
        "updated": updated,
        "skipped": len(body.source_ids) - updated,
        "action": body.action,
    }


@router.post("/jurisdictions/{county_id}/_discover-municipal-zoning")
async def discover_municipal_zoning(
    county_id: uuid.UUID,
    body: _MunicipalDiscoveryBody | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-town zoning-source discovery for an NJ county.

    Reads the county's municipality list from
    `backend/data/nj_municipalities.json` (or accepts `municipality_names`
    override in the body), runs the existing zoning_discovery for each
    town, and persists top candidates into `zoning_sources` keyed by
    (county_id, town). Operator then reviews via `_sources` GET +
    promotes via `_sources/{id}/verify`.

    Body (optional): `{"municipality_names": ["Paramus", "Mahwah"]}` to
    scope the run. Default sweeps every municipality.

    Per-town concurrency is capped at 4 to avoid Hub rate-limiting on a
    70-town county like Bergen.
    """
    from app.services.nj_municipal_discovery import discover_municipal_zoning_for_county
    munis = body.municipality_names if body else None
    return await discover_municipal_zoning_for_county(
        county_id, db, municipality_names=munis,
    )


@router.post("/jurisdictions/{county_id}/_ingest-municipal-zoning")
async def ingest_municipal_zoning(
    county_id: uuid.UUID,
    body: _MunicipalIngestBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest verified municipal zoning sources into the county's
    zoning_districts table.

    Body: `{"source_ids": ["<uuid>", "<uuid>", ...]}` — must all be rows
    in zoning_sources for this county AND have `confidence_label=verified`.

    Calls the existing _backfill-zoning code path per source with
    `replace=false` so towns aggregate. Uses ON CONFLICT idempotent
    overlay generation from bulk_ingest_zoning so re-runs are safe.
    """
    from app.services.nj_municipal_discovery import ingest_verified_municipal_zoning
    result = await ingest_verified_municipal_zoning(county_id, body.source_ids, db)

    # Post-mutation: refresh bbox + coverage snapshot for the county
    # whose districts just changed. Errors are logged but never break
    # the operator's ingest response.
    try:
        county = await db.get(Jurisdiction, county_id)
        if county is not None:
            from app.services.spatial_backfill import refresh_jurisdiction_bbox
            from app.services.coverage_audit import refresh_all_snapshots
            await refresh_jurisdiction_bbox(county, db)
            await db.commit()
            await refresh_all_snapshots(
                db, jurisdiction_id=county_id, source="post-ingest-municipal",
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "post-ingest-municipal refresh failed for %s: %r", county_id, exc,
        )

    return result


# ─── Admin: backfill zoning districts for an existing jurisdiction ───────────

async def _run_backfill_zoning(
    jurisdiction_id: uuid.UUID,
    zoning_url: str,
    where: str,
    replace: bool,
    spatial_join: bool,
    db: AsyncSession,
    on_stage=None,
) -> dict:
    """Core backfill: download a zoning FeatureServer -> ingest into
    zoning_districts -> spatial-join parcels.zoning_code. Shared by the sync
    `_backfill-zoning` endpoint and the async `_backfill-zoning-async`
    background task (which survives the 300s edge-proxy cap on county-sized
    ingests). `on_stage(name)` is an optional async progress callback.
    """
    from app.services.arcgis_query import download_all_features
    from app.services.zoning_ingestion import ingest_zoning_districts

    async def _stage(name: str) -> None:
        if on_stage is not None:
            await on_stage(name)

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(404, "jurisdiction not found")

    parcel_count = await db.scalar(
        select(func.count(Parcel.id)).where(Parcel.jurisdiction_id == jurisdiction_id)
    )
    pre_zone_count = await db.scalar(
        select(func.count(ZoningDistrict.id)).where(
            ZoningDistrict.jurisdiction_id == jurisdiction_id
        )
    )

    await _stage("downloading")
    gdf = await download_all_features(zoning_url, where=where)
    if gdf.empty:
        return {
            "jurisdiction": j.name,
            "parcel_count": parcel_count,
            "pre_zoning_count": pre_zone_count,
            "downloaded": 0,
            "ingested": 0,
            "spatial_updated": 0,
            "note": "downloaded 0 features — nothing to ingest",
        }

    await _stage("ingesting")
    ingested = await ingest_zoning_districts(gdf, jurisdiction_id, db, replace=replace)
    await db.commit()

    spatial_updated = 0
    if spatial_join and parcel_count and parcel_count > 0:
        await _stage("spatial_join")
        # Mirror the philly prefetch pattern: raw asyncpg + session-mode
        # 5432 + statement_timeout=0 so Supabase doesn't kill the join.
        import asyncpg
        session_url = settings.database_url.replace(":6543/", ":5432/").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        conn = await asyncpg.connect(
            session_url, statement_cache_size=0, command_timeout=7200
        )
        try:
            await conn.execute("SET statement_timeout = 0")
            result = await conn.execute(
                """
                WITH ranked AS (
                    SELECT
                        p.id AS parcel_id,
                        zd.zone_class,
                        zd.zone_code,
                        ROW_NUMBER() OVER (
                            PARTITION BY p.id
                            ORDER BY zd.id
                        ) AS rn
                    FROM parcels p
                    JOIN zoning_districts zd
                      ON zd.jurisdiction_id = p.jurisdiction_id
                     AND p.jurisdiction_id = $1
                     AND p.geom IS NOT NULL
                     AND zd.geom IS NOT NULL
                     AND ST_Within(ST_Centroid(p.geom), zd.geom)
                )
                UPDATE parcels p
                SET zone_class = ranked.zone_class,
                    zoning_code = COALESCE(NULLIF(p.zoning_code, ''), ranked.zone_code)
                FROM ranked
                WHERE p.id = ranked.parcel_id
                  AND ranked.rn = 1
                """,
                jurisdiction_id,
            )
        finally:
            await conn.close()
        # asyncpg's UPDATE returns 'UPDATE <n>'
        try:
            spatial_updated = int(result.split()[-1])
        except Exception:
            spatial_updated = 0

    # Post-mutation: refresh this jurisdiction's bbox + coverage snapshot
    # so /admin/coverage reflects the change immediately. Scoped to the
    # one jurisdiction; `refresh_all_snapshots` filters when kwarg is set.
    # Errors are swallowed (logged) so a downstream refresh failure
    # doesn't blank the operator's ingest response.
    try:
        from app.services.spatial_backfill import refresh_jurisdiction_bbox
        from app.services.coverage_audit import refresh_all_snapshots
        await refresh_jurisdiction_bbox(j, db)
        await db.commit()
        await refresh_all_snapshots(
            db, jurisdiction_id=jurisdiction_id, source="post-backfill",
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "post-backfill refresh failed for %s: %r", jurisdiction_id, exc,
        )

    return {
        "jurisdiction": j.name,
        "parcel_count": parcel_count or 0,
        "pre_zoning_count": pre_zone_count or 0,
        "downloaded": int(len(gdf)),
        "ingested": ingested,
        "spatial_updated": spatial_updated,
    }


@router.post(
    "/jurisdictions/{jurisdiction_id}/_backfill-zoning",
    dependencies=[Depends(require_secret)],
)
async def backfill_zoning(
    jurisdiction_id: uuid.UUID,
    zoning_url: str = Query(..., description="ArcGIS FeatureServer/MapServer layer URL"),
    where: str = Query(default="1=1"),
    replace: bool = Query(default=True),
    spatial_join: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Synchronous backfill (download + ingest + spatial-join). Fine for small
    layers; for county-sized ingests that exceed the ~300s edge-proxy cap use
    `_backfill-zoning-async`. Kept synchronous because `_ingest-municipal-zoning`
    drives it per-source. Idempotent when ``replace=true`` (default)."""
    return await _run_backfill_zoning(
        jurisdiction_id, zoning_url, where, replace, spatial_join, db,
    )


@router.post(
    "/jurisdictions/{jurisdiction_id}/_backfill-zoning-async",
    status_code=202,
    dependencies=[Depends(require_secret)],
)
async def backfill_zoning_async(
    jurisdiction_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    zoning_url: str = Query(..., description="ArcGIS FeatureServer/MapServer layer URL"),
    where: str = Query(default="1=1"),
    replace: bool = Query(default=False),
    spatial_join: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Async backfill: returns 202 + job_id immediately and runs the
    download->ingest->spatial-join in a BackgroundTask so it survives the ~300s
    edge-proxy cap that 502s/fails county-sized synchronous ingests (the NJTPA
    per-county layers). Poll
    ``GET /jurisdictions/_backfill-zoning-status/{job_id}`` — the status carries
    `stage`, the final `result` counts, and on failure `error` + `traceback`
    (so server-side exceptions surface without Railway log access).

    Defaults to ``replace=false`` (aggregate, don't delete existing districts).
    """
    from datetime import datetime as _dt, timezone as _tz
    from app.services.job_state_store import set_job_state

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    job_id = str(uuid.uuid4())
    state: dict = {
        "job_id": job_id,
        "kind": "backfill_zoning",
        "status": "queued",
        "jurisdiction_id": str(jurisdiction_id),
        "jurisdiction_name": j.name,
        "zoning_url": zoning_url,
        "replace": replace,
        "stage": None,
        "started_at": _dt.now(_tz.utc).isoformat(),
        "finished_at": None,
        "result": None,
        "error": None,
        "traceback": None,
    }
    await set_job_state(job_id, state)

    async def _bg() -> None:
        import logging as _logging
        import traceback as _tb
        from app.db import async_session_maker
        from app.services.job_state_store import set_job_state as _save
        _log = _logging.getLogger(__name__)

        state["status"] = "running"
        await _save(job_id, state)

        async def _on_stage(name: str) -> None:
            state["stage"] = name
            await _save(job_id, state)

        try:
            async with async_session_maker() as bg_db:
                result = await _run_backfill_zoning(
                    jurisdiction_id, zoning_url, where, replace, spatial_join,
                    bg_db, on_stage=_on_stage,
                )
            state["result"] = result
            state["status"] = "completed"
            _log.info("backfill-zoning-async job=%s complete: %s", job_id, result)
        except Exception as exc:  # noqa: BLE001
            state["status"] = "failed"
            state["error"] = str(exc)
            state["traceback"] = _tb.format_exc()
            _log.exception("backfill-zoning-async job=%s failed: %s", job_id, exc)
        finally:
            state["finished_at"] = _dt.now(_tz.utc).isoformat()
            await _save(job_id, state)

    background_tasks.add_task(_bg)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jurisdictions/_backfill-zoning-status/{job_id}")
async def backfill_zoning_status(job_id: str) -> dict:
    """State of an in-flight/completed async backfill. 404 if unknown/expired."""
    from app.services.job_state_store import get_job_state
    state = await get_job_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="backfill job not found (may have expired)")
    return state


# ─── Admin: upload zoning shapefile/GeoJSON ──────────────────────────────────

@router.post(
    "/jurisdictions/{jurisdiction_id}/_upload-zoning",
    dependencies=[Depends(require_secret)],
)
async def upload_zoning(
    jurisdiction_id: uuid.UUID,
    file: UploadFile = File(..., description=".geojson or zipped shapefile"),
    replace: bool = Query(default=False, description="default false: append to existing districts"),
    spatial_join: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest a uploaded zoning polygon file (.geojson or zipped .shp) into
    ``zoning_districts``, then optionally spatial-join parcels.

    Use this for municipalities that only publish PDF zoning maps — digitize
    the PDF into a shapefile in QGIS / ArcGIS Pro, zip it up, and POST it.

    Default is replace=false so you can stack multiple towns under one
    county-level jurisdiction (e.g. Marlboro Township + Freehold Township
    both under Monmouth County, NJ). Pass replace=true to wipe the
    jurisdiction's existing zoning_districts first.

    Note: zone_use_matrix has a uniqueness constraint on
    (jurisdiction_id, zone_code) — if two towns under the same county use
    the same zone_code with different rules, only one matrix row can win.
    The spatial join itself is unaffected; only the rules table.
    """
    import io
    import tempfile
    from pathlib import Path

    import geopandas as gpd

    from app.services.zoning_ingestion import ingest_zoning_districts

    j = await db.get(Jurisdiction, jurisdiction_id)
    if j is None:
        raise HTTPException(404, "jurisdiction not found")

    content = await file.read()
    if not content:
        raise HTTPException(422, "empty upload")

    fname = (file.filename or "").lower()
    try:
        if fname.endswith(".geojson") or fname.endswith(".json"):
            gdf = gpd.read_file(io.BytesIO(content))
        elif fname.endswith(".zip"):
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                gdf = gpd.read_file(f"zip://{tmp_path}")
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        else:
            raise HTTPException(422, f"unsupported file type: {file.filename!r} (need .geojson, .json, or .zip)")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"could not parse upload: {exc}")

    if gdf.empty:
        raise HTTPException(422, "uploaded file contained 0 features")

    # Ensure WGS84 — ingest_zoning_districts persists geom as 4326.
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    parcel_count = await db.scalar(
        select(func.count(Parcel.id)).where(Parcel.jurisdiction_id == jurisdiction_id)
    )
    pre_zone_count = await db.scalar(
        select(func.count(ZoningDistrict.id)).where(
            ZoningDistrict.jurisdiction_id == jurisdiction_id
        )
    )

    ingested = await ingest_zoning_districts(gdf, jurisdiction_id, db, replace=replace)
    await db.commit()

    spatial_updated = 0
    if spatial_join and parcel_count and parcel_count > 0:
        import asyncpg
        from app.config import settings
        session_url = settings.database_url.replace(":6543/", ":5432/").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        conn = await asyncpg.connect(
            session_url, statement_cache_size=0, command_timeout=7200
        )
        try:
            await conn.execute("SET statement_timeout = 0")
            result = await conn.execute(
                """
                WITH ranked AS (
                    SELECT
                        p.id AS parcel_id,
                        zd.zone_class,
                        zd.zone_code,
                        ROW_NUMBER() OVER (
                            PARTITION BY p.id
                            ORDER BY zd.id
                        ) AS rn
                    FROM parcels p
                    JOIN zoning_districts zd
                      ON zd.jurisdiction_id = p.jurisdiction_id
                     AND p.jurisdiction_id = $1
                     AND p.geom IS NOT NULL
                     AND zd.geom IS NOT NULL
                     AND ST_Within(ST_Centroid(p.geom), zd.geom)
                )
                UPDATE parcels p
                SET zone_class = ranked.zone_class,
                    zoning_code = COALESCE(NULLIF(p.zoning_code, ''), ranked.zone_code)
                FROM ranked
                WHERE p.id = ranked.parcel_id
                  AND ranked.rn = 1
                """,
                jurisdiction_id,
            )
        finally:
            await conn.close()
        try:
            spatial_updated = int(result.split()[-1])
        except Exception:
            spatial_updated = 0

    return {
        "jurisdiction": j.name,
        "filename": file.filename,
        "parcel_count": parcel_count or 0,
        "pre_zoning_count": pre_zone_count or 0,
        "downloaded": int(len(gdf)),
        "ingested": ingested,
        "spatial_updated": spatial_updated,
        "replace": replace,
    }
