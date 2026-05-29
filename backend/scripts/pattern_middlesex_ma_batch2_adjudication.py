"""Adjudicate defensible Middlesex County, MA pattern batch 2 rows.

Run from backend/:
    python scripts/pattern_middlesex_ma_batch2_adjudication.py --dry-run
    python scripts/pattern_middlesex_ma_batch2_adjudication.py --apply

This pass targets only high-confidence Middlesex municipal residential code
families after the Lowell batch 1 work. Parcel city is blank in the county
feed, so ambiguous shared abbreviations such as GR remain unclear.
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

SOMERVILLE_DISTRICTS_URL = "https://www.somervillezoning.com/wp-content/uploads/sites/2/2019/08/03-Residential-Districts.pdf"
SOMERVILLE_USES_URL = "https://www.somervillezoning.com/wp-content/uploads/sites/2/2019/08/09-Use-Provisions.pdf"
MELROSE_ZONING_URL = "https://ecode360.com/ME1773/laws/LF2202158.pdf"
READING_ZONING_URL = "https://www.readingma.gov/DocumentCenter/View/2242/Zoning-Bylaw-PDF"

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


SOMERVILLE_RESIDENTIAL_CITATIONS = [
    {
        "section": "Somerville Zoning Ordinance Article 9, Use Provisions",
        "quote": "Self Storage is not permitted in NR or UR districts.",
        "url": SOMERVILLE_USES_URL,
    },
    {
        "section": "Somerville Zoning Ordinance neighborhood district standards",
        "quote": "NR is Neighborhood Residence and UR is Urban Residence.",
        "url": SOMERVILLE_DISTRICTS_URL,
    },
]

MELROSE_URBAN_RESIDENTIAL_CITATIONS = [
    {
        "section": "Melrose Zoning Ordinance Section 235-5.1",
        "quote": "Urban Residence districts include UR-A, UR-B, UR-C, and UR-D.",
        "url": MELROSE_ZONING_URL,
    },
    {
        "section": "Melrose Zoning Ordinance Section 235-5.2",
        "quote": "Motor freight terminal and warehousing are not permitted in UR districts.",
        "url": MELROSE_ZONING_URL,
    },
    {
        "section": "Melrose Zoning Ordinance Section 235-5.2",
        "quote": "Uses not listed in the table are prohibited in every district.",
        "url": MELROSE_ZONING_URL,
    },
]

READING_SINGLE_FAMILY_CITATIONS = [
    {
        "section": "Reading Zoning Bylaw Table 4.2.2",
        "quote": "Residence districts include S-15, S-20, and S-40.",
        "url": READING_ZONING_URL,
    },
    {
        "section": "Reading Zoning Bylaw Section 5.2.1",
        "quote": "Use regulations are specified in the permitted use tables; No denotes prohibited.",
        "url": READING_ZONING_URL,
    },
    {
        "section": "Reading Zoning Bylaw Table 5.2.2",
        "quote": "Self-Service Storage Facility is listed only in business/industrial use rows.",
        "url": READING_ZONING_URL,
    },
]


ADJUDICATIONS: dict[str, Adjudication] = {
    # Somerville current zoning districts.
    "NR": prohibited(
        "NR",
        "Somerville Neighborhood Residence district; Self Storage is not permitted.",
        SOMERVILLE_RESIDENTIAL_CITATIONS,
    ),
    "UR": prohibited(
        "UR",
        "Somerville Urban Residence district; Self Storage is not permitted.",
        SOMERVILLE_RESIDENTIAL_CITATIONS,
    ),
    # Melrose UR-* districts; the county feed strips the hyphen.
    "URA": prohibited(
        "URA",
        "Hyphen-normalized Melrose UR-A Urban Residence district; warehouse/storage uses are prohibited.",
        MELROSE_URBAN_RESIDENTIAL_CITATIONS,
    ),
    "URB": prohibited(
        "URB",
        "Hyphen-normalized Melrose UR-B Urban Residence district; warehouse/storage uses are prohibited.",
        MELROSE_URBAN_RESIDENTIAL_CITATIONS,
    ),
    "URC": prohibited(
        "URC",
        "Hyphen-normalized Melrose UR-C Urban Residence district; warehouse/storage uses are prohibited.",
        MELROSE_URBAN_RESIDENTIAL_CITATIONS,
    ),
    "URD": prohibited(
        "URD",
        "Hyphen-normalized Melrose UR-D Urban Residence district; warehouse/storage uses are prohibited.",
        MELROSE_URBAN_RESIDENTIAL_CITATIONS,
    ),
    # Reading S-* districts; the county feed strips the hyphen.
    "S15": prohibited(
        "S15",
        "Hyphen-normalized Reading S-15 Single Family Residence district; storage/industrial uses are not residential uses.",
        READING_SINGLE_FAMILY_CITATIONS,
    ),
    "S20": prohibited(
        "S20",
        "Hyphen-normalized Reading S-20 Single Family Residence district; storage/industrial uses are not residential uses.",
        READING_SINGLE_FAMILY_CITATIONS,
    ),
    "S40": prohibited(
        "S40",
        "Hyphen-normalized Reading S-40 Single Family Residence district; storage/industrial uses are not residential uses.",
        READING_SINGLE_FAMILY_CITATIONS,
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
    parser = argparse.ArgumentParser(description="Adjudicate Middlesex MA pattern batch 2 rows")
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
