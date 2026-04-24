"""
GET  /api/jurisdictions                         — list known jurisdictions
GET  /api/jurisdictions/:id                     — single jurisdiction
GET  /api/jurisdictions/:id/zones               — zone→use matrix
GET  /api/jurisdictions/:id/zones/:code         — single zone row (for Layer 3 verification)
PATCH /api/jurisdictions/:id/zones/:code        — human override
GET  /api/jurisdictions/:id/parcels/map         — GeoJSON FeatureCollection for MapLibre
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.jurisdiction import Jurisdiction
from app.models.zone_use_matrix import ZoneUseMatrix, ClassificationSource
from app.schemas.jurisdiction import JurisdictionList, JurisdictionRead
from app.schemas.zone_use_matrix import (
    ZoneMatrixResponse,
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
                                -- Verified permitted (LLM or human source)
                                WHEN zum.classification_source IN ('llm','human')
                                 AND (zum.self_storage = 'permitted'
                                   OR zum.mini_warehouse = 'permitted'
                                   OR zum.luxury_garage_condo = 'permitted')
                                THEN 'permitted'
                                -- Verified conditional (LLM or human source)
                                WHEN zum.classification_source IN ('llm','human')
                                 AND (zum.self_storage = 'conditional'
                                   OR zum.mini_warehouse = 'conditional'
                                   OR zum.luxury_garage_condo = 'conditional')
                                THEN 'conditional'
                                -- Verified but has unclear use values — don't collapse to prohibited
                                WHEN zum.classification_source IN ('llm','human')
                                 AND (zum.self_storage = 'unclear'
                                   OR zum.mini_warehouse = 'unclear'
                                   OR zum.luxury_garage_condo = 'unclear')
                                THEN 'unclear'
                                -- Verified prohibited (LLM/human, all uses explicitly prohibited)
                                WHEN zum.classification_source IN ('llm','human')
                                 AND zum.zone_code IS NOT NULL
                                THEN 'prohibited'
                                -- Zone in matrix but unverified (rule-based or unknown source)
                                WHEN zum.zone_code IS NOT NULL THEN 'unclear'
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
