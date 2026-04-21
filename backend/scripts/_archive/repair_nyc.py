"""
NYC zoning repair: re-run zoning ingest + zone_class backfill using the
correct NYC Zoning Districts FeatureServer URL (v_Zoning_Districts_NYZD).
Parcels are left in place.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select

from app.db import async_session_maker
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.services.arcgis_query import download_all_features
from app.services.pipeline import _backfill_parcel_zone_class, _coverage_level
from app.services.zoning_ingestion import ingest_zoning_districts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ZONING_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services"
    "/v_Zoning_Districts_NYZD/FeatureServer/0"
)


async def main() -> None:
    async with async_session_maker() as db:
        j = (await db.execute(
            select(Jurisdiction).where(Jurisdiction.name == "New York, NY")
        )).scalar_one()
        logger.info("NYC jurisdiction id: %s", j.id)

        parcel_count = (await db.execute(
            select(func.count()).select_from(Parcel).where(Parcel.jurisdiction_id == j.id)
        )).scalar_one()
        logger.info("Existing parcels: %d", parcel_count)

        logger.info("Downloading NYC zoning districts …")
        zgdf = await download_all_features(ZONING_URL, where="1=1")
        zoning_count = await ingest_zoning_districts(zgdf, j.id, db, replace=True)
        await db.commit()
        logger.info("Ingested %d zoning districts", zoning_count)

        updated = await _backfill_parcel_zone_class(j.id, db)
        await db.commit()
        logger.info("zone_class backfill updated %d parcels", updated)

        j.coverage_level = _coverage_level(
            parcel_count=parcel_count, zoning_count=zoning_count
        )
        await db.commit()
        logger.info("coverage_level: %s", j.coverage_level)


if __name__ == "__main__":
    asyncio.run(main())
