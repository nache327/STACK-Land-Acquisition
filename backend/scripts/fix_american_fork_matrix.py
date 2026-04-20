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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"

AF_JUR_ID = "d3757bf8-b4f1-4142-bece-8c774c863955"


def classify_american_fork(code: str) -> str:
    u = code.strip().upper()

    # Industrial / Manufacturing — permitted
    if u in ("I-1", "M-1"):
        return "permitted"

    # General / Community Commercial — conditional
    if u in ("GC-1", "GC-2", "CC-1", "CC-2", "SC-1"):
        return "conditional"

    # Transit-Oriented Development — conditional
    if u == "TOD":
        return "conditional"

    # Planned Community — conditional
    if u == "PC":
        return "conditional"

    # Professional/Industrial — conditional
    if u == "PI-1":
        return "conditional"

    # Rural Agricultural — conditional
    if re.match(r'^RA-', u):
        return "conditional"

    # Professional Office — conditional (self-storage listed as CUP in Jan 2025 PC minutes)
    if u.startswith("PO"):
        return "conditional"

    # Public Facility / Shoreline Preservation — prohibited
    if u in ("PF", "SP"):
        return "prohibited"

    # Residential (R1-, R2-, R3-, R4-, PR-) — prohibited
    if re.match(r'^R[1-4]-', u):
        return "prohibited"
    if re.match(r'^PR-', u):
        return "prohibited"

    # Special / unclassified — conditional (conservative default)
    logger.warning("[American Fork] Unknown code '%s' — conditional", code)
    return "conditional"


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
                "notes": "Heuristic from AF zoning code §17.6.110 + Jan 2025 Planning Commission use matrix reference",
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
