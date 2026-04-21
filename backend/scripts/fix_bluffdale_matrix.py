"""
Phase 1 immediate DB fix:

1. Bluffdale MU zone: "Mixed Use" row was classified as conditional by the
   rule-based fallback. Bluffdale's MU district is residential-oriented
   (live/work, retail, office) — self-storage and warehousing are not
   permitted or conditional uses. Fix: prohibited.

2. Bluffdale R-MF zone: "R-MF Multifamily" row was classified as conditional.
   Multifamily residential zones do not permit storage uses. Fix: prohibited.

3. Other cities with risky MU/residential-coded conditional rows found by
   audit query: Eagle Mountain (Mixed-Use Residential/Commercial), Lindon
   (RMU-E, RMU-W), Ogden (Mixed Use). Fix to prohibited pending ordinance
   verification — conservative default applies.

Run from backend/ directory:
    python scripts/fix_bluffdale_matrix.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"

# (jurisdiction_id, zone_code pattern, note)
FIXES: list[tuple[str, str, str, str]] = [
    # Bluffdale
    (
        "cb5017c6-a845-4ffd-91a3-7dc26e2e5ce9",
        "Mixed Use",
        "EXACT",
        "Bluffdale MU is residential-oriented mixed use (live/work, retail, office) — "
        "self-storage not permitted per ordinance. Rule-based fallback misclassified as conditional.",
    ),
    (
        "cb5017c6-a845-4ffd-91a3-7dc26e2e5ce9",
        "R-MF Multifamily",
        "EXACT",
        "Bluffdale R-MF is a multifamily residential zone — storage not compatible. "
        "Rule-based fallback misclassified as conditional.",
    ),
    # Eagle Mountain — Mixed-Use Residential/Commercial: residential qualifier → conservative prohibited
    (
        "1f0d6f93-8e5c-462b-88ed-9d6a9e107bc1",
        "Mixed-Use Residential/Commercial",
        "EXACT",
        "Eagle Mountain Mixed-Use Residential/Commercial: residential qualifier suggests "
        "storage is not a primary use. Corrected to prohibited (conservative) — verify against §EM ordinance.",
    ),
    # Lindon — RMU zones: Residential Mixed Use → prohibited
    (
        "7a8acba7-8ea3-4844-9ab6-12c72d8fbc2c",
        "RMU-E",
        "EXACT",
        "Lindon RMU-E (Residential Mixed Use East) is residential-oriented — "
        "storage not compatible. Corrected to prohibited (conservative).",
    ),
    (
        "7a8acba7-8ea3-4844-9ab6-12c72d8fbc2c",
        "RMU-W",
        "EXACT",
        "Lindon RMU-W (Residential Mixed Use West) is residential-oriented — "
        "storage not compatible. Corrected to prohibited (conservative).",
    ),
    # Ogden — Mixed Use: needs ordinance verification but conservative default applies
    (
        "fe0f482f-da80-4673-b83b-556b0cca7ba4",
        "Mixed Use",
        "EXACT",
        "Ogden Mixed Use: corrected to prohibited (conservative default) — "
        "verify against Ogden City ordinance §MU use table before overriding.",
    ),
]


def run_fixes() -> None:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()

    for jur_id, zone_code, match_type, note in FIXES:
        if match_type == "EXACT":
            cur.execute(
                """
                UPDATE zone_use_matrix
                SET self_storage        = 'prohibited',
                    mini_warehouse      = 'prohibited',
                    luxury_garage_condo = 'prohibited',
                    notes               = %s
                WHERE jurisdiction_id = %s
                  AND zone_code = %s
                  AND human_reviewed = false
                """,
                (note, jur_id, zone_code),
            )
        rows = cur.rowcount
        logger.info("Fixed %d row(s): [%s] zone_code='%s'", rows, jur_id[:8], zone_code)

    conn.commit()

    # Verification query
    cur.execute(
        """
        SELECT j.name, z.zone_code, z.self_storage, z.mini_warehouse, z.luxury_garage_condo
        FROM zone_use_matrix z
        JOIN jurisdictions j ON z.jurisdiction_id = j.id
        WHERE z.self_storage = 'conditional'
          AND (
            z.zone_code ILIKE '%mixed use%'
            OR z.zone_code ILIKE '%multifamily%'
            OR z.zone_code ILIKE 'r-mf%'
            OR z.zone_code ILIKE 'rmu%'
          )
        ORDER BY j.name, z.zone_code
        """
    )
    remaining = cur.fetchall()
    if remaining:
        logger.warning("REMAINING risky conditional rows after fix (%d):", len(remaining))
        for r in remaining:
            logger.warning("  %s | %s | ss=%s mw=%s lgc=%s", r[0], r[1], r[2], r[3], r[4])
    else:
        logger.info("All targeted risky rows corrected.")

    conn.close()


if __name__ == "__main__":
    run_fixes()
