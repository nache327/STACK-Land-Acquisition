"""Adjudicate defensible Middlesex County, MA Lowell short-code rows.

Run from backend/:
    python scripts/pattern_middlesex_ma_adjudication.py --dry-run
    python scripts/pattern_middlesex_ma_adjudication.py --apply

This batch reuses the Norfolk-style short-code pattern only where the code
family is directly supported by Lowell's ordinance. Numeric rows and other
town-specific abbreviations are intentionally left unclear.
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

MIDDLESEX_JURISDICTION_NAME = "Middlesex County, MA"
LOWELL_ZONING_URL = "https://lowellma.gov/DocumentCenter/View/1007/Zoning-Ordinance-PDF?bidId="

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


LOWELL_CITATIONS = [
    {
        "section": "Lowell Zoning Ordinance Article XII, Table of Uses",
        "quote": "Districts: SSF SMF SMU RR TSF TTF TMF TMU NB USF UMF UMU DMU HRC INST OP LI GI",
        "url": LOWELL_ZONING_URL,
    },
    {
        "section": "Lowell Zoning Ordinance Section 12.9 Industrial Uses",
        "quote": "Self-storage facility. N N N N N N N N N N N N SP N SP N Y Y",
        "url": LOWELL_ZONING_URL,
    },
]


def lowell_prohibited(zone_code: str, label: str) -> Adjudication:
    return Adjudication(
        zone_code=zone_code,
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=0.9,
        notes=f"Lowell {label}; self-storage / mini-warehouse is not permitted in this district.",
        citations=LOWELL_CITATIONS,
    )


ADJUDICATIONS: dict[str, Adjudication] = {
    "SSF": lowell_prohibited("SSF", "Suburban Single-Family district"),
    "SMF": lowell_prohibited("SMF", "Suburban Multi-Family district"),
    "SMU": lowell_prohibited("SMU", "Suburban Mixed-Use district"),
    "TSF": lowell_prohibited("TSF", "Traditional Single-Family district"),
    "TTF": lowell_prohibited("TTF", "Traditional Two-Family district"),
    "NB": lowell_prohibited("NB", "Neighborhood Business district"),
    "USF": lowell_prohibited("USF", "Urban Single-Family district"),
    "UMF": lowell_prohibited("UMF", "Urban Multi-Family district"),
    "UMU": lowell_prohibited("UMU", "Urban Mixed-Use district"),
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
              AND z.municipality IS NULL
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
            "jurisdiction_name": MIDDLESEX_JURISDICTION_NAME,
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
          AND z.municipality IS NULL
          AND z.zone_code = :zone_code
          AND z.self_storage = 'unclear'
        """
    ).bindparams(bindparam("citations", type_=JSONB))
    result = await conn.execute(
        stmt,
        {
            "jurisdiction_name": MIDDLESEX_JURISDICTION_NAME,
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
        raise RuntimeError(f"Missing expected Middlesex rows: {sorted(missing)}")

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
    parser = argparse.ArgumentParser(description="Adjudicate Middlesex MA Lowell short-code rows")
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
            logger.info("Updated %d Middlesex zone_use_matrix rows", updated)
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
