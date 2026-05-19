"""
Populate zone_use_matrix for New York, NY (NYC, all 5 boroughs) from the
NYC Zoning Resolution use groups.

Source:
  NYC Zoning Resolution §32-15 to §32-31 — Commercial District Use Group tables
  NYC Zoning Resolution §42-10 to §42-15 — Manufacturing District Use Group tables

Self-storage in NYC is Use Group 16 ("General Service Uses — Storage and
Service Establishments — Self-Storage Warehouses").

Per ZR §32-25 + §42-12:
  Permitted by right (UG 16):
    M1, M2, M3 (all subtypes)
    C8 (auto-oriented commercial — auto repair, gas, warehousing)
    M1-D, M1-2A, M1-2F, M1-4A, M1-5A, M1-5M, M1-6D, M1-6M (variants)
  Special permit (treated as "conditional" — operator confirms feasibility):
    C6-2M, C6-3M, C6-4M (Manhattan-only special mixed districts)
  Prohibited:
    All R-prefix residential (R1 through R10 and subtypes)
    C1, C2, C3, C4, C5, C6 (except M-overlay subtypes), C7 (parks/recreation)
    Special districts (BPC, parks)

Light industrial (UG 17 + UG 11 limited):
  Permitted: M1, M2, M3 (with size limits in M1), C8 (limited), some C6
  Prohibited: all R, most C

Mini-warehouse: same as self-storage in NYC (no separate use group).

Luxury garage condo: no NYC-specific data; default unclear for
non-residential, prohibited for residential.

Run from backend/:
    python scripts/setup_nyc_matrix.py

This script is idempotent: it deletes existing matrix rows for NYC first,
then re-inserts. Safe to re-run.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.db import async_session_maker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

Y = "permitted"
N = "prohibited"
U = "unclear"
C = "conditional"


def make_zones() -> dict[str, tuple[str, str, str, str, str]]:
    """Build the full NYC zone catalog.

    Tuple: (zone_name, self_storage, mini_warehouse, light_industrial, luxury_garage_condo).
    Residential always prohibits all storage. Manufacturing always permits
    self-storage + mini-warehouse + light_industrial. Commercial varies.
    """
    z: dict[str, tuple[str, str, str, str, str]] = {}

    # ─── Residential (R1-R10 + variants) — all storage prohibited ───────────
    residential = [
        # R1 (low-density detached)
        ("R1-1", "Residential 1-Family Detached - R1-1"),
        ("R1-2", "Residential 1-Family Detached - R1-2"),
        ("R1-2A", "Residential 1-Family Detached - R1-2A"),
        # R2 (low-density detached)
        ("R2", "Residential 1-Family Detached - R2"),
        ("R2A", "Residential 1-Family Detached - R2A"),
        ("R2X", "Residential 1-Family Detached - R2X"),
        # R3 (low-density mixed)
        ("R3-1", "Residential 1-2 Family - R3-1"),
        ("R3-2", "Residential General - R3-2"),
        ("R3A", "Residential 1-Family Detached - R3A"),
        ("R3X", "Residential 1-Family Detached - R3X"),
        # R4 (low-medium density)
        ("R4", "Residential General - R4"),
        ("R4-1", "Residential 1-2 Family - R4-1"),
        ("R4A", "Residential 1-Family Detached - R4A"),
        ("R4B", "Residential 1-2 Family - R4B"),
        # R5 (medium density)
        ("R5", "Residential General - R5"),
        ("R5A", "Residential 1-Family Detached - R5A"),
        ("R5B", "Residential 1-2 Family - R5B"),
        ("R5D", "Residential General - R5D"),
        # R6 (medium-high density)
        ("R6", "Residential General - R6"),
        ("R6A", "Residential General - R6A"),
        ("R6B", "Residential General - R6B"),
        # R7 (high density)
        ("R7", "Residential General - R7"),
        ("R7-1", "Residential General - R7-1"),
        ("R7-2", "Residential General - R7-2"),
        ("R7A", "Residential General - R7A"),
        ("R7B", "Residential General - R7B"),
        ("R7D", "Residential General - R7D"),
        ("R7X", "Residential General - R7X"),
        # R8 (high density)
        ("R8", "Residential General - R8"),
        ("R8A", "Residential General - R8A"),
        ("R8B", "Residential General - R8B"),
        ("R8X", "Residential General - R8X"),
        # R9 (very high density)
        ("R9", "Residential General - R9"),
        ("R9A", "Residential General - R9A"),
        ("R9X", "Residential General - R9X"),
        # R10 (highest density)
        ("R10", "Residential General - R10"),
        ("R10A", "Residential General - R10A"),
        ("R10H", "Residential General - R10H (Hotel)"),
        ("R10X", "Residential General - R10X"),
    ]
    for code, name in residential:
        z[code] = (name, N, N, N, N)

    # ─── Commercial C1 (local retail; usually overlaid on residential) ──────
    # No self-storage; light industrial prohibited.
    c1_codes = [
        "C1-1", "C1-2", "C1-3", "C1-4", "C1-5",
        "C1-6", "C1-6A", "C1-7", "C1-7A",
        "C1-8", "C1-8A", "C1-8X", "C1-9", "C1-9A",
    ]
    for code in c1_codes:
        z[code] = (f"Commercial Local Retail - {code}", N, N, N, U)

    # ─── Commercial C2 (local service; overlay or stand-alone) ──────────────
    c2_codes = [
        "C2-1", "C2-2", "C2-3", "C2-4", "C2-5",
        "C2-6", "C2-6A", "C2-7", "C2-7A", "C2-7X",
        "C2-8", "C2-8A",
    ]
    for code in c2_codes:
        z[code] = (f"Commercial Local Service - {code}", N, N, N, U)

    # ─── Commercial C3 (waterfront recreation) ──────────────────────────────
    z["C3"] = ("Commercial Waterfront Recreation - C3", N, N, N, U)
    z["C3A"] = ("Commercial Waterfront Recreation - C3A", N, N, N, U)

    # ─── Commercial C4 (general commercial; regional) ───────────────────────
    c4_codes = [
        "C4-1", "C4-2", "C4-2A", "C4-2F", "C4-3", "C4-3A",
        "C4-4", "C4-4A", "C4-4D", "C4-4L", "C4-5", "C4-5A",
        "C4-5D", "C4-5X", "C4-6", "C4-6A", "C4-7", "C4-7A",
    ]
    for code in c4_codes:
        z[code] = (f"Commercial General - {code}", N, N, N, U)

    # ─── Commercial C5 (central commercial; CBD core) ───────────────────────
    c5_codes = [
        "C5-1", "C5-1A", "C5-2", "C5-2.5", "C5-2A",
        "C5-3", "C5-4", "C5-5", "C5-P",
    ]
    for code in c5_codes:
        z[code] = (f"Commercial Central Restricted - {code}", N, N, N, U)

    # ─── Commercial C6 (general central; mostly N; M-overlay variants Y) ───
    # M-overlay subtypes (C6-2M, C6-3M, C6-4M) permit Use Group 16 by special
    # permit — coded as conditional.
    c6_general = [
        "C6-1", "C6-1A", "C6-1G", "C6-11",
        "C6-2", "C6-2A", "C6-2G",
        "C6-3", "C6-3A", "C6-3D", "C6-3X",
        "C6-4", "C6-4A", "C6-4X",
        "C6-5", "C6-5.5", "C6-6", "C6-6.5",
        "C6-7", "C6-7T",
        "C6-8",
    ]
    for code in c6_general:
        z[code] = (f"Commercial Central General - {code}", N, N, N, U)
    # M-overlay C6 (conditional / special-permit)
    c6_m_overlay = ["C6-2M", "C6-3M", "C6-4M", "C6-9"]
    for code in c6_m_overlay:
        z[code] = (f"Commercial Central w/ M-Overlay - {code}", C, C, Y, U)

    # ─── Commercial C7 (commercial amusement) ───────────────────────────────
    z["C7"] = ("Commercial Amusement - C7", N, N, N, U)

    # ─── Commercial C8 (auto-oriented; self-storage Y) ──────────────────────
    c8_codes = ["C8-1", "C8-2", "C8-3", "C8-4"]
    for code in c8_codes:
        z[code] = (f"Commercial Auto-Oriented - {code}", Y, Y, Y, U)

    # ─── Manufacturing M1 (light manufacturing — Y all storage) ─────────────
    m1_codes = [
        "M1-1", "M1-2", "M1-3", "M1-4", "M1-5", "M1-6",
        "M1-1D", "M1-2D", "M1-3D", "M1-4D", "M1-5D", "M1-6D",
        "M1-2A", "M1-2F", "M1-4A", "M1-5A", "M1-5B",
        "M1-5M", "M1-6M",
        "M1-1/R5", "M1-1/R6", "M1-1/R7", "M1-1/R8", "M1-1/R9", "M1-1/R10",
        "M1-2/R5", "M1-2/R6", "M1-2/R6A", "M1-2/R7", "M1-2/R8",
        "M1-3/R6", "M1-3/R7", "M1-3/R8",
        "M1-4/R6", "M1-4/R7", "M1-4/R8",
        "M1-5/R6", "M1-5/R7", "M1-5/R8", "M1-5/R9",
        "M1-6/R9", "M1-6/R10",
    ]
    for code in m1_codes:
        z[code] = (f"Manufacturing Light - {code}", Y, Y, Y, U)

    # ─── Manufacturing M2 (medium manufacturing) ────────────────────────────
    m2_codes = ["M2-1", "M2-2", "M2-3", "M2-4"]
    for code in m2_codes:
        z[code] = (f"Manufacturing Medium - {code}", Y, Y, Y, U)

    # ─── Manufacturing M3 (heavy manufacturing) ─────────────────────────────
    m3_codes = ["M3-1", "M3-2"]
    for code in m3_codes:
        z[code] = (f"Manufacturing Heavy - {code}", Y, Y, Y, U)

    # ─── Special districts (storage prohibited; mostly residential overlay) ─
    z["BPC"] = ("Battery Park City Special District", N, N, N, U)
    z["PARK"] = ("Public Parks", N, N, N, N)

    return z


ZONES = make_zones()


async def main() -> None:
    async with async_session_maker() as db:
        # Resolve jurisdiction
        row = await db.execute(
            text("SELECT id, name FROM jurisdictions WHERE name = :name"),
            {"name": "New York, NY"},
        )
        jur = row.fetchone()
        if not jur:
            logger.error("Jurisdiction 'New York, NY' not found")
            return
        jur_id = str(jur.id)
        logger.info("Jurisdiction ID: %s (%s)", jur_id, jur.name)

        # Wipe existing matrix rows (idempotent)
        existing = await db.execute(
            text("SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": jur_id},
        )
        existing_count = existing.scalar() or 0
        logger.info("Existing matrix rows: %d", existing_count)

        await db.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": jur_id},
        )

        inserted = 0
        for zone_code, (zone_name, ss, mw, li, lgc) in ZONES.items():
            await db.execute(
                text("""
                    INSERT INTO zone_use_matrix
                        (jurisdiction_id, zone_code, zone_name,
                         self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                         classification_source, confidence, notes)
                    VALUES
                        (:jid, :zc, :zn, :ss, :mw, :li, :lgc,
                         'human', 1.0,
                         'NYC Zoning Resolution §32-25 + §42-12, Use Group 16 (self-storage)')
                """),
                {
                    "jid": jur_id, "zc": zone_code, "zn": zone_name,
                    "ss": ss, "mw": mw, "li": li, "lgc": lgc,
                },
            )
            inserted += 1

        await db.commit()
        logger.info("Inserted %d zone_use_matrix rows for New York, NY", inserted)

        # Permission distribution summary
        result = await db.execute(
            text("""
                SELECT self_storage, COUNT(*) FROM zone_use_matrix
                WHERE jurisdiction_id = :jid GROUP BY self_storage ORDER BY self_storage
            """),
            {"jid": jur_id},
        )
        logger.info("Self-storage permission distribution:")
        for r in result:
            logger.info("  %-12s %d zones", r[0], r[1])

        # Coverage check against actual parcel zoning_codes
        result = await db.execute(
            text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(z.zone_code) AS matched,
                    ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(*), 0), 1) AS pct
                FROM parcels p
                LEFT JOIN zone_use_matrix z
                    ON z.jurisdiction_id = p.jurisdiction_id
                    AND z.zone_code = p.zoning_code
                WHERE p.jurisdiction_id = :jid
            """),
            {"jid": jur_id},
        )
        r = result.fetchone()
        logger.info(
            "Parcel-matrix coverage: %d / %d (%.1f%%)",
            r.matched or 0, r.total or 0, float(r.pct or 0),
        )

        # Show un-matched zone codes (so operator can see what's still missing)
        result = await db.execute(
            text("""
                SELECT p.zoning_code, COUNT(*) AS n
                FROM parcels p
                LEFT JOIN zone_use_matrix z
                    ON z.jurisdiction_id = p.jurisdiction_id AND z.zone_code = p.zoning_code
                WHERE p.jurisdiction_id = :jid
                  AND z.zone_code IS NULL
                  AND p.zoning_code IS NOT NULL
                GROUP BY p.zoning_code
                ORDER BY n DESC
                LIMIT 25
            """),
            {"jid": jur_id},
        )
        unmatched = result.fetchall()
        if unmatched:
            logger.info("Top 25 unmatched zone codes (operator should review):")
            for r in unmatched:
                logger.info("  %-15s %d parcels", r[0], r[1])
        else:
            logger.info("✓ All parcel zoning codes are matched by the matrix")


if __name__ == "__main__":
    asyncio.run(main())
