"""Adjudicate Somerset County, NJ unclear zone_use_matrix rows.

Run from backend/:
    python scripts/somerset_nj_matrix_adjudication.py --dry-run
    python scripts/somerset_nj_matrix_adjudication.py --apply

This script only updates ordinance-backed Somerset County rows reviewed in this
pass. Ambiguous shared county codes are intentionally left unclear.
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

SOMERSET_JURISDICTION_ID = "394ef40c-ca0d-4d57-9b11-dc5417430240"

MANVILLE_ARTICLE_2_URL = "https://ecode360.com/36487194"
MANVILLE_ARTICLE_6_URL = "https://ecode360.com/47632848"
BRANCHBURG_ZONING_URL = "https://ecode360.com/36044516"
GREEN_BROOK_ZONING_URL = (
    "https://www.greenbrooktwp.org/_readwritedata/_file_depot/"
    "879360d9-8a02-43e7-8730-1576ff94d5d9.pdf"
)
FRANKLIN_DISTRICTS_URL = "https://ecode360.com/6274620"
FRANKLIN_PAC_URL = "https://ecode360.com/6275815"
FRANKLIN_SCV_URL = "https://ecode360.com/6275680"
WARREN_ZONING_URL = "https://ecode360.com/35252151"

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


def storage_adjudication(
    *,
    zone_code: str,
    permission: Permission,
    confidence: float,
    notes: str,
    citations: list[dict[str, str]],
) -> Adjudication:
    return Adjudication(
        zone_code=zone_code,
        self_storage=permission,
        mini_warehouse=permission,
        light_industrial=permission,
        luxury_garage_condo=permission,
        confidence=confidence,
        notes=notes,
        citations=citations,
    )


MANVILLE_RESIDENTIAL_CITATIONS = [
    {
        "section": "Manville Borough Code § 31-201",
        "quote": "S-100, S-75, S-60, S-50, and S-80 are Residential Districts.",
        "url": MANVILLE_ARTICLE_2_URL,
    },
    {
        "section": "Manville Borough Code § 31-601.2",
        "quote": "Permitted uses include dwellings and a home professional office.",
        "url": MANVILLE_ARTICLE_6_URL,
    },
]

GREEN_BROOK_RESIDENTIAL_CITATIONS = [
    {
        "section": "Green Brook Zoning Ordinance § 201",
        "quote": "LD-1 and LD-3 are Residential Districts.",
        "url": GREEN_BROOK_ZONING_URL,
    },
    {
        "section": "Green Brook Zoning Ordinance § 606.1-14",
        "quote": (
            "Self-Storage Facilities are listed in the RHC Regional Highway "
            "Commercial District."
        ),
        "url": GREEN_BROOK_ZONING_URL,
    },
]


ADJUDICATIONS: dict[str, Adjudication] = {
    "S-50": storage_adjudication(
        zone_code="S-50",
        permission="prohibited",
        confidence=0.95,
        notes="Manville S-50 is a residential zone; storage uses are not permitted.",
        citations=MANVILLE_RESIDENTIAL_CITATIONS,
    ),
    "S-60": storage_adjudication(
        zone_code="S-60",
        permission="prohibited",
        confidence=0.95,
        notes="Manville S-60 is a residential zone; storage uses are not permitted.",
        citations=MANVILLE_RESIDENTIAL_CITATIONS,
    ),
    "S-75": storage_adjudication(
        zone_code="S-75",
        permission="prohibited",
        confidence=0.95,
        notes="Manville S-75 is a residential zone; storage uses are not permitted.",
        citations=MANVILLE_RESIDENTIAL_CITATIONS,
    ),
    "S-80": storage_adjudication(
        zone_code="S-80",
        permission="prohibited",
        confidence=0.95,
        notes="Manville S-80 is a residential zone; storage uses are not permitted.",
        citations=MANVILLE_RESIDENTIAL_CITATIONS,
    ),
    "S-100": storage_adjudication(
        zone_code="S-100",
        permission="prohibited",
        confidence=0.95,
        notes="Manville S-100 is a residential zone; storage uses are not permitted.",
        citations=MANVILLE_RESIDENTIAL_CITATIONS,
    ),
    "LD": storage_adjudication(
        zone_code="LD",
        permission="prohibited",
        confidence=0.99,
        notes=(
            "Branchburg LD is Low Density Residential; mini-storage is "
            "prohibited in all zones."
        ),
        citations=[
            {
                "section": "Branchburg Code § LDO3-3.3.D",
                "quote": (
                    "Commercial storage of household or consumer goods, such "
                    "as mini-storage, is prohibited in all zones."
                ),
                "url": BRANCHBURG_ZONING_URL,
            },
            {
                "section": "Branchburg Code § LDO3-5",
                "quote": "LD Low Density One Acre Residential District.",
                "url": BRANCHBURG_ZONING_URL,
            },
        ],
    ),
    "LD-1": storage_adjudication(
        zone_code="LD-1",
        permission="prohibited",
        confidence=0.95,
        notes="Green Brook LD-1 is residential; self-storage is listed in RHC, not residential.",
        citations=GREEN_BROOK_RESIDENTIAL_CITATIONS,
    ),
    "LD-3": storage_adjudication(
        zone_code="LD-3",
        permission="prohibited",
        confidence=0.95,
        notes="Green Brook LD-3 is residential; self-storage is listed in RHC, not residential.",
        citations=GREEN_BROOK_RESIDENTIAL_CITATIONS,
    ),
    "SMD": storage_adjudication(
        zone_code="SMD",
        permission="prohibited",
        confidence=0.92,
        notes=(
            "Green Brook SMD permits residential/mountainside uses; "
            "self-storage is listed in RHC."
        ),
        citations=[
            {
                "section": "Green Brook Zoning Ordinance § 605.1",
                "quote": (
                    "SMD permitted uses include single-family dwellings and "
                    "cluster residential development."
                ),
                "url": GREEN_BROOK_ZONING_URL,
            },
            {
                "section": "Green Brook Zoning Ordinance § 606.1-14",
                "quote": (
                    "Self-Storage Facilities are listed in the RHC Regional "
                    "Highway Commercial District."
                ),
                "url": GREEN_BROOK_ZONING_URL,
            },
        ],
    ),
    "EP-250": storage_adjudication(
        zone_code="EP-250",
        permission="prohibited",
        confidence=0.95,
        notes=(
            "Warren EP-250 is agricultural-residential environmental "
            "protection; self-storage is not listed."
        ),
        citations=[
            {
                "section": "Warren Code § 16-9.1",
                "quote": "Development standards encourage clustered single-family dwellings.",
                "url": WARREN_ZONING_URL,
            },
            {
                "section": "Warren Code § 16-9.2",
                "quote": (
                    "No building, structure or lot shall be used except for "
                    "the following uses."
                ),
                "url": WARREN_ZONING_URL,
            },
        ],
    ),
    "PAC": storage_adjudication(
        zone_code="PAC",
        permission="conditional",
        confidence=0.7,
        notes="Franklin PAC is a planned adult community with limited commercial/support uses.",
        citations=[
            {
                "section": "Franklin Code § 112-161",
                "quote": (
                    "A minimum of 5% and up to 10% of the tract may be "
                    "developed for commercial uses."
                ),
                "url": FRANKLIN_PAC_URL,
            },
            {
                "section": "Franklin Code § 112-164.E",
                "quote": "Shopping and service facilities include retail goods and service stores.",
                "url": FRANKLIN_PAC_URL,
            },
        ],
    ),
    "S-C-V": storage_adjudication(
        zone_code="S-C-V",
        permission="conditional",
        confidence=0.7,
        notes=(
            "Franklin SCV is a planned senior citizen village with limited "
            "commercial/support uses."
        ),
        citations=[
            {
                "section": "Franklin Code § 112-151",
                "quote": (
                    "Senior Citizen Village District includes recreational, "
                    "medical and shopping facilities."
                ),
                "url": FRANKLIN_SCV_URL,
            },
            {
                "section": "Franklin Code § 112-153.F",
                "quote": "Shopping and service facilities include retail goods and service stores.",
                "url": FRANKLIN_SCV_URL,
            },
        ],
    ),
    "G-B": storage_adjudication(
        zone_code="G-B",
        permission="conditional",
        confidence=0.65,
        notes="Franklin G-B is a commercial district; classify conservatively as conditional.",
        citations=[
            {
                "section": "Franklin Code § 112-5",
                "quote": "G-B is General Business.",
                "url": FRANKLIN_DISTRICTS_URL,
            },
            {
                "section": "Franklin Code § 112-8.M",
                "quote": (
                    "G-B provides business and commercial uses for the local "
                    "traveling public."
                ),
                "url": FRANKLIN_DISTRICTS_URL,
            },
        ],
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
                z.zone_name,
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
              AND z.municipality IS NULL
              AND z.deleted_at IS NULL
              AND z.zone_code = ANY(:zone_codes)
            GROUP BY
                z.zone_code,
                z.zone_name,
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
            "jurisdiction_id": SOMERSET_JURISDICTION_ID,
            "zone_codes": list(ADJUDICATIONS),
        },
    )
    return [dict(row._mapping) for row in result]


async def apply_adjudication(conn, item: Adjudication) -> int:
    stmt = (
        text(
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
              AND municipality IS NULL
              AND deleted_at IS NULL
              AND zone_code = :zone_code
              AND self_storage = 'unclear'
              AND mini_warehouse = 'unclear'
              AND light_industrial = 'unclear'
              AND luxury_garage_condo = 'unclear'
            """
        )
        .bindparams(bindparam("citations", type_=JSONB))
    )
    result = await conn.execute(
        stmt,
        {
            "jurisdiction_id": SOMERSET_JURISDICTION_ID,
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
    unclear_parcels = 0
    matched_rows = {row["zone_code"] for row in rows}
    missing = set(ADJUDICATIONS) - matched_rows
    if missing:
        raise RuntimeError(f"Missing expected Somerset zone_use_matrix rows: {sorted(missing)}")

    for row in rows:
        item = ADJUDICATIONS[row["zone_code"]]
        moves_from_unclear = all(
            row[column] == "unclear"
            for column in (
                "self_storage",
                "mini_warehouse",
                "light_industrial",
                "luxury_garage_condo",
            )
        )
        if moves_from_unclear and item.self_storage != "unclear":
            unclear_parcels += int(row["parcel_count"])
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
    return len(rows), unclear_parcels


async def main() -> int:
    parser = argparse.ArgumentParser(description="Adjudicate Somerset County, NJ matrix rows")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview row and parcel impact")
    mode.add_argument("--apply", action="store_true", help="Apply the adjudication")
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
            citation_summary = {k: v.citations for k, v in ADJUDICATIONS.items()}
            logger.info("Citations:\n%s", json.dumps(citation_summary, indent=2))

            if args.dry_run:
                logger.info("Dry run only; no rows updated.")
                return 0

            updated = 0
            for item in ADJUDICATIONS.values():
                updated += await apply_adjudication(conn, item)
            logger.info("Updated %d Somerset zone_use_matrix rows", updated)
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
