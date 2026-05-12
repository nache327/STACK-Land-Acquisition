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

    by_name_state = {(r["name"].strip().lower(), (r["state"] or "").upper()): r for r in rows}

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
