"""
Fix West Jordan zone_use_matrix by replacing wrong overlay-zone entries
with correct base-zone classifications.

Uses Claude to classify each zone code, then upserts into zone_use_matrix.
"""
from __future__ import annotations

import asyncio
import json
import logging
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
WJ_JUR_ID = "f6273f2b-0911-440d-b639-fa80090f7f54"

# West Jordan zone code legend (from GIS field descriptions and WJ municipal code Chapter 13)
ZONE_LEGEND = """
West Jordan, Utah zone code reference:
- P-C, P-C(ZC): Planned Community (large mixed-use master plans)
- R-1-*: Single Family Residential (number = min lot sq ft in hundreds)
- R-2, R-2(*): Two Family Residential
- R-3-*: Multi-Family Residential
- R-M: Residential Multi-Family
- RR-.*: Rural Residential (acreage lots)
- RE-.*: Rural Estate
- LSFR: Low-Density Single Family Residential
- VLSFR: Very Low-Density Single Family Residential
- HFR: High-Density Family Residential
- MFR: Multi-Family Residential
- PRD(*): Planned Residential Development
- A-1, A-5, A-20, A-SP: Agricultural (1/5/20 acre min; SP=special)
- C-G, C-G(ZC): Commercial General
- C-M: Commercial Manufacturing
- C-N: Commercial Neighborhood
- CC-C: City Center Core
- CC-F: City Center Fringe
- CC-R: City Center Residential
- SC-1, SC-2, SC-3: Shopping Center (1=small, 3=regional)
- BR-P: Business/Retail Park
- P-O, P-O(ZC): Professional Office
- M-1: Light Manufacturing/Industrial
- M-2: General Manufacturing
- M-P: Manufacturing Park
- P-F: Public Facility
- (ZC) suffix = Zoning Condition applied; same base zone
- (PS) suffix = Planned Street condition; same base zone
- (PD) suffix = Planned Development; same base zone
- (SHO) suffix = Shoreline Overlay; same base zone
"""


def get_zone_codes() -> list[tuple[str, int]]:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT zoning_code, COUNT(*) as cnt
        FROM parcels
        WHERE jurisdiction_id = %s AND zoning_code IS NOT NULL
        GROUP BY zoning_code ORDER BY cnt DESC
    """, (WJ_JUR_ID,))
    rows = cur.fetchall()
    conn.close()
    return rows


def classify_zones(zone_codes: list[str]) -> dict[str, str]:
    """Rule-based classifier using West Jordan zone code naming patterns."""
    import re

    def classify_one(code: str) -> str:
        # Strip suffix variants: (ZC), (PS), (PD), (SHO) and whitespace
        base = re.sub(r'\s*\((ZC|PS|PD|SHO)\)\s*$', '', code.strip(), flags=re.IGNORECASE).strip()
        # Also strip trailing truncated variants like "(ZC" without closing paren
        base = re.sub(r'\s*\(ZC$', '', base).strip()
        u = base.upper()

        # Industrial — permitted
        if u in ("M-1", "M-2", "M-P"):
            return "permitted"

        # Commercial — conditional
        if u in ("C-G", "C-M", "SC-2", "SC-3", "BR-P", "C-N"):
            return "conditional"

        # Planned Community — conditional (large mixed-use)
        if u.startswith("P-C"):
            return "conditional"

        # Agricultural — conditional
        if re.match(r'^A-', u):
            return "conditional"

        # Residential patterns — prohibited
        if re.match(r'^R-[123]', u):
            return "prohibited"
        if re.match(r'^RR-', u):
            return "prohibited"
        if re.match(r'^RE-', u):
            return "prohibited"
        if re.match(r'^PRD', u):
            return "prohibited"
        if u in ("R-M", "MFR", "HFR", "LSFR", "VLSFR"):
            return "prohibited"

        # City Center — prohibited
        if u.startswith("CC-"):
            return "prohibited"

        # Small shopping center — prohibited
        if u == "SC-1":
            return "prohibited"

        # Professional Office — prohibited
        if u.startswith("P-O"):
            return "prohibited"

        # Public Facility — prohibited
        if u.startswith("P-F"):
            return "prohibited"

        # Default fallback — conditional (safer than prohibited)
        logger.warning("Unknown zone code '%s' — defaulting to conditional", code)
        return "conditional"

    return {code: classify_one(code) for code in zone_codes}


async def delete_old_and_insert(classifications: dict[str, str]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # Delete existing wrong entries
        deleted = await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": WJ_JUR_ID}
        )
        logger.info("Deleted %d old West Jordan matrix rows", deleted.rowcount)

        # Insert new entries
        inserted = 0
        for zone_code, perm in classifications.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name, self_storage, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, :conf, :notes)
            """), {
                "jid": WJ_JUR_ID,
                "zc": zone_code,
                "zn": zone_code,
                "ss": perm,
                "conf": 0.7,
                "notes": "Auto-classified from zone code name patterns via Claude"
            })
            inserted += 1

        logger.info("Inserted %d West Jordan matrix rows", inserted)


async def main() -> None:
    logger.info("Fetching West Jordan zone codes…")
    zones = get_zone_codes()
    zone_codes = [z[0] for z in zones]
    logger.info("Found %d distinct zone codes covering %d parcels",
                len(zone_codes), sum(z[1] for z in zones))

    logger.info("Classifying with Claude…")
    classifications = classify_zones(zone_codes)
    logger.info("Classified %d zones", len(classifications))

    counts = {"permitted": 0, "conditional": 0, "prohibited": 0}
    for v in classifications.values():
        counts[v] = counts.get(v, 0) + 1
    logger.info("Distribution: %s", counts)

    await delete_old_and_insert(classifications)
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
