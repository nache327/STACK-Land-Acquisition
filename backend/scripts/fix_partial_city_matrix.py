"""
Fix zone_use_matrix coverage gaps for:
  - Sandy        (PUD/SD variants, large-lot residential)
  - Washington   (14 missing residential/agricultural codes)
  - American Fork (R1- vs R-1- naming mismatch)
  - Bluffdale    (descriptive long-form zone names)
  - Draper       (compound semicolon-separated zone codes)

Only INSERTs new rows — does not touch existing correct entries.
Writes all 4 use columns + classification_source so data provenance is tracked.

Run from backend/ directory:
    python scripts/fix_partial_city_matrix.py
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


def get_unmatched_codes(jur_id: str) -> list[str]:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT p.zoning_code
        FROM parcels p
        LEFT JOIN zone_use_matrix z
            ON z.jurisdiction_id = p.jurisdiction_id AND z.zone_code = p.zoning_code
        WHERE p.jurisdiction_id = %s
          AND p.zoning_code IS NOT NULL
          AND z.zone_code IS NULL
    """, (jur_id,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_existing_matrix(jur_id: str) -> dict[str, str]:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("SELECT zone_code, self_storage FROM zone_use_matrix WHERE jurisdiction_id = %s", (jur_id,))
    result = {r[0]: r[1] for r in cur.fetchall()}
    conn.close()
    return result


# ── Sandy ─────────────────────────────────────────────────────────────────────

def classify_sandy(code: str) -> PerUseClassification:
    u = code.strip()

    if re.match(r'^R-1-\d+A$', u):
        return storage_cls("prohibited", 0.72, "Sandy large-lot residential")

    if re.match(r'^RM\(\d', u):
        return storage_cls("prohibited", 0.72, "Sandy parameterized multifamily")

    if re.match(r'^PUD[\s(]', u) or re.match(r'^PUD \d', u):
        return storage_cls("conditional", 0.65, "Sandy planned unit development")

    sd_match = re.match(r'^SD\((.+?)\)', u)
    if sd_match:
        inner = sd_match.group(1).upper()
        if re.match(r'^R[-\s]', inner) or inner.startswith('RM') or re.match(r'^\d+\.\d+$', inner):
            return storage_cls("prohibited", 0.70, "Sandy SD residential base zone")
        if any(inner.startswith(p) for p in ('CC', 'CN', 'C-', 'MU', 'PO', 'TC', 'SMART', 'FM', 'MAGNA',
                                              'HARADA', 'MDM', 'UNION', 'UN.', 'CARNATION', 'JHS',
                                              '1300', 'EH', 'H', 'P', 'X', 'OS', 'MU', 'C)')):
            return storage_cls("conditional", 0.65, "Sandy SD commercial/mixed base zone")
        if inner.startswith('OS'):
            return storage_cls("prohibited", 0.70, "Sandy SD open space")
        return storage_cls("conditional", 0.60, "Sandy SD unknown base zone")

    if u.startswith("A-"):
        return storage_cls("conditional", 0.60, "Sandy agricultural")

    logger.warning("[Sandy] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Sandy unknown zone code '{code}' — conservative default")


# ── Washington City ────────────────────────────────────────────────────────────

def classify_washington(code: str) -> PerUseClassification:
    u = code.strip().upper()
    if re.match(r'^R-1-', u) or re.match(r'^RA-', u) or u in ("RRST", "PUD"):
        return storage_cls("prohibited", 0.75, "Washington residential")
    if re.match(r'^A-', u):
        return storage_cls("conditional", 0.65, "Washington agricultural")
    logger.warning("[Washington] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Washington unknown zone code '{code}' — conservative default")


# ── American Fork ──────────────────────────────────────────────────────────────

def classify_american_fork_unmatched(code: str, existing: dict[str, str]) -> PerUseClassification:
    """
    Parcel codes use R1-9000 format; matrix has R-1-9000 or R-1-9,000.
    Normalise the parcel code to match matrix keys.
    """
    u = code.strip()
    normalized = re.sub(r'^R(\d)-', r'R-\1-', u)
    normalized_nocomma = normalized.replace(',', '')

    for key in (normalized, normalized_nocomma):
        if key in existing:
            perm = existing[key]
            return storage_cls(perm, 0.70, f"American Fork normalized match: '{code}' → '{key}'")

    if re.match(r'^R\d-\d+$', u):
        return storage_cls("prohibited", 0.72, "American Fork unmatched residential code")

    logger.warning("[American Fork] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"American Fork unknown zone code '{code}' — conservative default")


# ── Bluffdale ──────────────────────────────────────────────────────────────────

def classify_bluffdale(code: str) -> PerUseClassification:
    u = code.strip().upper()

    # Permitted — confirmed industrial/commercial storage zones
    if any(kw in u for kw in ('I-1', 'LIGHT INDUSTR', 'HEAVY COMMERCIAL', 'SG-1',
                               'COMMERCIAL STORAGE', 'DR DESTINATION')):
        return storage_cls("permitted", 0.78, f"Bluffdale industrial/storage zone: {code}")

    # Prohibited — residential zones (including Mixed Use which is residential-oriented)
    if any(kw in u for kw in ('MIXED USE', 'R-MF MULTIFAMILY', 'R-1-43', 'R-SL',
                               'UNDESIGNATED')):
        return storage_cls("prohibited", 0.78, f"Bluffdale residential/MU zone: {code}")

    # Prohibited — civic/institutional
    if any(kw in u for kw in ('CI CIVIC', 'CIVIC')):
        return storage_cls("prohibited", 0.75, f"Bluffdale civic zone: {code}")

    # Conditional — commercial/flex zones
    if any(kw in u for kw in ('GC-1', 'SD-X', 'SD-C', 'GW-R GATEWAY',
                               'REGIONAL COMMERCIAL', 'NC NEIGHBORHOOD', 'I-O INFILL',
                               'A-5 AGRICULTURAL', 'SD-R')):
        return storage_cls("conditional", 0.65, f"Bluffdale commercial/flex zone: {code}")

    # Conditional — special districts (could accommodate storage with CUP)
    if u.startswith('SD-'):
        return storage_cls("conditional", 0.60, f"Bluffdale special district: {code}")

    logger.warning("[Bluffdale] Unknown code '%s' — prohibited (conservative default)", code)
    return storage_cls("prohibited", 0.45, f"Bluffdale unknown zone code '{code}' — conservative default")


# ── Draper (compound codes) ────────────────────────────────────────────────────

def classify_draper_compound(code: str, existing: dict[str, str]) -> PerUseClassification:
    """
    Compound codes like 'C-3; RM' — take the most commercially permissive component.
    """
    parts = [p.strip() for p in code.split(';')]
    classifications = [existing.get(p) for p in parts if existing.get(p)]
    if 'permitted' in classifications:
        return storage_cls("permitted", 0.70, f"Draper compound zone (most permissive): {code}")
    if 'conditional' in classifications:
        return storage_cls("conditional", 0.65, f"Draper compound zone (most permissive): {code}")
    return storage_cls("prohibited", 0.70, f"Draper compound zone: {code}")


# ── Runner ─────────────────────────────────────────────────────────────────────

async def insert_new_codes(jur_id: str, name: str, new_entries: dict[str, PerUseClassification]) -> None:
    """Insert new zone_use_matrix rows, writing all 4 use columns + classification_source."""
    if not new_entries:
        logger.info("[%s] Nothing to insert", name)
        return
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        for zone_code, cls in new_entries.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name,
                     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                     classification_source, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, :mw, :li, :lgc, 'rule', :conf, :notes)
                ON CONFLICT (jurisdiction_id, zone_code) DO NOTHING
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
    logger.info("[%s] Inserted %d new rows", name, len(new_entries))
    await engine.dispose()


async def main() -> None:
    # ── Sandy ──────────────────────────────────────────────────────────────────
    SANDY = "0cf50881-fdf3-4149-8c9f-6db758c4a08f"
    sandy_unmatched = get_unmatched_codes(SANDY)
    logger.info("[Sandy] %d unmatched codes", len(sandy_unmatched))
    sandy_new = {code: classify_sandy(code) for code in sandy_unmatched}
    counts: dict[str, int] = {}
    for v in sandy_new.values():
        counts[v.self_storage] = counts.get(v.self_storage, 0) + 1
    logger.info("[Sandy] Distribution: %s", counts)
    await insert_new_codes(SANDY, "Sandy", sandy_new)

    # ── Washington City ────────────────────────────────────────────────────────
    WASHINGTON = "cad6d22f-7447-4a26-8385-587e93f7f340"
    wash_unmatched = get_unmatched_codes(WASHINGTON)
    logger.info("[Washington] %d unmatched codes", len(wash_unmatched))
    wash_new = {code: classify_washington(code) for code in wash_unmatched}
    await insert_new_codes(WASHINGTON, "Washington", wash_new)

    # ── American Fork ──────────────────────────────────────────────────────────
    AF = "d3757bf8-b4f1-4142-bece-8c774c863955"
    af_unmatched = get_unmatched_codes(AF)
    af_existing = get_existing_matrix(AF)
    logger.info("[American Fork] %d unmatched codes", len(af_unmatched))
    af_new = {code: classify_american_fork_unmatched(code, af_existing) for code in af_unmatched}
    await insert_new_codes(AF, "American Fork", af_new)

    # ── Bluffdale ──────────────────────────────────────────────────────────────
    BLUFFDALE = "cb5017c6-a845-4ffd-91a3-7dc26e2e5ce9"
    bluff_unmatched = get_unmatched_codes(BLUFFDALE)
    logger.info("[Bluffdale] %d unmatched codes", len(bluff_unmatched))
    bluff_new = {code: classify_bluffdale(code) for code in bluff_unmatched}
    await insert_new_codes(BLUFFDALE, "Bluffdale", bluff_new)

    # ── Draper ─────────────────────────────────────────────────────────────────
    DRAPER = "6e618f70-ae79-4d2d-8548-fda3ea21823a"
    draper_unmatched = get_unmatched_codes(DRAPER)
    draper_existing = get_existing_matrix(DRAPER)
    logger.info("[Draper] %d unmatched codes", len(draper_unmatched))
    draper_new = {code: classify_draper_compound(code, draper_existing) for code in draper_unmatched}
    await insert_new_codes(DRAPER, "Draper", draper_new)

    # ── Final match rates ──────────────────────────────────────────────────────
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT j.name,
               COUNT(p.id) AS total,
               COUNT(z.zone_code) AS matched,
               ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(p.id), 0), 1) AS pct
        FROM jurisdictions j
        JOIN parcels p ON p.jurisdiction_id = j.id
        LEFT JOIN zone_use_matrix z ON z.jurisdiction_id = j.id AND z.zone_code = p.zoning_code
        WHERE j.name IN ('Sandy', 'Washington', 'American Fork', 'Bluffdale', 'Draper City, UT')
        GROUP BY j.name
        ORDER BY pct DESC
    """)
    logger.info("Updated match rates:")
    for row in cur.fetchall():
        logger.info("  %-25s %6d/%d = %s%%", row[0], row[2], row[1], row[3])
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
