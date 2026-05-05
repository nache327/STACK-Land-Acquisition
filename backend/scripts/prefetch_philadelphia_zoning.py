"""
Pre-fetch Philadelphia zoning districts and run the spatial backfill so
future jobs skip the download phase entirely.

Usage (from backend/):
    railway run python scripts/prefetch_philadelphia_zoning.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.models.zoning_district import ZoningDistrict
from app.services.arcgis_query import download_all_features
from app.services.spatial_backfill import backfill_parcel_zoning_from_districts
from app.services.zoning_ingestion import ingest_zoning_districts

# Session-mode engine (port 5432) — avoids PgBouncer read-only connections.
_session_url = settings.database_url.replace(":6543/", ":5432/")
_engine = create_async_engine(
    _session_url,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0, "command_timeout": 600},
)
_session_maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ZONING_ENDPOINT = (
    "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/"
    "Zoning_BaseDistricts/FeatureServer/0"
)


async def main() -> None:
    async with _session_maker() as db:
        # 1. Look up Philadelphia jurisdiction
        result = await db.execute(
            select(Jurisdiction).where(
                Jurisdiction.name.ilike("%philadelphia%")
            )
        )
        jurisdiction = result.scalar_one_or_none()
        if not jurisdiction:
            logger.error("Philadelphia jurisdiction not found in DB")
            return
        logger.info("Jurisdiction: %s (%s)", jurisdiction.name, jurisdiction.id)

        # 2. Check existing zoning districts
        existing = await db.scalar(
            select(func.count(ZoningDistrict.id)).where(
                ZoningDistrict.jurisdiction_id == jurisdiction.id
            )
        )
        logger.info("Existing zoning districts: %d", existing or 0)

        # 3. Download zoning districts from ArcGIS
        logger.info("Downloading zoning districts from ArcGIS...")
        t0 = time.perf_counter()
        zgdf = await download_all_features(ZONING_ENDPOINT)
        elapsed = time.perf_counter() - t0
        logger.info("Downloaded %d zoning features in %.1fs", len(zgdf), elapsed)

        if zgdf.empty:
            logger.error("No zoning features downloaded — aborting")
            return

        # 4. Ingest into zoning_districts (replaces any existing rows)
        logger.info("Ingesting zoning districts into DB...")
        t1 = time.perf_counter()
        count = await ingest_zoning_districts(zgdf, jurisdiction.id, db, replace=True)
        await db.commit()
        logger.info("Ingested %d zoning districts in %.1fs", count, time.perf_counter() - t1)

        # 5. Spatial backfill via raw asyncpg — bypasses SQLAlchemy's connection
        # handling and sets statement_timeout at the SESSION level (not LOCAL)
        # so Supabase won't cancel the long-running spatial join.
        parcel_count = await db.scalar(
            select(func.count(Parcel.id)).where(
                Parcel.jurisdiction_id == jurisdiction.id
            )
        )
        logger.info("Running spatial backfill for %d parcels via raw asyncpg...", parcel_count or 0)
        t2 = time.perf_counter()

        import asyncpg as _asyncpg
        raw_url = _session_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await _asyncpg.connect(raw_url, statement_cache_size=0, command_timeout=7200)
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
                jurisdiction.id,
            )
        finally:
            await conn.close()

        updated = int(result.split()[-1]) if result else 0
        logger.info(
            "Backfill complete: %d parcels updated in %.1fs",
            updated,
            time.perf_counter() - t2,
        )

        # 6. Confirm
        unzoned = await db.scalar(
            select(func.count(Parcel.id)).where(
                Parcel.jurisdiction_id == jurisdiction.id,
                Parcel.zoning_code.is_(None),
            )
        )
        logger.info(
            "Done. Zoning districts: %d | Parcels updated: %d | Still unzoned: %d",
            count,
            updated,
            unzoned or 0,
        )


asyncio.run(main())
