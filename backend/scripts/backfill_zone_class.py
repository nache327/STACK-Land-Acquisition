"""
Backfill zone_class for all parcels where it is NULL or 'unknown'.

Classifies each (jurisdiction_id, zoning_code) pair using the heuristic
classifier and bulk-updates matching parcels. Spatial-join data (from
zoning_districts) always takes precedence — this script only fills gaps.

Run from the backend/ directory:
    python scripts/backfill_zone_class.py

Skips rows where zone_class is already set to a non-unknown value (including
rows previously set by the spatial join pipeline).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_maker
from app.models.zoning_district import ZoneClass
from app.services.classification import classify_zone_code

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    async with async_session_maker() as db:
        # Fetch all distinct (jurisdiction_id, zoning_code) pairs that still
        # need classification. We cover:
        #   1. zone_class IS NULL  — never set
        #   2. zone_class = 'unknown' — classifier returned unknown previously
        result = await db.execute(text("""
            SELECT DISTINCT
                j.name AS jurisdiction_name,
                p.jurisdiction_id::text AS jurisdiction_id,
                p.zoning_code
            FROM parcels p
            JOIN jurisdictions j ON j.id = p.jurisdiction_id
            WHERE p.zoning_code IS NOT NULL
              AND (p.zone_class IS NULL OR p.zone_class = 'unknown')
            ORDER BY j.name, p.zoning_code
        """))
        pairs = result.fetchall()

    logger.info("Found %d (jurisdiction, zone_code) pairs to classify", len(pairs))

    # Classify each pair
    updates: list[tuple[str, str, str]] = []  # (zone_class_value, jurisdiction_id, zoning_code)
    remaining_unknown: list[tuple[str, str]] = []

    for row in pairs:
        jur_name = row.jurisdiction_name
        jid = row.jurisdiction_id
        code = row.zoning_code
        zc = classify_zone_code(code)
        if zc == ZoneClass.unknown:
            remaining_unknown.append((jur_name, code))
        else:
            updates.append((zc.value, jid, code))

    logger.info(
        "Classified: %d resolvable, %d remain unknown",
        len(updates), len(remaining_unknown),
    )

    if not updates:
        logger.info("Nothing to update.")
    else:
        # Batch update by (jurisdiction_id, zoning_code)
        async with async_session_maker() as db:
            total = 0
            for zone_class_val, jid, code in updates:
                r = await db.execute(text("""
                    UPDATE parcels
                    SET zone_class = :zc
                    WHERE jurisdiction_id = :jid::uuid
                      AND zoning_code = :code
                      AND (zone_class IS NULL OR zone_class = 'unknown')
                """), {"zc": zone_class_val, "jid": jid, "code": code})
                total += r.rowcount
            await db.commit()

        logger.info("Updated %d parcel rows", total)

    if remaining_unknown:
        # Group by jurisdiction for easier reading
        by_jur: dict[str, list[str]] = {}
        for jname, code in remaining_unknown:
            by_jur.setdefault(jname, []).append(code)

        print(f"\n{'='*60}")
        print(f"STILL UNKNOWN after classifier ({len(remaining_unknown)} codes):")
        for jname, codes in sorted(by_jur.items()):
            # Count parcels for each unknown code
            print(f"  {jname}: {', '.join(sorted(codes)[:10])}"
                  + (f" ... ({len(codes)} total)" if len(codes) > 10 else ""))
        print("="*60)
    else:
        print("\nAll zone codes are now classified!")


if __name__ == "__main__":
    asyncio.run(run())
