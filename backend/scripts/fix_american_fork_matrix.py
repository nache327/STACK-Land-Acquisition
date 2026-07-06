"""
Fix American Fork zone_use_matrix — all entries were wrongly set to 'prohibited'.
Replaces the full matrix with correct rule-based classifications.

Run from backend/ directory:
    python scripts/fix_american_fork_matrix.py
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from scripts._db import get_dsn, get_sync_dsn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL = get_dsn()
DB_SYNC = get_sync_dsn()

AF_JUR_ID = "d3757bf8-b4f1-4142-bece-8c774c863955"


def classify_american_fork(code: str) -> str:
    u = code.strip().upper()

    # Industrial / Manufacturing — permitted
    # §17.6.110 sets explicit storage standards only for I-1; M-1 is same category
    if u in ("I-1", "M-1"):
        return "permitted"

    # Everything else — prohibited pending confirmation from use table exhibit
    # §17.6.110: "only in those zones in which such uses are specifically listed as a
    # permitted use." Use table (§14.13.080 / §14.15.030) is blank in published PDF.
    # Cannot confirm any other zone without the actual exhibit. Call AF Planning: 801-763-3060
    logger.warning("[American Fork] '%s' → prohibited (use table unverified)", code)
    return "prohibited"


def get_zone_codes() -> list[str]:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT zoning_code FROM parcels "
        "WHERE jurisdiction_id = %s AND zoning_code IS NOT NULL",
        (AF_JUR_ID,),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


async def replace_matrix(classifications: dict[str, str]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        deleted = await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": AF_JUR_ID},
        )
        logger.info("Deleted %d old American Fork matrix rows", deleted.rowcount)

        for zone_code, perm in classifications.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name, self_storage, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, 0.75, :notes)
            """), {
                "jid": AF_JUR_ID,
                "zc": zone_code,
                "zn": zone_code,
                "ss": perm,
                "notes": "§17.6.110 requires explicit use-table listing. Only I-1/M-1 confirmed. All others prohibited pending human verification (call AF Planning 801-763-3060).",
            })
        logger.info("Inserted %d American Fork matrix rows", len(classifications))
    await engine.dispose()


async def main() -> None:
    zone_codes = get_zone_codes()
    logger.info("Found %d distinct zone codes in American Fork parcels", len(zone_codes))

    classifications = {code: classify_american_fork(code) for code in zone_codes}

    counts: dict[str, int] = {}
    for v in classifications.values():
        counts[v] = counts.get(v, 0) + 1
    logger.info("Distribution: %s", counts)

    for code, perm in sorted(classifications.items()):
        logger.info("  %-20s → %s", code, perm)

    await replace_matrix(classifications)

    # Verify match rate
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(p.id) AS total,
               COUNT(z.zone_code) AS matched,
               ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id), 0), 1) AS pct
        FROM parcels p
        LEFT JOIN zone_use_matrix z
            ON z.jurisdiction_id = p.jurisdiction_id AND z.zone_code = p.zoning_code
        WHERE p.jurisdiction_id = %s
    """, (AF_JUR_ID,))
    row = cur.fetchone()
    conn.close()
    logger.info("American Fork match rate: %d/%d = %s%%", row[1], row[0], row[2])


if __name__ == "__main__":
    asyncio.run(main())
