"""Passaic wealth-ring discovery-rank: which zones/towns hold in-ring industrial/CI lots.

Ranks (city, zoning_code) by count of parcels that are BOTH in the wealth ring
(dt=10 median_home_value>=475000 AND median_hhi>=100000) AND acres>=1.5 — the needle
pre-filter (minus the zoning verdict, which grounding supplies). Flags likely industrial/
commercial codes so we ground only the in-ring industrial/CI towns (Hudson lesson: big
warehouse corridors OUTSIDE the ring are correct no-ops).
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import asyncpg
from scripts._db import get_sync_dsn

JID = "7a9ed95d-df89-4864-a203-f831a987b562"


async def main():
    c = await asyncpg.connect(get_sync_dsn())
    rows = await c.fetch(
        """
        SELECT p.city, p.zoning_code,
               count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000
                                 AND prm.median_hhi>=100000) AS in_ring_15ac,
               count(*) AS total
        FROM parcels p
        LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
        WHERE p.jurisdiction_id=$1 AND p.zoning_code IS NOT NULL
        GROUP BY p.city, p.zoning_code
        HAVING count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000
                                 AND prm.median_hhi>=100000) > 0
        ORDER BY in_ring_15ac DESC
        LIMIT 60
        """, JID)
    print(f"{'city':<24} {'zone':<10} {'in_ring>=1.5ac':>14} {'total':>7}")
    for r in rows:
        print(f"{r['city']:<24} {str(r['zoning_code']):<10} {r['in_ring_15ac']:>14} {r['total']:>7}")
    # town-level rollup
    print("\n--- town rollup (in-ring >=1.5ac parcels, any zone) ---")
    tr = await c.fetch(
        """SELECT p.city, count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000
              AND prm.median_hhi>=100000) n
           FROM parcels p LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
           WHERE p.jurisdiction_id=$1 AND p.zoning_code IS NOT NULL
           GROUP BY p.city ORDER BY n DESC""", JID)
    for r in tr:
        print(f"  {r['city']:<24} {r['n']}")
    await c.close()

asyncio.run(main())
