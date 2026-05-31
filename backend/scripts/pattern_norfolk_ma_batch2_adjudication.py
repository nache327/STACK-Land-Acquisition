"""Adjudicate defensible Norfolk County, MA batch 2 matrix rows.

Run from backend/:
    python scripts/pattern_norfolk_ma_batch2_adjudication.py --dry-run
    python scripts/pattern_norfolk_ma_batch2_adjudication.py --apply

This pass stays intentionally narrow. Large Canton numeric rows were inspected
against Canton official zoning geometry, but each high-volume row contained at
least a small nonresidential spillover, so they remain unclear for a later,
parcel-level or municipality-aware pass.
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

BELLINGHAM_DISTRICTS_URL = "https://ecode360.com/15958491"
BELLINGHAM_USES_URL = "https://ecode360.com/15958491"
BROOKLINE_DISTRICTS_URL = "https://ecode360.com/36311401"
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


def prohibited(
    zone_code: str,
    notes: str,
    citations: list[dict[str, str]],
    confidence: float = 0.9,
) -> Adjudication:
    return Adjudication(
        zone_code=zone_code,
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=confidence,
        notes=notes,
        citations=citations,
    )


BELLINGHAM_SUBURBAN_CITATIONS = [
    {
        "section": "Bellingham Zoning Bylaw Section 240-28",
        "quote": "For purposes of this bylaw, the Town of Bellingham is divided into districts including Suburban District S.",
        "url": BELLINGHAM_DISTRICTS_URL,
    },
    {
        "section": "Bellingham Zoning Bylaw Section 240-29",
        "quote": "No building or structure shall be used except as set forth in the Use Regulations Schedule.",
        "url": BELLINGHAM_USES_URL,
    },
    {
        "section": "Bellingham Zoning Bylaw Section 240-31",
        "quote": "Warehouse is No in all listed districts; bulk storage is No in S/R districts.",
        "url": BELLINGHAM_USES_URL,
    },
]

BROOKLINE_BUSINESS_STORAGE_CITATIONS = [
    {
        "section": "Brookline Zoning By-Law Section 3.01",
        "quote": "Business districts include Local Business L, Business and Professional Offices O, and General Business G.",
        "url": BROOKLINE_DISTRICTS_URL,
    },
    {
        "section": "Brookline Zoning By-Law Section 4.01",
        "quote": "A listed use is permitted only where Section 4.07 denotes the district with Yes or SP.",
        "url": BROOKLINE_USES_URL,
    },
    {
        "section": "Brookline Zoning By-Law Section 4.07",
        "quote": "Wholesale business and storage in a roofed structure is No in L, G, and O districts and Yes only in I.",
        "url": BROOKLINE_USES_URL,
    },
]


ADJUDICATIONS: dict[str, Adjudication] = {
    # Bellingham Suburban District. The county feed uses SUBN for Bellingham's
    # suburban zoning label; coordinates cluster entirely in Bellingham.
    "SUBN": prohibited(
        "SUBN",
        "Bellingham Suburban district; warehouse/storage uses are not permitted in the S/R columns.",
        BELLINGHAM_SUBURBAN_CITATIONS,
    ),
    # Brookline business/office districts. These are not residence rows, but
    # Brookline still marks wholesale business/storage as No in L, G, and O.
    "G10": prohibited(
        "G10",
        "Hyphen-normalized Brookline G-1.0 General Business district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "G175(CC)": prohibited(
        "G175(CC)",
        "Hyphen-normalized Brookline G-1.75 (CC) General Business district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "G175(WS)": prohibited(
        "G175(WS)",
        "Hyphen-normalized Brookline G-1.75 (WS) General Business district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "G20": prohibited(
        "G20",
        "Hyphen-normalized Brookline G-2.0 General Business district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "G20(CA)": prohibited(
        "G20(CA)",
        "Hyphen-normalized Brookline G-2.0 (CA) General Business district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "L05": prohibited(
        "L05",
        "Hyphen-normalized Brookline L-0.5 Local Business district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "L05(CL)": prohibited(
        "L05(CL)",
        "Hyphen-normalized Brookline L-0.5 (CL) Local Business district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "L10": prohibited(
        "L10",
        "Hyphen-normalized Brookline L-1.0 Local Business district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "O10": prohibited(
        "O10",
        "Hyphen-normalized Brookline O-1.0 Business and Professional Offices district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
    ),
    "O20(CH)": prohibited(
        "O20(CH)",
        "Hyphen-normalized Brookline O-2.0 (CH) Business and Professional Offices district; storage uses are prohibited outside I.",
        BROOKLINE_BUSINESS_STORAGE_CITATIONS,
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
        raise RuntimeError(f"Missing expected Norfolk batch 2 rows: {sorted(missing)}")

    moved = 0
    for row in rows:
        item = ADJUDICATIONS[row["zone_code"]]
        if row["self_storage"] == "unclear" and item.self_storage != "unclear":
            moved += int(row["parcel_count"])
        logger.info(
            "%-10s parcels=%5d %s/%s/%s/%s -> %s/%s/%s/%s",
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
    parser = argparse.ArgumentParser(description="Adjudicate Norfolk MA pattern batch 2 rows")
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
