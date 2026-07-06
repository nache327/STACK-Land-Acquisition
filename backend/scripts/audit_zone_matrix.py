"""
Audit zone_use_matrix for high-risk rows that may be misclassified.

Produces a CSV of rows matching any risk criterion, for human analyst review.

Run from backend/ directory:
    python scripts/audit_zone_matrix.py [--output zone_matrix_audit.csv]
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2

from scripts._db import get_sync_dsn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

DB_SYNC = get_sync_dsn()

RISK_CRITERIA = [
    ("conditional_mixed_use",
     "self_storage = 'conditional' AND (z.zone_code ILIKE '%mixed use%' OR z.zone_code ILIKE '%mixed-use%')"),
    ("conditional_multifamily",
     "self_storage = 'conditional' AND z.zone_code ILIKE '%multifamily%'"),
    ("conditional_rmu",
     "self_storage = 'conditional' AND (z.zone_code ILIKE 'rmu%' OR z.zone_code ILIKE 'r-mu%')"),
    ("conditional_residential",
     "self_storage = 'conditional' AND (z.zone_code ILIKE 'r-mf%' OR z.zone_code ILIKE 'rmf%')"),
    ("unclear_mini_warehouse",
     "mini_warehouse = 'unclear'"),
    ("unclear_luxury_garage",
     "luxury_garage_condo = 'unclear'"),
    ("low_confidence_rule",
     "classification_source = 'rule' AND confidence < 0.65"),
]


def run_audit(output_path: str) -> int:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()

    all_rows: list[dict] = []
    seen_ids: set[int] = set()

    for criterion_name, where_clause in RISK_CRITERIA:
        cur.execute(f"""
            SELECT z.id, j.name AS city, z.zone_code, z.zone_name,
                   z.self_storage, z.mini_warehouse, z.light_industrial,
                   z.luxury_garage_condo, z.classification_source,
                   z.confidence, z.human_reviewed, z.notes
            FROM zone_use_matrix z
            JOIN jurisdictions j ON z.jurisdiction_id = j.id
            WHERE {where_clause}
            ORDER BY j.name, z.zone_code
        """)
        rows = cur.fetchall()
        logger.info("[%s] %d rows", criterion_name, len(rows))
        for row in rows:
            row_id = row[0]
            if row_id not in seen_ids:
                seen_ids.add(row_id)
                all_rows.append({
                    "id": row[0],
                    "city": row[1],
                    "zone_code": row[2],
                    "zone_name": row[3],
                    "self_storage": row[4],
                    "mini_warehouse": row[5],
                    "light_industrial": row[6],
                    "luxury_garage_condo": row[7],
                    "classification_source": row[8],
                    "confidence": row[9],
                    "human_reviewed": row[10],
                    "notes": row[11],
                    "risk_criterion": criterion_name,
                })

    conn.close()

    if not all_rows:
        logger.info("No risky rows found — matrix looks clean.")
        return 0

    fieldnames = ["id", "city", "zone_code", "zone_name", "self_storage",
                  "mini_warehouse", "light_industrial", "luxury_garage_condo",
                  "classification_source", "confidence", "human_reviewed",
                  "notes", "risk_criterion"]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    logger.info("Wrote %d risky rows to %s", len(all_rows), output_path)
    return len(all_rows)


def print_summary() -> None:
    conn = psycopg2.connect(DB_SYNC)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            classification_source,
            COUNT(*) AS total,
            SUM(CASE WHEN self_storage = 'conditional' THEN 1 ELSE 0 END) AS conditional,
            SUM(CASE WHEN self_storage = 'permitted'   THEN 1 ELSE 0 END) AS permitted,
            SUM(CASE WHEN self_storage = 'prohibited'  THEN 1 ELSE 0 END) AS prohibited,
            SUM(CASE WHEN self_storage = 'unclear'     THEN 1 ELSE 0 END) AS unclear
        FROM zone_use_matrix
        GROUP BY classification_source
        ORDER BY classification_source
    """)
    logger.info("Zone matrix summary by source:")
    for row in cur.fetchall():
        logger.info("  %-10s total=%-5d conditional=%-4d permitted=%-4d prohibited=%-4d unclear=%d",
                    row[0], row[1], row[2], row[3], row[4], row[5])

    cur.execute("""
        SELECT COUNT(*) FROM zone_use_matrix WHERE mini_warehouse = 'unclear'
    """)
    unclear_mw = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM zone_use_matrix WHERE luxury_garage_condo = 'unclear'
    """)
    unclear_lgc = cur.fetchone()[0]
    logger.info("Incomplete rows: mini_warehouse=unclear: %d, luxury_garage_condo=unclear: %d",
                unclear_mw, unclear_lgc)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit zone_use_matrix for risky rows")
    parser.add_argument(
        "--output", default=f"zone_matrix_audit_{date.today().isoformat()}.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    print_summary()
    count = run_audit(args.output)
    sys.exit(0 if count == 0 else 1)
