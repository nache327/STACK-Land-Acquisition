"""
One-shot backfill script: download UGRC parcels for every Utah jurisdiction
that has zone_use_matrix data but 0 parcels.

Run from backend/ directory:
    python scripts/backfill_utah_parcels.py

Connects directly to Supabase — no Railway deployment needed.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_maker
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel
from app.models.zone_use_matrix import ZoneUseMatrix
from app.services.arcgis_query import download_all_features
from app.services.ingestion import ingest_parcels

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_UGRC = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services"

# city name (lowercase) → (county_service, parcel_city_value)
CITY_MAP: dict[str, tuple[str, str]] = {
    # Salt Lake County
    "sandy, ut":            ("Parcels_SaltLake", "Sandy"),
    "west jordan, ut":      ("Parcels_SaltLake", "West Jordan"),
    "west valley city, ut": ("Parcels_SaltLake", "West Valley City"),
    "south jordan, ut":     ("Parcels_SaltLake", "South Jordan"),
    "midvale, ut":          ("Parcels_SaltLake", "Midvale"),
    "millcreek, ut":        ("Parcels_SaltLake", "Millcreek"),
    "cottonwood heights, ut": ("Parcels_SaltLake", "Cottonwood Heights"),
    "murray, ut":           ("Parcels_SaltLake", "Murray"),
    "taylorsville, ut":     ("Parcels_SaltLake", "Taylorsville"),
    "herriman, ut":         ("Parcels_SaltLake", "Herriman"),
    "riverton, ut":         ("Parcels_SaltLake", "Riverton"),
    "holladay, ut":         ("Parcels_SaltLake", "Holladay"),
    "south salt lake, ut":  ("Parcels_SaltLake", "South Salt Lake"),
    "bluffdale, ut":        ("Parcels_SaltLake", "Bluffdale"),
    "salt lake city, ut":   ("Parcels_SaltLake", "Salt Lake City"),
    # Utah County
    "provo, ut":            ("Parcels_Utah", "Provo"),
    "orem, ut":             ("Parcels_Utah", "Orem"),
    "lehi, ut":             ("Parcels_Utah", "Lehi"),
    "american fork, ut":    ("Parcels_Utah", "American Fork"),
    "eagle mountain, ut":   ("Parcels_Utah", "Eagle Mountain"),
    "pleasant grove, ut":   ("Parcels_Utah", "Pleasant Grove"),
    "springville, ut":      ("Parcels_Utah", "Springville"),
    "spanish fork, ut":     ("Parcels_Utah", "Spanish Fork"),
    "payson, ut":           ("Parcels_Utah", "Payson"),
    # Weber County
    "ogden, ut":            ("Parcels_Weber", "Ogden"),
    "roy, ut":              ("Parcels_Weber", "Roy"),
    "west haven, ut":       ("Parcels_Weber", "West Haven"),
    # Davis County
    "layton, ut":           ("Parcels_Davis", "Layton"),
    "bountiful, ut":        ("Parcels_Davis", "Bountiful"),
    "clearfield, ut":       ("Parcels_Davis", "Clearfield"),
    "syracuse, ut":         ("Parcels_Davis", "Syracuse"),
    "farmington, ut":       ("Parcels_Davis", "Farmington"),
    "kaysville, ut":        ("Parcels_Davis", "Kaysville"),
    "north salt lake, ut":  ("Parcels_Davis", "North Salt Lake"),
    # Cache County
    "logan, ut":            ("Parcels_Cache", "Logan"),
    # Washington County
    "st george, ut":        ("Parcels_Washington", "St. George"),
    "washington, ut":       ("Parcels_Washington", "Washington"),
    "hurricane, ut":        ("Parcels_Washington", "Hurricane"),
    # Iron County
    "cedar city, ut":       ("Parcels_Iron", "Cedar City"),
    # Tooele County
    "tooele, ut":           ("Parcels_Tooele", "Tooele"),
}


async def backfill_city(db: AsyncSession, jur: Jurisdiction) -> int:
    key = jur.name.lower()
    mapping = CITY_MAP.get(key)
    if mapping is None:
        logger.warning("No UGRC mapping for %r — skipping", jur.name)
        return 0

    service, city_val = mapping
    endpoint = f"{_UGRC}/{service}/FeatureServer/0"
    where = f"PARCEL_CITY='{city_val}'"

    logger.info("=== %s === endpoint=%s WHERE %s", jur.name, service, where)
    try:
        gdf = await download_all_features(endpoint, where=where)
        logger.info("  Downloaded %d features", len(gdf))
        if gdf.empty:
            logger.warning("  0 features returned — check PARCEL_CITY value")
            return 0
        count = await ingest_parcels(gdf, jur.id, db, replace=True)
        logger.info("  Ingested %d parcels for %s", count, jur.name)
        return count
    except Exception as exc:
        logger.error("  Failed %s: %s", jur.name, exc)
        return 0


async def main() -> None:
    async with async_session_maker() as db:
        # Find jurisdictions with zone data but no parcels
        result = await db.execute(
            select(Jurisdiction)
            .where(Jurisdiction.state == "UT")
            .order_by(Jurisdiction.name)
        )
        jurisdictions = result.scalars().all()

        targets = []
        for jur in jurisdictions:
            # Skip if already has parcels
            parcel_result = await db.execute(
                select(func.count()).select_from(Parcel)
                .where(Parcel.jurisdiction_id == jur.id)
            )
            parcel_count = parcel_result.scalar_one()
            if parcel_count > 0:
                logger.info("SKIP %s — already has %d parcels", jur.name, parcel_count)
                continue

            # Check if it has zone data
            zone_result = await db.execute(
                select(func.count()).select_from(ZoneUseMatrix)
                .where(ZoneUseMatrix.jurisdiction_id == jur.id)
            )
            zone_count = zone_result.scalar_one()
            if zone_count == 0:
                logger.info("SKIP %s — no zone data", jur.name)
                continue

            targets.append(jur)

        logger.info("Found %d cities to backfill", len(targets))

        total = 0
        for jur in targets:
            count = await backfill_city(db, jur)
            total += count
            if count > 0:
                await db.commit()
                logger.info("  Committed %s", jur.name)

        logger.info("=== DONE: %d total parcels inserted ===", total)


if __name__ == "__main__":
    asyncio.run(main())
