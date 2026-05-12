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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

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
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(ZoneUseMatrix)
        .where(ZoneUseMatrix.jurisdiction_id == jurisdiction_id)
        .order_by(ZoneUseMatrix.zone_code)
    )
    zones = result.scalars().all()
    return {"zones": zones, "unknown_zones": [], "parser_warnings": []}


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
    existing = await db.execute(
        select(ZoneUseMatrix).where(
            ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
            ZoneUseMatrix.zone_code == payload.zone_code,
        )
    )
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


@router.get(
    "/jurisdictions/{jurisdiction_id}/zones/{zone_code}",
    response_model=ZoneUseMatrixRead,
)
async def get_zone(
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    result = await db.execute(
        select(ZoneUseMatrix).where(
            ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
            ZoneUseMatrix.zone_code == zone_code,
        )
    )
    zone = result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.patch(
    "/jurisdictions/{jurisdiction_id}/zones/{zone_code}",
    response_model=ZoneUseMatrixRead,
)
async def update_zone(
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    payload: ZoneUseMatrixUpdate,
    db: AsyncSession = Depends(get_db),
) -> ZoneUseMatrix:
    result = await db.execute(
        select(ZoneUseMatrix).where(
            ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
            ZoneUseMatrix.zone_code == zone_code,
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
    payload size.  Only parcels with valid geometries are included.
    """
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
                            'apn',               p.apn,
                            'zoning_code',       p.zoning_code,
                            'zone_class',        p.zone_class,
                            'acres',             p.acres,
                            'has_structure',     p.has_structure,
                            'in_flood_zone',     p.in_flood_zone,
                            'in_wetland',        p.in_wetland,
                            'address',           p.address,
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
        WHERE p.jurisdiction_id = :jid
    """)

    result = await db.execute(sql, {"jid": jurisdiction_id})
    row = result.one_or_none()

    headers = {"Cache-Control": "no-store"}

    if row is None or row.fc is None:
        return JSONResponse(
            content={"type": "FeatureCollection", "features": []},
            media_type="application/geo+json",
            headers=headers,
        )

    return JSONResponse(content=row.fc, media_type="application/geo+json", headers=headers)


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


@router.post("/admin/coverage/refresh")
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
    """
    from app.services.coverage_audit import refresh_all_snapshots
    result = await refresh_all_snapshots(db, jurisdiction_id=jurisdiction_id, source=source)
    return result


@router.get("/admin/coverage")
async def admin_coverage_get(db: AsyncSession = Depends(get_db)) -> dict:
    """Return the latest coverage snapshot per jurisdiction.

    Reads only from `coverage_snapshots` — sub-second response regardless
    of `parcels` / `zoning_overlays` table size. Run
    `POST /api/admin/coverage/refresh` to update.
    """
    from app.services.coverage_audit import latest_snapshots
    snaps = await latest_snapshots(db)
    return {
        "count": len(snaps),
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
            }
            for s in snaps
        ],
    }


@router.post("/jurisdictions/_cleanup-empty")
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
                FROM zone_use_matrix GROUP BY jurisdiction_id
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

@router.post("/jurisdictions/{jurisdiction_id}/_discover-zoning")
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all zoning_sources rows for this jurisdiction.

    Returns rows sorted by confidence_score DESC. Used by the operator to
    review past discovery candidates without re-running the crawler.
    """
    from app.models.zoning_source import ZoningSource
    result = await db.execute(
        select(ZoningSource)
        .where(ZoningSource.jurisdiction_id == jurisdiction_id)
        .order_by(ZoningSource.confidence_score.desc().nulls_last())
    )
    rows = result.scalars().all()
    return {
        "jurisdiction_id": str(jurisdiction_id),
        "count": len(rows),
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
                "validation_status": r.validation_status,
                "discovered_by": r.discovered_by,
                "reasons": r.reasons,
                "last_verified_at": r.last_verified_at.isoformat() if r.last_verified_at else None,
                "notes": r.notes,
            }
            for r in rows
        ],
    }


@router.post("/jurisdictions/{jurisdiction_id}/_sources/{source_id}/verify")
async def verify_zoning_source(
    jurisdiction_id: uuid.UUID,
    source_id: uuid.UUID,
    validation_status: str = Query(default="verified"),
    notes: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Promote a discovered candidate to verified (or mark it rejected/empty/token_gated).

    `validation_status` accepted values: 'verified' | 'rejected' | 'token_gated' |
    'empty' | 'pending'. The 'verified' label freezes the row from
    further automated overwrites by subsequent discovery runs.
    """
    from datetime import datetime, timezone
    from app.models.zoning_source import ZoningSource

    src = await db.get(ZoningSource, source_id)
    if src is None or src.jurisdiction_id != jurisdiction_id:
        raise HTTPException(404, "zoning_source not found")
    valid = {"verified", "rejected", "token_gated", "empty", "pending"}
    if validation_status not in valid:
        raise HTTPException(400, f"validation_status must be one of {sorted(valid)}")
    src.validation_status = validation_status
    if validation_status == "verified":
        src.confidence_label = "verified"
        src.last_verified_at = datetime.now(timezone.utc)
    if notes is not None:
        src.notes = notes
    src.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()
    return {
        "id": str(src.id),
        "validation_status": src.validation_status,
        "confidence_label": src.confidence_label,
        "last_verified_at": src.last_verified_at.isoformat() if src.last_verified_at else None,
    }


@router.post("/jurisdictions/{county_id}/_discover-municipal-zoning")
async def discover_municipal_zoning(
    county_id: uuid.UUID,
    municipality_names: list[str] | None = None,
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
    return await discover_municipal_zoning_for_county(
        county_id, db, municipality_names=municipality_names,
    )


@router.post("/jurisdictions/{county_id}/_ingest-municipal-zoning")
async def ingest_municipal_zoning(
    county_id: uuid.UUID,
    source_ids: list[uuid.UUID],
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
    return await ingest_verified_municipal_zoning(county_id, source_ids, db)


# ─── Admin: backfill zoning districts for an existing jurisdiction ───────────

@router.post("/jurisdictions/{jurisdiction_id}/_backfill-zoning")
async def backfill_zoning(
    jurisdiction_id: uuid.UUID,
    zoning_url: str = Query(..., description="ArcGIS FeatureServer/MapServer layer URL"),
    where: str = Query(default="1=1"),
    replace: bool = Query(default=True),
    spatial_join: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Download a zoning FeatureServer + ingest into zoning_districts +
    spatial-join parcels.

    Useful for backfilling counties whose initial pipeline ingest didn't
    have a zoning endpoint configured. Idempotent when ``replace=true``
    (default): existing zoning_districts rows for the jurisdiction are
    deleted and re-inserted from the source.

    Returns counts so the caller can verify the backfill landed.
    """
    from app.services.arcgis_query import download_all_features
    from app.services.zoning_ingestion import ingest_zoning_districts

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

    ingested = await ingest_zoning_districts(gdf, jurisdiction_id, db, replace=replace)
    await db.commit()

    spatial_updated = 0
    if spatial_join and parcel_count and parcel_count > 0:
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

    return {
        "jurisdiction": j.name,
        "parcel_count": parcel_count or 0,
        "pre_zoning_count": pre_zone_count or 0,
        "downloaded": int(len(gdf)),
        "ingested": ingested,
        "spatial_updated": spatial_updated,
    }


# ─── Admin: upload zoning shapefile/GeoJSON ──────────────────────────────────

@router.post("/jurisdictions/{jurisdiction_id}/_upload-zoning")
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
