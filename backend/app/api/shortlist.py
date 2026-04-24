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
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.parcel import Parcel
from app.models.shortlist import Shortlist
from app.models.zone_use_matrix import ZoneUseMatrix
from app.schemas.shortlist import ShortlistCreate, ShortlistRead
from app.api.parcels import _storage_perm_expr, _zum_join

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

    from app.models.zone_use_matrix import ZoneUseMatrix as _ZUM
    result = await db.execute(
        select(Parcel, _storage_perm_expr,
               _ZUM.self_storage, _ZUM.luxury_garage_condo,
               _ZUM.classification_source, _ZUM.confidence)
        .outerjoin(_ZUM, _zum_join)
        .where(Parcel.id.in_(sl.parcel_ids))
    )
    rows = result.all()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "apn", "address", "owner_name", "acres",
            "zoning_code", "storage_permission",
            "self_storage", "luxury_garage_condo",
            "classification_source", "confidence",
            "in_flood_zone", "in_wetland", "has_structure",
            "improvement_value", "county_link",
        ],
    )
    writer.writeheader()
    for row in rows:
        p = row[0]
        writer.writerow({
            "apn": p.apn,
            "address": p.address or "",
            "owner_name": p.owner_name or "",
            "acres": p.acres,
            "zoning_code": p.zoning_code or "",
            "storage_permission": row[1] or "unclassified",
            "self_storage": str(row[2].value) if row[2] else "",
            "luxury_garage_condo": str(row[3].value) if row[3] else "",
            "classification_source": str(row[4].value) if row[4] else "",
            "confidence": row[5] or "",
            "in_flood_zone": p.in_flood_zone,
            "in_wetland": p.in_wetland,
            "has_structure": p.has_structure,
            "improvement_value": p.improvement_value,
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
