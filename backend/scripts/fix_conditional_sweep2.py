"""
Fix Round 2 — Residential/agricultural zones misclassified as 'conditional'.

Fixes:
  1. ALL cities: agricultural zone codes (A-1, A-2, A-3, A-4, A-5, A, RA-1, RA, RAPD) → prohibited
  2. Lehi:        PC, TH-5, RC, RA-1 → prohibited
  3. Lindon:      PC-1, PC-2, RC → prohibited
  4. Pleasant Grove: A-1, RAO → prohibited
  5. Provo:       RA, RAPD, A-* agricultural → prohibited

Run: python backend/scripts/fix_conditional_sweep2.py [--dry-run]
"""
from __future__ import annotations
import sys
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_URL = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"

DRY_RUN = "--dry-run" in sys.argv

# (description, SQL WHERE clause)
FIXES: list[tuple[str, str]] = [
    # ── Global: agricultural zone codes ──────────────────────────────────────
    (
        "ALL cities: agricultural zone codes (A-1..A-5, A, RA-*, RA, RAPD) → prohibited",
        r"""
        self_storage = 'conditional'
        AND classification_source NOT IN ('llm', 'human')
        AND (
            zone_code ~* '^A-\d'
            OR zone_code ~* '^A\d'
            OR zone_code = 'A'
            OR zone_code ~* '^RA-\d'
            OR zone_code IN ('RA', 'RAPD')
            OR zone_code ILIKE 'Agriculture%'
            OR zone_code ILIKE 'Agricultural%'
        )
        """,
    ),
    # ── Lehi-specific ─────────────────────────────────────────────────────────
    (
        "Lehi: PC, TH-5, RC, RA-1 → prohibited",
        r"""
        self_storage = 'conditional'
        AND classification_source NOT IN ('llm', 'human')
        AND jurisdiction_id = (
            SELECT id FROM jurisdictions WHERE name = 'Lehi' AND state = 'UT' LIMIT 1
        )
        AND zone_code IN ('PC', 'TH-5', 'RC', 'RA-1')
        """,
    ),
    # ── Lindon-specific ───────────────────────────────────────────────────────
    (
        "Lindon: PC-1, PC-2, RC → prohibited",
        r"""
        self_storage = 'conditional'
        AND classification_source NOT IN ('llm', 'human')
        AND jurisdiction_id = (
            SELECT id FROM jurisdictions WHERE name = 'Lindon' AND state = 'UT' LIMIT 1
        )
        AND zone_code IN ('PC-1', 'PC-2', 'RC')
        """,
    ),
    # ── Pleasant Grove ────────────────────────────────────────────────────────
    (
        "Pleasant Grove: A-1, RAO → prohibited",
        r"""
        self_storage = 'conditional'
        AND classification_source NOT IN ('llm', 'human')
        AND jurisdiction_id = (
            SELECT id FROM jurisdictions WHERE name = 'Pleasant Grove' AND state = 'UT' LIMIT 1
        )
        AND zone_code IN ('A-1', 'RAO')
        """,
    ),
    # ── Highland ─────────────────────────────────────────────────────────────
    (
        "Highland: A-* agricultural → prohibited",
        r"""
        self_storage = 'conditional'
        AND classification_source NOT IN ('llm', 'human')
        AND jurisdiction_id = (
            SELECT id FROM jurisdictions WHERE name = 'Highland' AND state = 'UT' LIMIT 1
        )
        AND zone_code ~* '^A[-\d]'
        """,
    ),
    # ── Bluffdale A-5 ─────────────────────────────────────────────────────────
    (
        "Bluffdale: A-5 → prohibited",
        r"""
        self_storage = 'conditional'
        AND classification_source NOT IN ('llm', 'human')
        AND jurisdiction_id = (
            SELECT id FROM jurisdictions WHERE name = 'Bluffdale' AND state = 'UT' LIMIT 1
        )
        AND zone_code IN ('A-5', 'A-1', 'A-2', 'A-3', 'A-4')
        """,
    ),
]

UPDATE_SQL = """
UPDATE zone_use_matrix
SET
    self_storage        = 'prohibited',
    mini_warehouse      = 'prohibited',
    luxury_garage_condo = 'prohibited',
    notes = COALESCE(notes || ' | ', '') || 'fix_conditional_sweep2: reclassified to prohibited'
WHERE {where}
"""

COUNT_SQL = "SELECT COUNT(*) FROM zone_use_matrix WHERE {where}"


async def main() -> None:
    engine = create_async_engine(DB_URL)
    total = 0

    async with engine.begin() as conn:
        for desc, where in FIXES:
            count_row = await conn.execute(text(COUNT_SQL.format(where=where)))
            count = count_row.scalar()
            logger.info("[%s] %d rows affected", desc, count)

            if count and not DRY_RUN:
                await conn.execute(text(UPDATE_SQL.format(where=where)))
                total += count

        if DRY_RUN:
            logger.info("DRY RUN — no changes committed")
        else:
            logger.info("Committed %d total row updates", total)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
