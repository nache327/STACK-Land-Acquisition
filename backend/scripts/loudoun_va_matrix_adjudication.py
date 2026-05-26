"""Adjudicate Loudoun County, VA remaining unclear matrix rows.

Run from backend/:
    python scripts/loudoun_va_matrix_adjudication.py --dry-run
    python scripts/loudoun_va_matrix_adjudication.py --apply

Only ordinance-cited rows are classified. TOWNS and PUD-1 are reviewed but
intentionally left unclear because the current rows require separate local
zoning or case-specific PUD review.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings

Permission = Literal["permitted", "conditional", "prohibited", "unclear"]

LOUDOUN_JURISDICTION_ID = "8ebaf814-11f9-4e18-89de-d8b947660174"

LOUDOUN_ZONING_URL = "https://www.loudoun.gov/zoningordinance"
LOUDOUN_1972_URL = (
    "https://www.loudoun.gov/DocumentCenter/View/99543/"
    "Complete_1972_Loudoun_County_Zoning_Ordinance?bidId="
)
LOUDOUN_PUD_URL = (
    "https://www.loudoun.gov/5954/"
    "Zoning-Ordinance-Rewrite-Change-Highligh"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Adjudication:
    zone_code: str
    self_storage: Permission
    mini_warehouse: Permission
    light_industrial: Permission
    luxury_garage_condo: Permission
    confidence: float
    notes: str
    citations: list[dict[str, str]]


ADJUDICATIONS: dict[str, Adjudication] = {
    "TOWNS": Adjudication(
        zone_code="TOWNS",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.5,
        notes=(
            "Incorporated towns are outside the county zoning ordinance; "
            "town zoning must be reviewed separately. Leaving unclear rather "
            "than treating out-of-scope town parcels as county-prohibited."
        ),
        citations=[
            {
                "section": "Loudoun County Zoning Ordinance page",
                "quote": (
                    "The Zoning Ordinance does not apply to properties within "
                    "the seven incorporated towns."
                ),
                "url": LOUDOUN_ZONING_URL,
            }
        ],
    ),
    "C1": Adjudication(
        zone_code="C1",
        self_storage="conditional",
        mini_warehouse="conditional",
        light_industrial="conditional",
        luxury_garage_condo="conditional",
        confidence=0.8,
        notes=(
            "Legacy 1972 C-1 commercial district allows indoor storage/"
            "warehousing by special exception; classify storage uses as "
            "conditional."
        ),
        citations=[
            {
                "section": "1972 Loudoun Zoning Ordinance, C-1 district",
                "quote": "Warehousing indoor storage.",
                "url": LOUDOUN_1972_URL,
            },
            {
                "section": "1972 Loudoun Zoning Ordinance, C-1 district",
                "quote": "Special Exception Permissible by Board of Zoning Appeals.",
                "url": LOUDOUN_1972_URL,
            },
        ],
    ),
    "PDCH": Adjudication(
        zone_code="PDCH",
        self_storage="conditional",
        mini_warehouse="conditional",
        light_industrial="conditional",
        luxury_garage_condo="conditional",
        confidence=0.75,
        notes=(
            "Legacy PD-CH is planned highway commercial with site-plan and "
            "Board approval context; storage-type uses require case review."
        ),
        citations=[
            {
                "section": "1972 Loudoun Zoning Ordinance § 710.1",
                "quote": (
                    "PD-CH is created to permit a broad range of "
                    "highway-related commercial activities."
                ),
                "url": LOUDOUN_1972_URL,
            },
            {
                "section": "1972 Loudoun Zoning Ordinance § 710",
                "quote": (
                    "Site development plans and reports by the Planning "
                    "Commission are required for planned developments."
                ),
                "url": LOUDOUN_1972_URL,
            },
        ],
    ),
    "PUD": Adjudication(
        zone_code="PUD",
        self_storage="conditional",
        mini_warehouse="conditional",
        light_industrial="conditional",
        luxury_garage_condo="conditional",
        confidence=0.75,
        notes=(
            "PUD is fully customizable and plan-specific; storage verdicts "
            "require approved PUD plan review."
        ),
        citations=[
            {
                "section": "Loudoun Zoning Ordinance Rewrite, Planned Unit Development",
                "quote": (
                    "The PUD district allows for an innovative, fully "
                    "customizable proposal."
                ),
                "url": LOUDOUN_PUD_URL,
            },
            {
                "section": "Loudoun Zoning Ordinance Rewrite, New Unmapped Zoning Districts",
                "quote": (
                    "New districts are not yet mapped and will only be mapped "
                    "upon approval of a rezoning application."
                ),
                "url": LOUDOUN_PUD_URL,
            },
        ],
    ),
    "PUD-1": Adjudication(
        zone_code="PUD-1",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.5,
        notes=(
            "Reviewed in cleanup pass. PUD-1 appears to be a local PUD "
            "variant, but no direct ordinance citation was verified; leaving "
            "all use columns unclear."
        ),
        citations=[],
    ),
}


def _database_url(override: str | None) -> str:
    if override:
        if override.startswith("postgresql://"):
            return "postgresql+asyncpg://" + override[len("postgresql://") :]
        if override.startswith("postgres://"):
            return "postgresql+asyncpg://" + override[len("postgres://") :]
        return override
    return Settings().database_url


async def fetch_current_counts(conn) -> list[dict]:
    result = await conn.execute(
        text(
            """
            SELECT
                z.zone_code,
                z.self_storage,
                z.mini_warehouse,
                z.light_industrial,
                z.luxury_garage_condo,
                z.classification_source,
                z.human_reviewed,
                COUNT(p.id)::int AS parcel_count
            FROM zone_use_matrix z
            LEFT JOIN parcels p
              ON p.jurisdiction_id = z.jurisdiction_id
             AND p.zoning_code = z.zone_code
            WHERE z.jurisdiction_id = :jurisdiction_id
              AND z.deleted_at IS NULL
              AND z.zone_code = ANY(:zone_codes)
            GROUP BY
                z.zone_code,
                z.self_storage,
                z.mini_warehouse,
                z.light_industrial,
                z.luxury_garage_condo,
                z.classification_source,
                z.human_reviewed
            ORDER BY z.zone_code
            """
        ),
        {
            "jurisdiction_id": LOUDOUN_JURISDICTION_ID,
            "zone_codes": list(ADJUDICATIONS),
        },
    )
    return [dict(row._mapping) for row in result]


async def apply_adjudication(conn, item: Adjudication) -> int:
    stmt = text(
        """
        UPDATE zone_use_matrix
        SET
            self_storage = :self_storage,
            mini_warehouse = :mini_warehouse,
            light_industrial = :light_industrial,
            luxury_garage_condo = :luxury_garage_condo,
            classification_source = 'human',
            confidence = :confidence,
            human_reviewed = TRUE,
            notes = :notes,
            citations = :citations,
            updated_at = now()
        WHERE jurisdiction_id = :jurisdiction_id
          AND deleted_at IS NULL
          AND zone_code = :zone_code
        """
    ).bindparams(bindparam("citations", type_=JSONB))
    result = await conn.execute(
        stmt,
        {
            "jurisdiction_id": LOUDOUN_JURISDICTION_ID,
            "zone_code": item.zone_code,
            "self_storage": item.self_storage,
            "mini_warehouse": item.mini_warehouse,
            "light_industrial": item.light_industrial,
            "luxury_garage_condo": item.luxury_garage_condo,
            "confidence": item.confidence,
            "notes": item.notes,
            "citations": item.citations,
        },
    )
    return result.rowcount or 0


def summarize(rows: list[dict]) -> tuple[int, int]:
    moved = 0
    matched = {row["zone_code"] for row in rows}
    missing = set(ADJUDICATIONS) - matched
    if missing:
        raise RuntimeError(f"Missing expected Loudoun rows: {sorted(missing)}")

    for row in rows:
        item = ADJUDICATIONS[row["zone_code"]]
        was_unclear = row["self_storage"] == "unclear"
        becomes_classified = item.self_storage != "unclear"
        if was_unclear and becomes_classified:
            moved += int(row["parcel_count"])
        logger.info(
            "%-6s parcels=%5d %s/%s/%s/%s -> %s/%s/%s/%s",
            row["zone_code"],
            row["parcel_count"],
            row["self_storage"],
            row["mini_warehouse"],
            row["light_industrial"],
            row["luxury_garage_condo"],
            item.self_storage,
            item.mini_warehouse,
            item.light_industrial,
            item.luxury_garage_condo,
        )
    return len(rows), moved


async def main() -> int:
    parser = argparse.ArgumentParser(description="Adjudicate Loudoun VA matrix tail")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    args = parser.parse_args()

    engine = create_async_engine(_database_url(args.database_url))
    try:
        async with engine.begin() as conn:
            rows = await fetch_current_counts(conn)
            row_count, moved = summarize(rows)
            logger.info(
                "Expected parcels moved from unclear to classified: %d across %d rows",
                moved,
                row_count,
            )
            logger.info(
                "Citations:\n%s",
                json.dumps({k: v.citations for k, v in ADJUDICATIONS.items()}, indent=2),
            )
            if args.dry_run:
                logger.info("Dry run only; no rows updated.")
                return 0

            updated = 0
            for item in ADJUDICATIONS.values():
                updated += await apply_adjudication(conn, item)
            logger.info("Updated %d Loudoun zone_use_matrix rows", updated)
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
