"""
Backfill mini_warehouse, light_industrial, and luxury_garage_condo columns for
existing zone_use_matrix rows where those columns are still 'unclear'.

These rows were inserted before the PerUseClassification refactor and only have
self_storage populated correctly. This script applies the same inference rules
used by the live code (storage_cls + apply_luxury_garage_inference) to fill in
the missing columns.

Only updates rows where:
  - classification_source = 'rule'   (rule-based, not LLM-parsed or human)
  - human_reviewed = false
  - mini_warehouse = 'unclear'       (incomplete write from pre-refactor code)

Run from backend/ directory:
    python scripts/backfill_zone_matrix_uses.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2

from scripts._db import get_sync_dsn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_SYNC = get_sync_dsn()


def infer_luxury_garage(ss: str, mw: str, li: str) -> str:
    """Mirror of apply_luxury_garage_inference() for direct SQL backfill."""
    if mw == "permitted" or ss == "permitted":
        return "permitted"
    if mw == "conditional" or ss == "conditional":
        return "conditional"
    if li in ("permitted", "conditional"):
        return "conditional"
    return "prohibited"


def run_backfill(dry_run: bool) -> int:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, self_storage, mini_warehouse, light_industrial, luxury_garage_condo
        FROM zone_use_matrix
        WHERE classification_source = 'rule'
          AND human_reviewed = false
          AND mini_warehouse = 'unclear'
    """)
    rows = cur.fetchall()
    logger.info("Found %d rows needing backfill", len(rows))

    updated = 0
    for row_id, ss, mw, li, lgc in rows:
        # mini_warehouse and light_industrial mirror self_storage for rule-based rows
        new_mw = ss if mw == "unclear" else mw
        new_li = ss if li == "unclear" else li
        new_lgc = infer_luxury_garage(ss, new_mw, new_li) if lgc == "unclear" else lgc

        if dry_run:
            logger.info(
                "DRY RUN id=%d  ss=%-12s  mw: %s→%-12s  li: %s→%-12s  lgc: %s→%s",
                row_id, ss, mw, new_mw, li, new_li, lgc, new_lgc,
            )
        else:
            cur.execute("""
                UPDATE zone_use_matrix
                SET mini_warehouse      = %s,
                    light_industrial    = %s,
                    luxury_garage_condo = %s
                WHERE id = %s
            """, (new_mw, new_li, new_lgc, row_id))
        updated += 1

    if not dry_run:
        conn.commit()
        logger.info("Committed %d row updates", updated)
    else:
        logger.info("Dry run complete — %d rows would be updated", updated)

    conn.close()
    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill zone_use_matrix use columns")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing to DB")
    args = parser.parse_args()

    count = run_backfill(dry_run=args.dry_run)
    sys.exit(0 if count == 0 else 0)  # always exit 0 — row count is informational
