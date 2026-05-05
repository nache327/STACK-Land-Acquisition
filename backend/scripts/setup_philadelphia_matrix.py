"""
Populate zone_use_matrix for Philadelphia, PA from Title 14 use tables.

Source tables:
  Table 14-602-1 (Residential)   — RSA, RSD, RTA, RM, RMX
  Table 14-602-2 (Commercial)    — CMX, CA
  Table 14-602-3 (Industrial)    — I, ICMX, IRMX, IP
  Table 14-602-4 (Special Purp.) — SP-*

Self-storage = "Moving and Storage Facilities" (§ 14-603) which explicitly
covers "self-service and mini-storage warehouses."

Permitted by right:  CA2, ICMX, I1, I2, I3, IP
Prohibited:          Everything else (no conditional/special-exception path exists)

Run from backend/:
    python scripts/setup_philadelphia_matrix.py
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

# (zone_name, self_storage, mini_warehouse, light_industrial, luxury_garage_condo)
# light_industrial = "Artists Studios and Artisan Industrial" + "Limited Industrial"
#   from Tables 14-602-2 and 14-602-3.
# luxury_garage_condo = no Philadelphia-specific data → unclear except residential (prohibited).
ZONES: dict[str, tuple[str, str, str, str, str]] = {
    # ── Residential ─────────────────────────────────────────── all storage N ──
    "RSD1":   ("Residential Single Family Detached 1",     N, N, N, N),
    "RSD2":   ("Residential Single Family Detached 2",     N, N, N, N),
    "RSD3":   ("Residential Single Family Detached 3",     N, N, N, N),
    "RSA1":   ("Residential Single Family Attached 1",     N, N, N, N),
    "RSA2":   ("Residential Single Family Attached 2",     N, N, N, N),
    "RSA3":   ("Residential Single Family Attached 3",     N, N, N, N),
    "RSA4":   ("Residential Single Family Attached 4",     N, N, N, N),
    "RSA5":   ("Residential Single Family Attached 5",     N, N, N, N),
    "RSA6":   ("Residential Single Family Attached 6",     N, N, N, N),
    "RTA1":   ("Residential Townhouse Attached 1",         N, N, N, N),
    "RTA2":   ("Residential Townhouse Attached 2",         N, N, N, N),
    "RM1":    ("Residential Multi-Family 1",               N, N, N, N),
    "RM2":    ("Residential Multi-Family 2",               N, N, N, N),
    "RM3":    ("Residential Multi-Family 3",               N, N, N, N),
    "RM4":    ("Residential Multi-Family 4",               N, N, N, N),
    "RMX1":   ("Residential Mixed-Use 1",                  N, N, N, N),
    "RMX2":   ("Residential Mixed-Use 2",                  N, N, N, N),
    "RMX3":   ("Residential Mixed-Use 3",                  N, N, N, N),
    # ── Commercial / Mixed-Use ───────────────────── storage N except CA2 ──────
    "CMX1":   ("Commercial Mixed-Use 1",                   N, N, N, U),
    "CMX2":   ("Commercial Mixed-Use 2",                   N, N, Y, U),
    "CMX2.5": ("Commercial Mixed-Use 2.5",                 N, N, Y, U),
    "CMX3":   ("Commercial Mixed-Use 3",                   N, N, Y, U),
    "CMX4":   ("Commercial Mixed-Use 4",                   N, N, Y, U),
    "CMX5":   ("Commercial Mixed-Use 5",                   N, N, Y, U),
    "CA1":    ("Auto-Oriented Commercial 1",               N, N, N, U),
    "CA2":    ("Auto-Oriented Commercial 2",               Y, Y, Y, U),
    # ── Industrial ──────────────────────────────── storage Y except IRMX ──────
    "I1":     ("Industrial 1",                             Y, Y, Y, U),
    "I2":     ("Industrial 2",                             Y, Y, Y, U),
    "I3":     ("Industrial 3",                             Y, Y, Y, U),
    "IP":     ("Industrial Park",                          Y, Y, Y, U),
    "ICMX":   ("Industrial-Commercial Mixed-Use",          Y, Y, Y, U),
    "IRMX":   ("Industrial-Residential Mixed-Use",         N, N, Y, U),
    # ── Special Purpose ─────────────────────────── all storage N ─────────────
    "SPAIR":  ("Special Purpose - Airport",                N, N, N, U),
    "SPCIV":  ("Special Purpose - Civic",                  N, N, N, U),
    "SPENT":  ("Special Purpose - Entertainment",          N, N, N, U),
    "SPINS":  ("Special Purpose - Institutional",          N, N, N, U),
    "SPPOA":  ("Special Purpose - Public Order A",         N, N, N, U),
    "SPPOP":  ("Special Purpose - Public Order P",         N, N, N, U),
    "SPSTA":  ("Special Purpose - Stadium",                N, N, N, U),
}


async def main() -> None:
    async with async_session_maker() as db:
        row = await db.execute(
            text("SELECT id FROM jurisdictions WHERE name = :name"),
            {"name": "Philadelphia, PA"},
        )
        jur = row.fetchone()
        if not jur:
            logger.error("Philadelphia, PA jurisdiction not found — run a job first.")
            return
        jur_id = str(jur.id)
        logger.info("Jurisdiction ID: %s", jur_id)

        await db.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": jur_id},
        )
        logger.info("Cleared existing matrix rows")

        inserted = 0
        for zone_code, (zone_name, ss, mw, li, lgc) in ZONES.items():
            await db.execute(text("""
                INSERT INTO zone_use_matrix
                    (jurisdiction_id, zone_code, zone_name,
                     self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                     classification_source, confidence, notes)
                VALUES
                    (:jid, :zc, :zn, :ss, :mw, :li, :lgc,
                     'human', 1.0,
                     'Title 14 Philadelphia Code use tables 14-602-1 through 14-602-4')
            """), {
                "jid": jur_id, "zc": zone_code, "zn": zone_name,
                "ss": ss, "mw": mw, "li": li, "lgc": lgc,
            })
            inserted += 1

        await db.commit()
        logger.info("Inserted %d zone_use_matrix rows for Philadelphia, PA", inserted)

        # Summary
        result = await db.execute(text("""
            SELECT self_storage, COUNT(*) FROM zone_use_matrix
            WHERE jurisdiction_id = :jid GROUP BY self_storage ORDER BY self_storage
        """), {"jid": jur_id})
        for r in result:
            logger.info("  self_storage=%-12s %d zones", r[0], r[1])

        # Coverage check against actual parcel data
        result = await db.execute(text("""
            SELECT COUNT(*) as total,
                   COUNT(z.zone_code) as matched,
                   ROUND(100.0 * COUNT(z.zone_code) / NULLIF(COUNT(*), 0), 1) as pct
            FROM parcels p
            LEFT JOIN zone_use_matrix z
                ON z.jurisdiction_id = p.jurisdiction_id AND z.zone_code = p.zoning_code
            WHERE p.jurisdiction_id = :jid
        """), {"jid": jur_id})
        r = result.fetchone()
        logger.info("Parcel coverage: %d / %d (%.1f%%)", r.matched, r.total, float(r.pct or 0))


if __name__ == "__main__":
    asyncio.run(main())
