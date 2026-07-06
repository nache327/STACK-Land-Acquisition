"""
One-shot fix: download Farmington zoning districts, ingest into PostGIS,
run spatial backfill to assign zone_code/zone_class to parcels, and
bootstrap the zone_use_matrix.

Run from backend/ directory:
    python scripts/fix_farmington_zoning.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts._db import get_dsn

os.environ.setdefault("DATABASE_URL", get_dsn())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

FARMINGTON_JUR_ID = "f90d021b-98fe-47b0-ad31-bf8c1b2dd23f"
ZONING_ENDPOINT = (
    "https://services6.arcgis.com/IkwwnD5sRYXgxM2N/arcgis/rest"
    "/services/CEDEV_ZONING_FC2017F_Zoning_View/FeatureServer/0"
)


async def main() -> None:
    import uuid
    from app.db import async_session_maker
    from app.services.arcgis_query import download_all_features
    from app.services.zoning_ingestion import ingest_zoning_districts
    from app.services.spatial_backfill import backfill_parcel_zoning_from_districts
    from app.services.matrix_bootstrap import bootstrap_zone_use_matrix

    jur_id = uuid.UUID(FARMINGTON_JUR_ID)

    async with async_session_maker() as db:
        # 1. Download zoning polygons
        logger.info("Downloading Farmington zoning districts …")
        zgdf = await download_all_features(ZONING_ENDPOINT, where="1=1")
        logger.info("Downloaded %d zoning polygons", len(zgdf))

        if zgdf.empty:
            logger.error("No zoning features returned — aborting")
            return

        # 2. Ingest into zoning_districts table (replaces any prior rows)
        logger.info("Ingesting zoning districts into PostGIS …")
        count = await ingest_zoning_districts(zgdf, jur_id, db, replace=True)
        await db.commit()
        logger.info("Ingested %d zoning districts", count)

        if count == 0:
            logger.error("Zero districts ingested — check field mapping")
            return

        # 3. Spatial backfill: assign zone_code + zone_class to parcels
        logger.info("Running spatial backfill (parcel ∩ zoning district) …")
        updated = await backfill_parcel_zoning_from_districts(jur_id, db)
        await db.commit()
        logger.info("Backfill updated %d parcels with zone_code/zone_class", updated)

        # 4. Bootstrap zone_use_matrix rows (creates unclassified stubs for
        #    any zone code not yet in the matrix, so the ordinance parser can
        #    fill them in later)
        logger.info("Bootstrapping zone_use_matrix …")
        seeded = await bootstrap_zone_use_matrix(jur_id, db, missing_only=True)
        await db.commit()
        logger.info("Bootstrapped %d zone_use_matrix rows", seeded)

        logger.info("=== Farmington zoning fix complete ===")
        logger.info(
            "  Zoning districts ingested : %d", count
        )
        logger.info(
            "  Parcels updated           : %d", updated
        )
        logger.info(
            "  Matrix rows seeded        : %d", seeded
        )


if __name__ == "__main__":
    asyncio.run(main())
