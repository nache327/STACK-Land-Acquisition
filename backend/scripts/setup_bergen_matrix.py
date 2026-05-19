"""
Bootstrap zone_use_matrix for Bergen County, NJ via the heuristic
zone-class classifier in matrix_bootstrap.bootstrap_zone_use_matrix.

Rationale: Bergen has 144+ Paramus zone codes alone, plus the future NJSEA
Meadowlands ingest will add another ~100 codes with town-suffix patterns
(e.g. R1-RU, M1-LYND, LIA, RRR-CARL). Explicit-zone enumeration like
setup_philadelphia_matrix.py / setup_nyc_matrix.py is not the right shape for
per-town variant codes. The existing heuristic bootstrap (matrix_bootstrap.py)
classifies each zone via `zone_classifier.classify_zone_code` → ZoneClass →
default UsePermission map.

Output: confidence='heuristic' rows. Operator can later promote specific zones
to confidence='human' via ordinance lookup if needed for high-value buybox
classes.

Run from backend/:
    python scripts/setup_bergen_matrix.py [--replace] [--missing-only]

`--replace`     — wipe existing matrix rows + rebuild
`--missing-only` — default; only add rows for codes not already in matrix
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.db import async_session_maker
from app.services.matrix_bootstrap import bootstrap_zone_use_matrix

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


JURISDICTION_NAME = "Bergen County, NJ"


async def main(replace: bool, missing_only: bool) -> None:
    async with async_session_maker() as db:
        row = await db.execute(
            text("SELECT id, name FROM jurisdictions WHERE name = :name"),
            {"name": JURISDICTION_NAME},
        )
        jur = row.fetchone()
        if not jur:
            logger.error("Jurisdiction %r not found — ingest parcels first.", JURISDICTION_NAME)
            return
        jur_id = jur.id
        logger.info("Jurisdiction ID: %s (%s)", jur_id, jur.name)

        # Pre-flight: how many distinct zone codes exist in parcels + zoning_districts?
        pre = await db.execute(text("""
            SELECT
                (SELECT COUNT(DISTINCT zoning_code) FROM parcels WHERE jurisdiction_id = :jid AND zoning_code IS NOT NULL) AS parcel_codes,
                (SELECT COUNT(DISTINCT zone_code) FROM zoning_districts WHERE jurisdiction_id = :jid) AS district_codes,
                (SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id = :jid) AS matrix_rows_before
        """), {"jid": jur_id})
        p = pre.fetchone()
        logger.info(
            "Pre-flight: %d distinct parcel zoning codes, %d district codes, %d existing matrix rows",
            p.parcel_codes or 0, p.district_codes or 0, p.matrix_rows_before or 0,
        )

        seeded = await bootstrap_zone_use_matrix(
            jur_id,
            db,
            replace=replace,
            missing_only=missing_only,
        )
        await db.commit()
        logger.info("Seeded %d zone_use_matrix rows (replace=%s missing_only=%s)", seeded, replace, missing_only)

        # Post-check
        post = await db.execute(text("""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(*) FILTER (WHERE self_storage = 'permitted')     AS ss_y,
                COUNT(*) FILTER (WHERE self_storage = 'conditional')   AS ss_c,
                COUNT(*) FILTER (WHERE self_storage = 'prohibited')    AS ss_n,
                COUNT(*) FILTER (WHERE self_storage = 'unclear')       AS ss_u
            FROM zone_use_matrix WHERE jurisdiction_id = :jid
        """), {"jid": jur_id})
        r = post.fetchone()
        logger.info(
            "Matrix totals: %d rows | self_storage: Y=%d C=%d N=%d U=%d",
            r.total_rows or 0, r.ss_y or 0, r.ss_c or 0, r.ss_n or 0, r.ss_u or 0,
        )

        # Parcel coverage check
        cov = await db.execute(text("""
            SELECT
                COUNT(*) AS total_parcels,
                COUNT(*) FILTER (WHERE p.zoning_code IS NOT NULL) AS with_code,
                COUNT(*) FILTER (WHERE z.zone_code IS NOT NULL)   AS matched
            FROM parcels p
            LEFT JOIN zone_use_matrix z
                ON z.jurisdiction_id = p.jurisdiction_id AND z.zone_code = p.zoning_code
            WHERE p.jurisdiction_id = :jid
        """), {"jid": jur_id})
        c = cov.fetchone()
        total = c.total_parcels or 0
        with_code = c.with_code or 0
        matched = c.matched or 0
        logger.info(
            "Coverage: total=%d  with_zoning_code=%d  matrix-matched=%d  matrix_match_pct_of_zoned=%.1f",
            total, with_code, matched,
            (100.0 * matched / with_code) if with_code else 0,
        )

        # Show unmatched codes (operator follow-up)
        un = await db.execute(text("""
            SELECT p.zoning_code, COUNT(*) AS n
            FROM parcels p
            LEFT JOIN zone_use_matrix z
                ON z.jurisdiction_id = p.jurisdiction_id AND z.zone_code = p.zoning_code
            WHERE p.jurisdiction_id = :jid
              AND z.zone_code IS NULL
              AND p.zoning_code IS NOT NULL
            GROUP BY p.zoning_code
            ORDER BY n DESC
            LIMIT 15
        """), {"jid": jur_id})
        unmatched = un.fetchall()
        if unmatched:
            logger.info("Top 15 unmatched zoning codes for Bergen:")
            for u in unmatched:
                logger.info("  %-30s %d parcels", u[0], u[1])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--replace", action="store_true", help="wipe existing matrix rows before seeding")
    p.add_argument("--missing-only", action="store_true", default=True, help="only seed codes not already in matrix (default)")
    args = p.parse_args()
    asyncio.run(main(replace=args.replace, missing_only=args.missing_only and not args.replace))
