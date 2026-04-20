"""
Fix zone_use_matrix coverage gaps for:
  - Sandy        (PUD/SD variants, large-lot residential)
  - Washington   (14 missing residential/agricultural codes)
  - American Fork (R1- vs R-1- naming mismatch)
  - Bluffdale    (descriptive long-form zone names)
  - Draper       (compound semicolon-separated zone codes)

Only INSERTs new rows — does not touch existing correct entries.

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

def classify_sandy(code: str) -> str:
    u = code.strip()

    # Large-lot single-family residential
    if re.match(r'^R-1-\d+A$', u):
        return "prohibited"

    # Parameterized multi-family residential RM(n)
    if re.match(r'^RM\(\d', u):
        return "prohibited"

    # Parameterized PUD — planned unit developments are mixed use → conditional
    if re.match(r'^PUD[\s(]', u) or re.match(r'^PUD \d', u):
        return "conditional"

    # Named/parameterized special districts — classify by base zone component
    sd_match = re.match(r'^SD\((.+?)\)', u)
    if sd_match:
        inner = sd_match.group(1).upper()
        # Residential base zones → prohibited
        if re.match(r'^R[-\s]', inner) or inner.startswith('RM') or re.match(r'^\d+\.\d+$', inner):
            return "prohibited"
        # Commercial / mixed / office base zones → conditional
        if any(inner.startswith(p) for p in ('CC', 'CN', 'C-', 'MU', 'PO', 'TC', 'SMART', 'FM', 'MAGNA',
                                              'HARADA', 'MDM', 'UNION', 'UN.', 'CARNATION', 'JHS',
                                              '1300', 'EH', 'H', 'P', 'X', 'OS', 'MU', 'C)')):
            return "conditional"
        # Open space → prohibited
        if inner.startswith('OS'):
            return "prohibited"
        # Default SD → conditional
        return "conditional"

    # Agricultural
    if u.startswith("A-"):
        return "conditional"

    # Fallback
    logger.warning("[Sandy] Unknown code '%s' — conditional", code)
    return "conditional"


# ── Washington City ────────────────────────────────────────────────────────────

def classify_washington(code: str) -> str:
    u = code.strip().upper()
    # Residential
    if re.match(r'^R-1-', u) or re.match(r'^RA-', u) or u in ("RRST", "PUD"):
        return "prohibited"
    # Agricultural
    if re.match(r'^A-', u):
        return "conditional"
    # Fallback
    logger.warning("[Washington] Unknown code '%s' — conditional", code)
    return "conditional"


# ── American Fork ──────────────────────────────────────────────────────────────

def classify_american_fork_unmatched(code: str, existing: dict[str, str]) -> str:
    """
    Parcel codes use R1-9000 format; matrix has R-1-9000 or R-1-9,000.
    Normalise the parcel code to match matrix keys.
    """
    u = code.strip()
    # R1- → R-1-
    normalized = re.sub(r'^R(\d)-', r'R-\1-', u)
    # Remove commas in numbers (R-1-9,000 → R-1-9000)
    normalized_nocomma = normalized.replace(',', '')

    if normalized in existing:
        return existing[normalized]
    if normalized_nocomma in existing:
        return existing[normalized_nocomma]

    # All unmatched AF codes are residential → prohibited
    if re.match(r'^R\d-\d+$', u):
        return "prohibited"

    logger.warning("[American Fork] Unknown code '%s' — conditional", code)
    return "conditional"


# ── Bluffdale ──────────────────────────────────────────────────────────────────

def classify_bluffdale(code: str) -> str:
    u = code.strip().upper()

    # Permitted — industrial/commercial storage
    if any(kw in u for kw in ('I-1', 'LIGHT INDUSTR', 'HEAVY COMMERCIAL', 'SG-1',
                               'COMMERCIAL STORAGE', 'DR DESTINATION')):
        return "permitted"

    # Conditional — commercial/mixed/flex
    if any(kw in u for kw in ('MIXED USE', 'GC-1', 'SD-X', 'SD-C', 'GW-R GATEWAY',
                               'REGIONAL COMMERCIAL', 'NC NEIGHBORHOOD', 'I-O INFILL',
                               'A-5 AGRICULTURAL', 'R-MF MULTIFAMILY')):
        return "conditional"

    # Conditional — special districts (could accommodate storage with CUP)
    if u.startswith('SD-'):
        return "conditional"

    # Prohibited — residential, civic, open space
    if any(kw in u for kw in ('R-1-43', 'R-SL', 'CI CIVIC', 'UNDESIGNATED')):
        return "prohibited"

    logger.warning("[Bluffdale] Unknown code '%s' — conditional", code)
    return "conditional"


# ── Draper (compound codes) ────────────────────────────────────────────────────

def classify_draper_compound(code: str, existing: dict[str, str]) -> str:
    """
    Compound codes like 'C-3; RM' — take the most commercially permissive component.
    """
    parts = [p.strip() for p in code.split(';')]
    classifications = [existing.get(p) for p in parts if existing.get(p)]
    if 'permitted' in classifications:
        return 'permitted'
    if 'conditional' in classifications:
        return 'conditional'
    return 'prohibited'


# ── Runner ─────────────────────────────────────────────────────────────────────

async def insert_new_codes(jur_id: str, name: str, new_entries: dict[str, str]) -> None:
    if not new_entries:
        logger.info("[%s] Nothing to insert", name)
        return
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        for zone_code, perm in new_entries.items():
            await conn.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name, self_storage, confidence, notes)
                VALUES (:jid, :zc, :zn, :ss, :conf, :notes)
                ON CONFLICT (jurisdiction_id, zone_code) DO NOTHING
            """), {
                "jid": jur_id,
                "zc": zone_code,
                "zn": zone_code,
                "ss": perm,
                "conf": 0.7,
                "notes": "Rule-based classification for variant/missing zone codes",
            })
    logger.info("[%s] Inserted %d new rows", name, len(new_entries))
    await engine.dispose()


async def main() -> None:
    # ── Sandy ──────────────────────────────────────────────────────────────────
    SANDY = "0cf50881-fdf3-4149-8c9f-6db758c4a08f"
    sandy_unmatched = get_unmatched_codes(SANDY)
    logger.info("[Sandy] %d unmatched codes", len(sandy_unmatched))
    sandy_new = {code: classify_sandy(code) for code in sandy_unmatched}
    counts = {}
    for v in sandy_new.values(): counts[v] = counts.get(v, 0) + 1
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
