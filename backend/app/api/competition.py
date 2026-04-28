"""
Competition & Saturation API endpoints.

GET  /api/jurisdictions/{jurisdiction_id}/competitors          → GeoJSON map layer
POST /api/jurisdictions/{jurisdiction_id}/competitors/sync     → trigger Google Places sync
POST /api/competitors/import-kmz                               → upload KMZ file
GET  /api/parcels/{parcel_id}/saturation                       → single parcel saturation
POST /api/parcels/saturation-batch                             → batch saturation
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.saturation import (
    RingResult,
    SaturationResult,
    compute_batch_saturation,
    compute_ring_saturation,
)

router = APIRouter(tags=["competition"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RingResultSchema(BaseModel):
    radius_miles: float
    population: float
    facility_count: int
    total_sqft: int
    sqft_per_person: float | None


class SaturationResponse(BaseModel):
    parcel_id: int
    rings: list[RingResultSchema]
    primary_sqft_per_person: float | None
    color: str


class SaturationBatchRequest(BaseModel):
    parcel_ids: list[int]
    ring_miles: float = 3.0


class SaturationBatchResponse(BaseModel):
    results: dict[str, dict]  # str(parcel_id) → {sqft_per_person, color}


def _ring_to_schema(r: RingResult) -> RingResultSchema:
    return RingResultSchema(
        radius_miles=r.radius_miles,
        population=r.population,
        facility_count=r.facility_count,
        total_sqft=r.total_sqft,
        sqft_per_person=r.sqft_per_person,
    )


def _saturation_to_response(s: SaturationResult) -> SaturationResponse:
    return SaturationResponse(
        parcel_id=s.parcel_id,
        rings=[_ring_to_schema(r) for r in s.rings],
        primary_sqft_per_person=s.primary_sqft_per_person,
        color=s.color,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/jurisdictions/{jurisdiction_id}/competitors")
async def get_competitors(
    jurisdiction_id: uuid.UUID,
    bbox: str | None = Query(None, description="xmin,ymin,xmax,ymax viewport filter"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return GeoJSON FeatureCollection of competitor facilities for the map layer.
    Optionally filter by viewport bbox. Returns all data if no API key is configured
    (falls back to KMZ-only data).
    """
    bbox_filter = ""
    params: dict = {"jurisdiction_id": jurisdiction_id}

    if bbox:
        try:
            xmin, ymin, xmax, ymax = [float(x) for x in bbox.split(",")]
            bbox_filter = """
                AND ST_Intersects(
                    geom,
                    ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
                )
            """
            params.update({"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax})
        except ValueError:
            pass

    # Always include NULL-jurisdiction records (KMZ imports have no jurisdiction)
    if bbox:
        where = f"""
            WHERE (jurisdiction_id = :jurisdiction_id OR jurisdiction_id IS NULL)
            {bbox_filter}
        """
    else:
        where = "WHERE (jurisdiction_id = :jurisdiction_id OR jurisdiction_id IS NULL)"

    result = await db.execute(
        text(f"""
            SELECT
                id,
                name,
                operator,
                address,
                COALESCE(sq_ft, 60000) AS sq_ft,
                sqft_source,
                data_source,
                ST_AsGeoJSON(geom)::json AS geometry
            FROM competitor_facilities
            {where}
            {"LIMIT 10000" if bbox else ""}
        """),
        params,
    )
    rows = result.fetchall()

    features = []
    for row in rows:
        features.append({
            "type": "Feature",
            "geometry": row[7],
            "properties": {
                "id": row[0],
                "name": row[1] or "",
                "operator": row[2] or "",
                "address": row[3] or "",
                "sq_ft": row[4],
                "sqft_source": row[5],
                "data_source": row[6],
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.post("/jurisdictions/{jurisdiction_id}/competitors/sync")
async def sync_competitors(
    jurisdiction_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger an async Google Places sync for the jurisdiction bounding box.
    Returns immediately; sync runs in the background.
    """
    from app.config import settings

    if not settings.google_places_enabled:
        return {
            "status": "skipped",
            "message": "GOOGLE_PLACES_API_KEY not configured. Set it in your environment to enable Google Places sync.",
        }

    # Get jurisdiction bbox
    result = await db.execute(
        text("SELECT bbox FROM jurisdictions WHERE id = :id"),
        {"id": jurisdiction_id},
    )
    row = result.fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Jurisdiction not found or has no bbox")

    bbox_data = row[0]
    if isinstance(bbox_data, str):
        bbox_data = json.loads(bbox_data)
    bbox = tuple(bbox_data)  # [xmin, ymin, xmax, ymax]

    async def _do_sync():
        from app.db import async_session_maker
        from app.services.competitor_google import upsert_google_competitors
        async with async_session_maker() as sess:
            try:
                count = await upsert_google_competitors(bbox, jurisdiction_id, sess)
                await sess.commit()
            except Exception as exc:
                await sess.rollback()
                import logging
                logging.getLogger(__name__).error("Competitor sync failed: %s", exc)

    background_tasks.add_task(_do_sync)
    return {"status": "queued", "message": "Google Places sync started in background"}


@router.post("/competitors/import-kmz")
async def import_kmz(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and import a KMZ file. Placemarks are inserted into competitor_facilities
    with data_source='kmz'. Existing KMZ records are NOT deleted first — they are
    upserted. To replace all KMZ data, delete first via /competitors/kmz/clear.
    """
    if not file.filename or not file.filename.lower().endswith(".kmz"):
        raise HTTPException(status_code=400, detail="File must be a .kmz file")

    from app.services.competitor_kmz import ingest_kmz_file

    content = await file.read()
    import io
    inserted, skipped = await ingest_kmz_file(io.BytesIO(content), None, db)
    await db.commit()

    return {
        "inserted": inserted,
        "skipped": skipped,
        "message": f"{inserted} facilities added, {skipped} placemarks skipped (no coordinates)",
    }


@router.delete("/competitors/{competitor_id}")
async def delete_competitor(
    competitor_id: int,
    db: AsyncSession = Depends(get_db),
):
    from app.models.competitor_facility import CompetitorFacility
    from sqlalchemy import delete as sql_delete
    result = await db.execute(
        sql_delete(CompetitorFacility).where(CompetitorFacility.id == competitor_id)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return {"deleted": competitor_id}


@router.post("/competitors")
async def create_competitor(
    payload: dict,  # {lng, lat, name?, sq_ft?, jurisdiction_id?}
    db: AsyncSession = Depends(get_db),
):
    from app.models.competitor_facility import CompetitorFacility
    from geoalchemy2 import WKTElement
    lng = payload["lng"]
    lat = payload["lat"]
    facility = CompetitorFacility(
        name=payload.get("name"),
        sq_ft=payload.get("sq_ft"),
        sqft_source="manual",
        data_source="manual",
        attributes={"pin_type": "manual"},
        geom=WKTElement(f"POINT({lng} {lat})", srid=4326),
        jurisdiction_id=payload.get("jurisdiction_id"),
    )
    db.add(facility)
    await db.commit()
    await db.refresh(facility)
    return {"id": facility.id}


@router.delete("/competitors/kmz/clear")
async def clear_kmz_competitors(db: AsyncSession = Depends(get_db)):
    """Remove all KMZ-sourced competitors so you can re-import a fresh file."""
    from app.services.competitor_kmz import delete_kmz_competitors
    count = await delete_kmz_competitors(db)
    await db.commit()
    return {"deleted": count}


@router.get("/parcels/{parcel_id}/saturation", response_model=SaturationResponse)
async def get_parcel_saturation(
    parcel_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Compute saturation analysis for a single parcel (all 4 rings).
    Ensures census tract data is loaded for the area before computing.
    """
    # Ensure census tracts are loaded for the parcel's area
    bbox_result = await db.execute(
        text("""
            SELECT
                ST_XMin(ST_Extent(centroid)) - 0.15,
                ST_YMin(ST_Extent(centroid)) - 0.15,
                ST_XMax(ST_Extent(centroid)) + 0.15,
                ST_YMax(ST_Extent(centroid)) + 0.15
            FROM parcels WHERE id = :id
        """),
        {"id": parcel_id},
    )
    bbox_row = bbox_result.fetchone()
    if bbox_row and bbox_row[0] is not None:
        from app.services.census import ensure_census_tracts
        try:
            await ensure_census_tracts(
                (bbox_row[0], bbox_row[1], bbox_row[2], bbox_row[3]), db
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Census prefetch failed (non-fatal): %s", exc)

    saturation = await compute_ring_saturation(parcel_id, db)
    if saturation is None:
        raise HTTPException(status_code=404, detail="Parcel not found or has no centroid")

    return _saturation_to_response(saturation)


@router.post("/parcels/saturation-batch", response_model=SaturationBatchResponse)
async def get_saturation_batch(
    request: SaturationBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Compute saturation at a single ring radius for multiple parcels.
    Returns a dict keyed by parcel_id string (JSON keys must be strings).
    Limited to 1,000 parcels per request.
    """
    if len(request.parcel_ids) > 1000:
        raise HTTPException(
            status_code=400,
            detail="Maximum 1,000 parcel IDs per batch request",
        )

    results = await compute_batch_saturation(
        request.parcel_ids, request.ring_miles, db
    )
    # Convert int keys to str for JSON compatibility
    return SaturationBatchResponse(results={str(k): v for k, v in results.items()})
