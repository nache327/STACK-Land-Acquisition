"""Document Highland, UT PD-1 as reviewed but still unclear.

Run from backend/:
    python scripts/highland_ut_matrix_adjudication.py --dry-run
    python scripts/highland_ut_matrix_adjudication.py --apply

Highland PD-1 has parcel bind count, but the citywide Planned Development
district text does not directly authorize self-storage. The adopted PD narrative
is the controlling use regulation, so this row stays unclear until that narrative
is available. Zero-bind unclear rows are intentionally left untouched.
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

HIGHLAND_JURISDICTION_NAME = "Highland, UT"
HIGHLAND_DEVELOPMENT_CODE_URL = (
    "https://www.highlandut.gov/DocumentCenter/View/742/2013-Development-Code"
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


PD_CITATIONS = [
    {
        "section": "Highland City Development Code Article 5, Section 3-510(1)(c)",
        "quote": (
            "All PD Districts may have a mix of residential and non-residential "
            "uses including office, retail, and business park uses."
        ),
        "url": HIGHLAND_DEVELOPMENT_CODE_URL,
    },
    {
        "section": "Highland City Development Code Article 5, Section 3-510(5)",
        "quote": (
            "The PD Narrative, site plan, design standards and any other documents, "
            "exhibits or plans associated with the PD... shall become part of the "
            "regulations governing the use and development of the PD."
        ),
        "url": HIGHLAND_DEVELOPMENT_CODE_URL,
    },
]


ADJUDICATIONS: dict[str, Adjudication] = {
    "PD-1": Adjudication(
        zone_code="PD-1",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.5,
        notes=(
            "Highland Planned Development district requires the adopted PD narrative "
            "to determine allowed uses; no direct self-storage permission found in "
            "the citywide PD district text."
        ),
        citations=PD_CITATIONS,
    )
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
            JOIN jurisdictions j ON j.id = z.jurisdiction_id
            LEFT JOIN parcels p
              ON p.jurisdiction_id = z.jurisdiction_id
             AND p.zoning_code = z.zone_code
            WHERE j.name = :jurisdiction_name
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
            "jurisdiction_name": HIGHLAND_JURISDICTION_NAME,
            "zone_codes": list(ADJUDICATIONS),
        },
    )
    return [dict(row._mapping) for row in result]


async def apply_adjudication(conn, item: Adjudication) -> int:
    stmt = text(
        """
        UPDATE zone_use_matrix z
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
        FROM jurisdictions j
        WHERE j.id = z.jurisdiction_id
          AND j.name = :jurisdiction_name
          AND z.deleted_at IS NULL
          AND z.zone_code = :zone_code
        """
    ).bindparams(bindparam("citations", type_=JSONB))
    result = await conn.execute(
        stmt,
        {
            "jurisdiction_name": HIGHLAND_JURISDICTION_NAME,
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
    matched = {row["zone_code"] for row in rows}
    missing = set(ADJUDICATIONS) - matched
    if missing:
        raise RuntimeError(f"Missing expected Highland rows: {sorted(missing)}")

    moved = 0
    for row in rows:
        item = ADJUDICATIONS[row["zone_code"]]
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
    parser = argparse.ArgumentParser(description="Adjudicate Highland UT PD-1 review row")
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
            logger.info("Updated %d Highland zone_use_matrix rows", updated)
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
