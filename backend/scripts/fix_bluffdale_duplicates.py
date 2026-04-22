"""
Fix Bluffdale zone_use_matrix duplicates.

The DB has two entries per zone:
  - Short code (e.g. "I-1")            ← what parcels reference, has WRONG values
  - Long name (e.g. "I-1 Light Industry") ← has CORRECT values, never matched by parcels

Fix: update the short-code entries to correct values, delete the long-name duplicates.
"""
import asyncio
import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_URL = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")

BLUFFDALE = "cb5017c6-a845-4ffd-91a3-7dc26e2e5ce9"

# Short-code corrections: zone_code → (self_storage, mini_warehouse, light_industrial, luxury_garage_condo, confidence, notes)
SHORT_CODE_FIXES = {
    "I-1": ("permitted",    "permitted",    "permitted",    "conditional", 0.82, "Bluffdale I-1 Light Industrial — storage permitted by right"),
    "HC":  ("permitted",    "permitted",    "conditional",  "conditional", 0.78, "Bluffdale Heavy Commercial — storage permitted by right"),
    "DR":  ("permitted",    "conditional",  "conditional",  "permitted",   0.75, "Bluffdale DR Destination Retail — storage permitted"),
    "SG-1":("permitted",    "permitted",    "permitted",    "conditional", 0.80, "Bluffdale SG-1 Sand & Gravel — industrial storage permitted"),
    "GC-1":("conditional",  "conditional",  "conditional",  "conditional", 0.70, "Bluffdale GC-1 General Commercial — conditional use"),
}

# Long-name duplicates to delete (parcels never reference these codes)
LONG_NAME_DUPLICATES = [
    "I-1 Light Industry",
    "I-1 LIGHT INDUSTRY",
    "Heavy Commercial",
    "HEAVY COMMERCIAL",
    "DR Destination Retail",
    "DR DESTINATION RETAIL",
    "SG-1 Sand & Gravel",
    "SG-1 SAND & GRAVEL",
    "GC-1 Commercial",
    "GC-1 COMMERCIAL",
]


async def main() -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:

        # 1. Update short-code entries to correct values
        for zone_code, (ss, mw, li, lgc, conf, notes) in SHORT_CODE_FIXES.items():
            result = await conn.execute(text("""
                UPDATE zone_use_matrix
                SET self_storage        = :ss,
                    mini_warehouse      = :mw,
                    light_industrial    = :li,
                    luxury_garage_condo = :lgc,
                    confidence          = :conf,
                    notes               = :notes,
                    classification_source = 'rule'
                WHERE jurisdiction_id = :jid
                  AND zone_code = :zc
            """), {"jid": BLUFFDALE, "zc": zone_code, "ss": ss, "mw": mw,
                   "li": li, "lgc": lgc, "conf": conf, "notes": notes})
            logger.info("Updated %-8s → self_storage=%-12s (%d rows)", zone_code, ss, result.rowcount)

        # 2. Delete long-name duplicate entries
        for long_name in LONG_NAME_DUPLICATES:
            result = await conn.execute(text("""
                DELETE FROM zone_use_matrix
                WHERE jurisdiction_id = :jid
                  AND zone_code = :zc
            """), {"jid": BLUFFDALE, "zc": long_name})
            if result.rowcount:
                logger.info("Deleted duplicate: %r (%d rows)", long_name, result.rowcount)

    await engine.dispose()
    logger.info("Done — Bluffdale duplicates fixed.")


if __name__ == "__main__":
    asyncio.run(main())
