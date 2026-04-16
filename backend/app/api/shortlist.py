"""
POST /api/shortlists             — save a named shortlist
GET  /api/shortlists/:id         — retrieve shortlist
GET  /api/shortlists/:id/export.csv — CSV export
"""
import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.parcel import Parcel
from app.models.shortlist import Shortlist
from app.schemas.shortlist import ShortlistCreate, ShortlistRead

router = APIRouter(tags=["shortlists"])


@router.post("/shortlists", response_model=ShortlistRead, status_code=201)
async def create_shortlist(
    payload: ShortlistCreate,
    db: AsyncSession = Depends(get_db),
) -> Shortlist:
    sl = Shortlist(**payload.model_dump())
    db.add(sl)
    await db.flush()
    await db.refresh(sl)
    return sl


@router.get("/shortlists/{shortlist_id}", response_model=ShortlistRead)
async def get_shortlist(
    shortlist_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Shortlist:
    sl = await db.get(Shortlist, shortlist_id)
    if sl is None:
        raise HTTPException(status_code=404, detail="Shortlist not found")
    return sl


@router.get("/shortlists/{shortlist_id}/export.csv")
async def export_shortlist_csv(
    shortlist_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    sl = await db.get(Shortlist, shortlist_id)
    if sl is None:
        raise HTTPException(status_code=404, detail="Shortlist not found")

    if not sl.parcel_ids:
        raise HTTPException(status_code=422, detail="Shortlist has no parcels.")

    result = await db.execute(
        select(Parcel).where(Parcel.id.in_(sl.parcel_ids))
    )
    parcels = result.scalars().all()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "apn", "address", "owner_name", "acres",
            "zoning_code", "in_flood_zone", "avg_slope_pct", "in_wetland",
            "improvement_value", "has_structure", "county_link",
        ],
    )
    writer.writeheader()
    for p in parcels:
        writer.writerow({
            "apn": p.apn,
            "address": p.address or "",
            "owner_name": p.owner_name or "",
            "acres": p.acres,
            "zoning_code": p.zoning_code or "",
            "in_flood_zone": p.in_flood_zone,
            "avg_slope_pct": p.avg_slope_pct,
            "in_wetland": p.in_wetland,
            "improvement_value": p.improvement_value,
            "has_structure": p.has_structure,
            "county_link": p.county_link or "",
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="shortlist-{shortlist_id}.csv"'
        },
    )
