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

from app.services.zone_classifier import PerUseClassification, apply_luxury_garage_inference, storage_cls

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_URL = "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"


# ── Per-city classifiers ──────────────────────────────────────────────────────

def classify_herriman(code: str) -> PerUseClassification:
    u = code.strip().upper()
    if u == "M-1":
        return storage_cls("permitted", 0.80, "Herriman industrial M-1")
    if re.match(r'^R-[0-9]', u) or re.match(r'^FR-', u):
        return storage_cls("prohibited", 0.80, "Herriman residential")
    if re.match(r'^A-1', u):
        return storage_cls("conditional", 0.65, "Herriman agricultural")
    if u in ("C-1", "C-2"):
        return storage_cls("conditional", 0.70, "Herriman commercial")
    if u.startswith("MU"):
        return storage_cls("prohibited", 0.70, "Herriman mixed use — residential-oriented")
    if u == "OP":
        return storage_cls("prohibited", 0.72, "Herriman office park")
    if u == "RC":
        return storage_cls("prohibited", 0.75, "Herriman rural conservation")
    if u in ("LPMPC", "AMSD"):
        return storage_cls("conditional", 0.60, "Herriman planned/master community")
    if u == "TM":
        return storage_cls("conditional", 0.65, "Herriman transitional mixed")
    logger.warning("[Herriman] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Herriman unknown zone code '{code}' — conservative default")


def classify_eagle_mountain(code: str) -> PerUseClassification:
    u = code.strip().upper()

    if u in ("INDUSTRIAL", "LIGHT MANUFACTURING/DISTRIBUTION ZONE",
             "BUSINESS PARK / LIGHT INDUSTRIAL", "BUSINESS PARK",
             "REGIONAL TECHNOLOGY", "AIRPARK", "LMD",
             "COMMERCIAL/INDUSTRIAL", "COMMERCIAL STORAGE"):
        return storage_cls("permitted", 0.80, f"Eagle Mountain industrial/storage: {code}")

    if u == "MIXED-USE RESIDENTIAL/COMMERCIAL":
        return storage_cls("prohibited", 0.72, "Eagle Mountain mixed-use residential — storage not permitted")

    if any(u.startswith(p) for p in ("COMMERCIAL", "VILLAGE CORE - COMMERCIAL",
                                      "NEIGHBORHOOD COMMERCIAL", "SATELLITE COMMERCIAL",
                                      "SATELLITE/COMMERCIAL", "TOWN CENTER")):
        return storage_cls("conditional", 0.70, f"Eagle Mountain commercial: {code}")

    if u in ("VILLAGE CORE", "FLEX USE TIER III-IV", "UNDER REVIEW", "OTHER"):
        return storage_cls("conditional", 0.60, f"Eagle Mountain flex/unknown commercial: {code}")

    if u.startswith("AGRICULTURE"):
        return storage_cls("conditional", 0.65, "Eagle Mountain agricultural")

    if any(kw in u for kw in ("OPEN SPACE", "PARK", "POND", "RETENTION",
                                "CHURCH", "SCHOOL", "FIRE STATION",
                                "PUBLIC FACILIT")):
        return storage_cls("prohibited", 0.78, f"Eagle Mountain civic/open space: {code}")

    if u in ("OS-1", "OS-N", "RC"):
        return storage_cls("prohibited", 0.78, f"Eagle Mountain open space/conservation: {code}")

    return storage_cls("prohibited", 0.72, f"Eagle Mountain residential (catch-all): {code}")


def classify_hurricane(code: str) -> PerUseClassification:
    u = code.strip().upper()
    if u in ("M-1", "M-2", "BMP"):
        return storage_cls("permitted", 0.80, "Hurricane industrial")
    if u in ("HC", "GC", "NC", "PC"):
        return storage_cls("conditional", 0.70, "Hurricane commercial")
    if re.match(r'^A-', u):
        return storage_cls("conditional", 0.65, "Hurricane agricultural")
    if u == "MH/RV":
        return storage_cls("conditional", 0.65, "Hurricane MH/RV park — storage commonly co-located")
    if u in ("PF", "OS"):
        return storage_cls("prohibited", 0.78, "Hurricane public/open space")
    if re.match(r'^R[M1A]', u) or u == "RR":
        return storage_cls("prohibited", 0.80, "Hurricane residential")
    logger.warning("[Hurricane] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Hurricane unknown zone code '{code}' — conservative default")


def classify_kaysville(code: str) -> PerUseClassification:
    u = code.strip().upper()
    if u == "LI":
        return storage_cls("permitted", 0.80, "Kaysville light industrial")
    if u in ("GC", "HC", "CC"):
        return storage_cls("conditional", 0.70, "Kaysville commercial")
    if u == "MU":
        return storage_cls("prohibited", 0.70, "Kaysville mixed use — residential-oriented")
    if re.match(r'^A-', u):
        return storage_cls("conditional", 0.65, "Kaysville agricultural")
    if u in ("PB", "PU"):
        return storage_cls("prohibited", 0.72, "Kaysville professional/public utility")
    if re.match(r'^R-', u):
        return storage_cls("prohibited", 0.80, "Kaysville residential")
    logger.warning("[Kaysville] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Kaysville unknown zone code '{code}' — conservative default")


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


async def replace_matrix(jur_id: str, name: str, classifications: dict[str, PerUseClassification]) -> None:
    """Delete existing rows and re-insert with all 4 use columns + classification_source."""
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        deleted = await conn.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": jur_id},
        )
        logger.info("[%s] Deleted %d old rows", name, deleted.rowcount)

        for zone_code, cls in classifications.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name,
                     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                     classification_source, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, :mw, :li, :lgc, 'rule', :conf, :notes)
            """), {
                "jid": jur_id,
                "zc": zone_code,
                "zn": zone_code,
                "ss": cls.self_storage,
                "mw": cls.mini_warehouse,
                "li": cls.light_industrial,
                "lgc": cls.luxury_garage_condo,
                "conf": cls.confidence,
                "notes": cls.notes,
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

        counts: dict[str, int] = {}
        for cls in classifications.values():
            counts[cls.self_storage] = counts.get(cls.self_storage, 0) + 1
        logger.info("[%s] Distribution: %s", name, counts)

        await replace_matrix(jur_id, name, classifications)

    logger.info("All cities done.")


if __name__ == "__main__":
    asyncio.run(main())
