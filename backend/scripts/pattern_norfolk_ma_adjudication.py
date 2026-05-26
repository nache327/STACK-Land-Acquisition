"""Adjudicate defensible Norfolk County, MA short-code residential rows.

Run from backend/:
    python scripts/pattern_norfolk_ma_adjudication.py --dry-run
    python scripts/pattern_norfolk_ma_adjudication.py --apply

This pass deliberately avoids numeric assessor-style rows and generic
business/industrial abbreviations where the source municipality is missing.
Only rows backed by direct municipal district/use citations are updated.
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

NORFOLK_JURISDICTION_NAME = "Norfolk County, MA"

NORWOOD_DISTRICTS_URL = "https://ecode360.com/42511353"
NORWOOD_USES_URL = "https://ecode360.com/42511366"
NEEDHAM_BYLAW_URL = "https://www.needhamma.gov/DocumentCenter/View/16644"
BROOKLINE_DISTRICTS_URL = "https://ecode360.com/36311407"
BROOKLINE_USES_URL = "https://ecode360.com/45070995"

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


def prohibited(zone_code: str, notes: str, citations: list[dict[str, str]]) -> Adjudication:
    return Adjudication(
        zone_code=zone_code,
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=0.9,
        notes=notes,
        citations=citations,
    )


NORWOOD_RESIDENTIAL_CITATIONS = [
    {
        "section": "Norwood Zoning Bylaws Section 2.1",
        "quote": "Residential districts include Single Residence (S), S1, S2, and General Residence (G).",
        "url": NORWOOD_DISTRICTS_URL,
    },
    {
        "section": "Norwood Zoning Bylaws Section 3.1.4",
        "quote": "A use not classifiable under any listed category is forbidden in all zoning districts.",
        "url": NORWOOD_USES_URL,
    },
]

NEEDHAM_GR_CITATIONS = [
    {
        "section": "Needham Zoning By-Law Section 3.2.1",
        "quote": "The residential use table includes General Residence (GR) with residence uses.",
        "url": NEEDHAM_BYLAW_URL,
    },
    {
        "section": "Needham Zoning By-Law Section 3.2.1 Manufacturing",
        "quote": "Wholesale distribution facilities or storage in an enclosed structure are not allowed in GR.",
        "url": NEEDHAM_BYLAW_URL,
    },
]

BROOKLINE_RESIDENTIAL_CITATIONS = [
    {
        "section": "Brookline Zoning By-Law Section 3.01",
        "quote": "Residence districts include Single-Family (S) and Two-Family and Attached Single-Family (T).",
        "url": BROOKLINE_DISTRICTS_URL,
    },
    {
        "section": "Brookline Zoning By-Law Section 4.07",
        "quote": "The table of use regulations separates S, SC, T, F, M, L, G, O, and I districts.",
        "url": BROOKLINE_USES_URL,
    },
]


ADJUDICATIONS: dict[str, Adjudication] = {
    # Norwood residential short codes.
    "S": prohibited(
        "S",
        "Norwood Single Residence district; self-storage/warehouse uses are not a listed residential use.",
        NORWOOD_RESIDENTIAL_CITATIONS,
    ),
    "S1": prohibited(
        "S1",
        "Norwood Single Residence - 1 district; self-storage/warehouse uses are not a listed residential use.",
        NORWOOD_RESIDENTIAL_CITATIONS,
    ),
    "S2": prohibited(
        "S2",
        "Norwood Single Residence - 2 district; self-storage/warehouse uses are not a listed residential use.",
        NORWOOD_RESIDENTIAL_CITATIONS,
    ),
    "G": prohibited(
        "G",
        "Norwood General Residence district; self-storage/warehouse uses are not a listed residential use.",
        NORWOOD_RESIDENTIAL_CITATIONS,
    ),
    # Needham residential short code.
    "GR": prohibited(
        "GR",
        "Needham General Residence district; enclosed storage/distribution is not allowed in GR.",
        NEEDHAM_GR_CITATIONS,
    ),
    # Brookline residential short codes. The county feed normalizes some
    # Brookline S-10/S-15/S-25/S-40 values by stripping the hyphen.
    "S-7": prohibited(
        "S-7",
        "Brookline Single-Family S-7 district; storage uses are not residential uses.",
        BROOKLINE_RESIDENTIAL_CITATIONS,
    ),
    "S10": prohibited(
        "S10",
        "Hyphen-normalized Brookline S-10 Single-Family district; storage uses are not residential uses.",
        BROOKLINE_RESIDENTIAL_CITATIONS,
    ),
    "S15": prohibited(
        "S15",
        "Hyphen-normalized Brookline S-15 Single-Family district; storage uses are not residential uses.",
        BROOKLINE_RESIDENTIAL_CITATIONS,
    ),
    "S25": prohibited(
        "S25",
        "Hyphen-normalized Brookline S-25 Single-Family district; storage uses are not residential uses.",
        BROOKLINE_RESIDENTIAL_CITATIONS,
    ),
    "S40": prohibited(
        "S40",
        "Hyphen-normalized Brookline S-40 Single-Family district; storage uses are not residential uses.",
        BROOKLINE_RESIDENTIAL_CITATIONS,
    ),
    "T-5": prohibited(
        "T-5",
        "Brookline T-5 Two-Family / Attached Single-Family district; storage uses are not residential uses.",
        BROOKLINE_RESIDENTIAL_CITATIONS,
    ),
    "T-6": prohibited(
        "T-6",
        "Brookline T-6 Two-Family / Attached Single-Family district; storage uses are not residential uses.",
        BROOKLINE_RESIDENTIAL_CITATIONS,
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
            "jurisdiction_name": NORFOLK_JURISDICTION_NAME,
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
            "jurisdiction_name": NORFOLK_JURISDICTION_NAME,
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
        raise RuntimeError(f"Missing expected Norfolk rows: {sorted(missing)}")

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
    parser = argparse.ArgumentParser(description="Adjudicate Norfolk MA short-code rows")
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
            logger.info("Updated %d Norfolk zone_use_matrix rows", updated)
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
