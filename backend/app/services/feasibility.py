from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parcel import Parcel
from app.services.job_tracking import start_job_step
from app.services.zoning_system import get_zoning_from_db


async def run_parcel_feasibility(parcel_id: int, db: AsyncSession) -> dict[str, Any]:
    parcel = await db.get(Parcel, parcel_id)
    if parcel is None:
        raise ValueError(f"Parcel {parcel_id} not found")

    zoning = await get_zoning_from_db(parcel_id, db)
    if zoning is None:
        step = await start_job_step(
            db,
            None,
            "zoning",
            {"parcel_id": parcel_id},
        )
        step.status = "waiting_for_data"
        await db.flush()
        return {
            "status": "pending_zoning",
            "message": "Zoning data is being ingested",
        }

    rule = zoning["rule"]
    return {
        "status": "complete",
        "parcel_id": parcel_id,
        "zoning": {
            "city": rule.city,
            "zone_code": rule.zone_code,
            "density": rule.density,
            "max_units": rule.max_units,
            "min_lot_size": rule.min_lot_size,
            "setbacks": rule.setbacks,
            "height_limit": rule.height_limit,
            "source": rule.source,
            "confidence": rule.confidence,
        },
    }
