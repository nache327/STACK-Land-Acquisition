"""Review Howard County, MD remaining unclear matrix rows.

Run from backend/:
    python scripts/howard_md_unclear_cleanup_matrix_adjudication.py --dry-run
    python scripts/howard_md_unclear_cleanup_matrix_adjudication.py --apply

This cleanup intentionally leaves OT and 2R0 unclear. No direct ordinance
citation was verified for either code, so the honest action is to mark the
review result without manufacturing a classification.
"""
from __future__ import annotations

import argparse
import asyncio
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

HOWARD_JURISDICTION_ID = "dc2d9d42-aa78-45e3-8c85-970e69a30240"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Review:
    zone_code: str
    self_storage: Permission
    mini_warehouse: Permission
    light_industrial: Permission
    luxury_garage_condo: Permission
    confidence: float
    notes: str
    citations: list[dict[str, str]]


REVIEWS: dict[str, Review] = {
    "2R0": Review(
        zone_code="2R0",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.35,
        notes=(
            "Reviewed in Howard cleanup pass. 2R0 appears to be a data-quality "
            "or OCR anomaly; no direct ordinance citation verified. Leaving "
            "unclear."
        ),
        citations=[],
    ),
    "OT": Review(
        zone_code="OT",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.35,
        notes=(
            "Reviewed in Howard cleanup pass. OT definition not verified "
            "against current Howard County zoning regulations. Leaving unclear."
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
            "jurisdiction_id": HOWARD_JURISDICTION_ID,
            "zone_codes": list(REVIEWS),
        },
    )
    return [dict(row._mapping) for row in result]


async def apply_review(conn, item: Review) -> int:
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
            "jurisdiction_id": HOWARD_JURISDICTION_ID,
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
    missing = set(REVIEWS) - matched
    if missing:
        raise RuntimeError(f"Missing expected Howard rows: {sorted(missing)}")

    for row in rows:
        item = REVIEWS[row["zone_code"]]
        if row["self_storage"] == "unclear" and item.self_storage != "unclear":
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
    parser = argparse.ArgumentParser(description="Review Howard MD matrix tail")
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
            if args.dry_run:
                logger.info("Dry run only; no rows updated.")
                return 0

            updated = 0
            for item in REVIEWS.values():
                updated += await apply_review(conn, item)
            logger.info("Updated %d Howard zone_use_matrix rows", updated)
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
