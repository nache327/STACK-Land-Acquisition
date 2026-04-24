"""
Fix systematically misclassified zone_use_matrix rows across all Utah cities.

Corrects six patterns where rule-based classifiers returned 'conditional' for
zones that should be 'prohibited':

  1. Agricultural zones (A-1, A-5, A-10, A-20, A-1-*, etc.)
  2. Sandy PUD(density) — residential planned unit developments
  3. Sandy SD(R*) / SD(OS) / SD(P) — residential/open-space base zones
  4. Taylorsville SSD-R — residential special sub-district
  5. North Salt Lake NOS — Natural Open Space
  6. Bare MU in residential-oriented cities (Herriman, Kaysville, Saratoga Springs,
     Taylorsville, South Jordan MU-R_D)
  7. Eagle Mountain Agriculture descriptor
  8. Millcreek MD (Medium Density residential)

Only updates rows where:
  - classification_source = 'rule'
  - human_reviewed = false
  - self_storage = 'conditional'  (the rows we know are wrong)

Run from backend/ directory:
    python scripts/fix_misclassified_zones.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_SYNC = "host=aws-1-us-east-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.bbvywbpxwsoyvdvygvyw password=Teczmn3027$"

FIXES = [
    # ── 1. Agricultural zones ─────────────────────────────────────────────────
    # A-1, A-5, A-10, A-20, A-1-10, A-1-21, A-1-43, A-2, Agriculture (text)
    (
        "agricultural_zones",
        """
        UPDATE zone_use_matrix z
        SET self_storage        = 'prohibited',
            mini_warehouse      = 'prohibited',
            light_industrial    = 'prohibited',
            luxury_garage_condo = 'prohibited',
            notes = 'Agricultural zone — storage prohibited (conservative default)'
        WHERE z.classification_source = 'rule'
          AND z.human_reviewed = false
          AND z.self_storage = 'conditional'
          AND (
            z.zone_code ~ '^A-[0-9]'
            OR z.zone_code ILIKE 'Agriculture%'
            OR z.zone_code ILIKE '% Agricultural%'
          )
        RETURNING z.id, z.zone_code,
                  (SELECT name FROM jurisdictions WHERE id = z.jurisdiction_id) AS city
        """,
    ),

    # ── 2. Sandy PUD(density) — residential planned unit developments ─────────
    (
        "sandy_pud_residential",
        """
        UPDATE zone_use_matrix z
        SET self_storage        = 'prohibited',
            mini_warehouse      = 'prohibited',
            light_industrial    = 'prohibited',
            luxury_garage_condo = 'prohibited',
            notes = 'Sandy PUD: residential planned unit development — storage prohibited'
        FROM jurisdictions j
        WHERE z.jurisdiction_id = j.id
          AND j.name = 'Sandy'
          AND z.classification_source = 'rule'
          AND z.human_reviewed = false
          AND z.self_storage = 'conditional'
          AND z.zone_code ~ '^PUD[\\s(0-9]'
        RETURNING z.id, z.zone_code, j.name AS city
        """,
    ),

    # ── 3. Sandy SD with residential / open-space base zones ─────────────────
    # SD(R), SD(R2.0), SD(R2.3), SD(OS), SD(P), SD(PO/R [...R...]) variants
    (
        "sandy_sd_residential",
        """
        UPDATE zone_use_matrix z
        SET self_storage        = 'prohibited',
            mini_warehouse      = 'prohibited',
            light_industrial    = 'prohibited',
            luxury_garage_condo = 'prohibited',
            notes = 'Sandy SD with residential/open-space base zone — storage prohibited'
        FROM jurisdictions j
        WHERE z.jurisdiction_id = j.id
          AND j.name = 'Sandy'
          AND z.classification_source = 'rule'
          AND z.human_reviewed = false
          AND z.self_storage = 'conditional'
          AND (
            z.zone_code ~ '^SD[(]R'           -- SD(R), SD(R2.0), SD(R2.3)
            OR z.zone_code ~ 'PO/R [(]R'     -- SD(PO/R [R-1-8]) etc.
            OR z.zone_code = 'SD(OS)'
            OR z.zone_code = 'SD(P)'
          )
        RETURNING z.id, z.zone_code, j.name AS city
        """,
    ),

    # ── 4. Taylorsville SSD-R — residential special sub-district ─────────────
    (
        "taylorsville_ssd_r",
        """
        UPDATE zone_use_matrix z
        SET self_storage        = 'prohibited',
            mini_warehouse      = 'prohibited',
            light_industrial    = 'prohibited',
            luxury_garage_condo = 'prohibited',
            notes = 'Taylorsville SSD-R: residential special sub-district — storage prohibited'
        FROM jurisdictions j
        WHERE z.jurisdiction_id = j.id
          AND j.name = 'Taylorsville'
          AND z.classification_source = 'rule'
          AND z.human_reviewed = false
          AND z.zone_code ILIKE 'SSD-R%'
        RETURNING z.id, z.zone_code, j.name AS city
        """,
    ),

    # ── 5. North Salt Lake NOS — Natural Open Space ───────────────────────────
    (
        "nsl_nos",
        """
        UPDATE zone_use_matrix z
        SET self_storage        = 'prohibited',
            mini_warehouse      = 'prohibited',
            light_industrial    = 'prohibited',
            luxury_garage_condo = 'prohibited',
            notes = 'Natural Open Space zone — storage prohibited'
        FROM jurisdictions j
        WHERE z.jurisdiction_id = j.id
          AND j.name = 'North Salt Lake'
          AND z.classification_source = 'rule'
          AND z.human_reviewed = false
          AND z.zone_code = 'NOS'
        RETURNING z.id, z.zone_code, j.name AS city
        """,
    ),

    # ── 6. Bare MU / residential-oriented MU ─────────────────────────────────
    # Herriman MU / MU-2, Kaysville MU, Saratoga Springs MU, Taylorsville MU,
    # South Jordan MU-R_D (explicitly residential)
    (
        "residential_mu",
        """
        UPDATE zone_use_matrix z
        SET self_storage        = 'prohibited',
            mini_warehouse      = 'prohibited',
            light_industrial    = 'prohibited',
            luxury_garage_condo = 'prohibited',
            notes = 'Residential-oriented mixed use — storage prohibited (conservative default)'
        FROM jurisdictions j
        WHERE z.jurisdiction_id = j.id
          AND j.name IN ('Herriman', 'Kaysville', 'Saratoga Springs', 'Taylorsville', 'South Jordan')
          AND z.classification_source = 'rule'
          AND z.human_reviewed = false
          AND z.self_storage = 'conditional'
          AND (
            z.zone_code = 'MU'
            OR z.zone_code = 'MU-2'
            OR z.zone_code ILIKE 'MU-R%'
          )
        RETURNING z.id, z.zone_code, j.name AS city
        """,
    ),

    # ── 7. Eagle Mountain Agriculture descriptor ──────────────────────────────
    (
        "eagle_mountain_agriculture",
        """
        UPDATE zone_use_matrix z
        SET self_storage        = 'prohibited',
            mini_warehouse      = 'prohibited',
            light_industrial    = 'prohibited',
            luxury_garage_condo = 'prohibited',
            notes = 'Eagle Mountain agricultural zone — storage prohibited'
        FROM jurisdictions j
        WHERE z.jurisdiction_id = j.id
          AND j.name = 'Eagle Mountain'
          AND z.classification_source = 'rule'
          AND z.human_reviewed = false
          AND z.self_storage = 'conditional'
          AND z.zone_code ILIKE 'Agriculture%'
        RETURNING z.id, z.zone_code, j.name AS city
        """,
    ),

    # ── 8. Millcreek MD — Medium Density residential ──────────────────────────
    (
        "millcreek_md_residential",
        """
        UPDATE zone_use_matrix z
        SET self_storage        = 'prohibited',
            mini_warehouse      = 'prohibited',
            light_industrial    = 'prohibited',
            luxury_garage_condo = 'prohibited',
            notes = 'Millcreek MD: medium density residential — storage prohibited'
        FROM jurisdictions j
        WHERE z.jurisdiction_id = j.id
          AND j.name = 'Millcreek'
          AND z.classification_source = 'rule'
          AND z.human_reviewed = false
          AND z.self_storage = 'conditional'
          AND z.zone_code ILIKE 'MD%'
        RETURNING z.id, z.zone_code, j.name AS city
        """,
    ),
]


def run_fixes(dry_run: bool) -> dict[str, int]:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    counts: dict[str, int] = {}

    for name, sql in FIXES:
        if dry_run:
            preview_sql = sql.replace(
                "UPDATE zone_use_matrix z\n        SET",
                "SELECT z.id, z.zone_code,"
            ).split("RETURNING")[0]
            # Just count how many rows would be affected
            count_sql = f"SELECT COUNT(*) FROM ({sql.split('RETURNING')[0].replace('UPDATE zone_use_matrix z', 'UPDATE zone_use_matrix z').split('SET')[0].strip()}) x"
            # Simpler: replace UPDATE...SET...WHERE with SELECT COUNT(*) WHERE
            where_part = sql.split("WHERE", 1)[1].split("RETURNING")[0]
            cur.execute(f"""
                SELECT COUNT(*) FROM zone_use_matrix z
                JOIN jurisdictions j ON z.jurisdiction_id = j.id
                WHERE {where_part}
            """)
            count = cur.fetchone()[0]
            logger.info("[DRY RUN] %-35s would update %d rows", name, count)
            counts[name] = count
        else:
            cur.execute(sql)
            rows = cur.fetchall()
            count = len(rows)
            for row in rows:
                logger.info("  fixed: %-20s %s", row[2], row[1])
            logger.info("[%s] updated %d rows", name, count)
            counts[name] = count

    if not dry_run:
        conn.commit()
        total = sum(counts.values())
        logger.info("Committed — %d total rows fixed", total)
    else:
        total = sum(counts.values())
        logger.info("Dry run complete — %d rows would be fixed", total)

    conn.close()
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix misclassified conditional zones across all cities")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing to DB")
    args = parser.parse_args()

    run_fixes(dry_run=args.dry_run)
