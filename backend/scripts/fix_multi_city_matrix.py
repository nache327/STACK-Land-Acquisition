"""
Fix zone_use_matrix for Herriman, Eagle Mountain, Hurricane, and Kaysville.
Replaces existing entries with rule-based classifications derived from
each city's zone code naming conventions.

Run from backend/ directory:
    python scripts/fix_multi_city_matrix.py
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


# ── Per-city classifiers ──────────────────────────────────────────────────────

def classify_herriman(code: str) -> str:
    u = code.strip().upper()
    # Industrial
    if u == "M-1":
        return "permitted"
    # Residential
    if re.match(r'^R-[0-9]', u) or re.match(r'^FR-', u):
        return "prohibited"
    # Agricultural
    if re.match(r'^A-1', u):
        return "conditional"
    # Commercial
    if u in ("C-1", "C-2"):
        return "conditional"
    # Mixed Use
    if u.startswith("MU"):
        return "conditional"
    # Office Park
    if u == "OP":
        return "prohibited"
    # Rural Conservation
    if u == "RC":
        return "prohibited"
    # Planned/master community
    if u in ("LPMPC", "AMSD"):
        return "conditional"
    # Transitional Mixed
    if u == "TM":
        return "conditional"
    logger.warning("[Herriman] Unknown code '%s' — conditional", code)
    return "conditional"


def classify_eagle_mountain(code: str) -> str:
    u = code.strip().upper()

    # Explicit permitted
    if u in ("INDUSTRIAL", "LIGHT MANUFACTURING/DISTRIBUTION ZONE",
             "BUSINESS PARK / LIGHT INDUSTRIAL", "BUSINESS PARK",
             "REGIONAL TECHNOLOGY", "AIRPARK", "LMD",
             "COMMERCIAL/INDUSTRIAL", "COMMERCIAL STORAGE"):
        return "permitted"

    # Commercial — conditional
    if any(u.startswith(p) for p in ("COMMERCIAL", "VILLAGE CORE - COMMERCIAL",
                                      "NEIGHBORHOOD COMMERCIAL", "SATELLITE COMMERCIAL",
                                      "SATELLITE/COMMERCIAL", "TOWN CENTER")):
        return "conditional"
    if u in ("VILLAGE CORE", "MIXED-USE RESIDENTIAL/COMMERCIAL",
             "FLEX USE TIER III-IV", "UNDER REVIEW", "OTHER"):
        return "conditional"

    # Agriculture — conditional
    if u.startswith("AGRICULTURE"):
        return "conditional"

    # Open space / parks / civic — prohibited
    if any(kw in u for kw in ("OPEN SPACE", "PARK", "POND", "RETENTION",
                                "CHURCH", "SCHOOL", "FIRE STATION",
                                "PUBLIC FACILIT")):
        return "prohibited"
    if u in ("OS-1", "OS-N", "RC"):
        return "prohibited"

    # Residential — prohibited (catch-all for everything left)
    return "prohibited"


def classify_hurricane(code: str) -> str:
    u = code.strip().upper()
    # Industrial
    if u in ("M-1", "M-2", "BMP"):
        return "permitted"
    # Commercial
    if u in ("HC", "GC", "NC", "PC"):
        return "conditional"
    # Agricultural
    if re.match(r'^A-', u):
        return "conditional"
    # MH/RV parks — conditional (storage commonly co-located)
    if u == "MH/RV":
        return "conditional"
    # Public / open space
    if u in ("PF", "OS"):
        return "prohibited"
    # Residential
    if re.match(r'^R[M1A]', u) or u == "RR":
        return "prohibited"
    logger.warning("[Hurricane] Unknown code '%s' — conditional", code)
    return "conditional"


def classify_kaysville(code: str) -> str:
    u = code.strip().upper()
    # Industrial
    if u == "LI":
        return "permitted"
    # Commercial
    if u in ("GC", "HC", "CC", "MU"):
        return "conditional"
    # Agricultural
    if re.match(r'^A-', u):
        return "conditional"
    # Professional Business
    if u == "PB":
        return "prohibited"
    # Public Utility
    if u == "PU":
        return "prohibited"
    # Residential (R-* and R-A, R-D, R-T, R-M)
    if re.match(r'^R-', u):
        return "prohibited"
    logger.warning("[Kaysville] Unknown code '%s' — conditional", code)
    return "conditional"


CITY_CONFIGS = [
    {
        "name": "Herriman",
        "jur_id": "8c489a6c-fdec-4d4d-98c1-3157d0233a8b",
        "classifier": classify_herriman,
    },
    {
        "name": "Eagle Mountain",
        "jur_id": "1f0d6f93-8e5c-462b-88ed-9d6a9e107bc1",
        "classifier": classify_eagle_mountain,
    },
    {
        "name": "Hurricane",
        "jur_id": "648f20ae-ff2d-4876-b936-d67c20488eec",
        "classifier": classify_hurricane,
    },
    {
        "name": "Kaysville",
        "jur_id": "0a9e2fb0-031a-4905-a07f-b645dadc5827",
        "classifier": classify_kaysville,
    },
]


def get_zone_codes(jur_id: str) -> list[str]:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT zoning_code FROM parcels "
        "WHERE jurisdiction_id = %s AND zoning_code IS NOT NULL",
        (jur_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


async def replace_matrix(jur_id: str, name: str, classifications: dict[str, str]) -> None:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        deleted = await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": jur_id},
        )
        logger.info("[%s] Deleted %d old rows", name, deleted.rowcount)

        for zone_code, perm in classifications.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name, self_storage, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, :conf, :notes)
            """), {
                "jid": jur_id,
                "zc": zone_code,
                "zn": zone_code,
                "ss": perm,
                "conf": 0.75,
                "notes": "Rule-based classification from zone code naming patterns",
            })
        logger.info("[%s] Inserted %d rows", name, len(classifications))
    await engine.dispose()


async def main() -> None:
    for city in CITY_CONFIGS:
        name = city["name"]
        jur_id = city["jur_id"]
        classifier = city["classifier"]

        zone_codes = get_zone_codes(jur_id)
        logger.info("[%s] %d distinct zone codes", name, len(zone_codes))

        classifications = {code: classifier(code) for code in zone_codes}

        counts = {}
        for v in classifications.values():
            counts[v] = counts.get(v, 0) + 1
        logger.info("[%s] Distribution: %s", name, counts)

        await replace_matrix(jur_id, name, classifications)

    logger.info("All cities done.")


if __name__ == "__main__":
    asyncio.run(main())
