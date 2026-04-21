"""
GET /api/jurisdictions/{id}/zoning-districts          — paginated list
GET /api/jurisdictions/{id}/zoning-districts/map      — GeoJSON for MapLibre
PATCH /api/zoning-districts/{id}                      — human override
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.zoning_district import ZoningDistrict
from app.schemas.zoning_district import (
    ZoningDistrictList,
    ZoningDistrictRead,
    ZoningDistrictUpdate,
)

router = APIRouter(tags=["zoning-districts"])


@router.get(
    "/jurisdictions/{jurisdiction_id}/zoning-districts",
    response_model=ZoningDistrictList,
)
async def list_zoning_districts(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(ZoningDistrict)
        .where(ZoningDistrict.jurisdiction_id == jurisdiction_id)
        .order_by(ZoningDistrict.zone_code)
    )
    districts = result.scalars().all()
    return {"items": districts, "total": len(districts)}


@router.get("/jurisdictions/{jurisdiction_id}/zoning-districts/map")
async def get_zoning_districts_map(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    GeoJSON FeatureCollection of zoning-district polygons for MapLibre.

    Geometry simplified to ~0.1 m precision (6 decimal places). For
    jurisdictions with many small polygons (e.g., NYC ~40k), callers should
    prefer the pg_tileserv vector-tile endpoint (/public.zoning_districts/…)
    over this blob endpoint.
    """
    sql = text("""
        SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(
                json_agg(
                    json_build_object(
                        'type',       'Feature',
                        'id',         zd.id,
                        'geometry',   ST_AsGeoJSON(zd.geom, 6)::json,
                        'properties', json_build_object(
                            'id',                zd.id,
                            'zone_code',         zd.zone_code,
                            'zone_name',         zd.zone_name,
                            'zone_class',        zd.zone_class,
                            'max_far',           zd.max_far,
                            'max_height_ft',     zd.max_height_ft,
                            'max_density_dua',   zd.max_density_dua,
                            'allowed_uses',      zd.allowed_uses
                        )
                    )
                    ORDER BY zd.id
                ) FILTER (WHERE zd.geom IS NOT NULL),
                '[]'::json
            )
        ) AS fc
        FROM zoning_districts zd
        WHERE zd.jurisdiction_id = :jid
    """)

    result = await db.execute(sql, {"jid": jurisdiction_id})
    row = result.one_or_none()

    if row is None or row.fc is None:
        return JSONResponse(
            content={"type": "FeatureCollection", "features": []},
            media_type="application/geo+json",
        )

    return JSONResponse(content=row.fc, media_type="application/geo+json")


@router.patch(
    "/zoning-districts/{district_id}",
    response_model=ZoningDistrictRead,
)
async def update_zoning_district(
    district_id: int,
    payload: ZoningDistrictUpdate,
    db: AsyncSession = Depends(get_db),
) -> ZoningDistrict:
    zd = await db.get(ZoningDistrict, district_id)
    if zd is None:
        raise HTTPException(status_code=404, detail="Zoning district not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(zd, field, value)
    zd.human_reviewed = True
    await db.flush()
    await db.refresh(zd)
    return zd
