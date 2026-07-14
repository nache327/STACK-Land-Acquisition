"""Per-town zoning_code inventory (bound parcels) + wealth-ring counts (fast JOIN). Read-only."""
import asyncio, asyncpg, sys
from scripts._db import get_sync_dsn
JID='67541a18-c599-423b-bf05-d68153af1e2f'

async def main():
    towns = sys.argv[1].split("|") if len(sys.argv)>1 else \
        ['Fairfield township','West Caldwell township','Livingston township','Millburn township']
    c=await asyncpg.connect(get_sync_dsn(),timeout=180,statement_cache_size=0)
    try:
        await c.execute("SET statement_timeout=0")
        for t in towns:
            print(f"\n=== {t} — bound zoning_codes (n | wealth-ring>=1.5ac) ===")
            rows=await c.fetch("""
              SELECT p.zoning_code,
                count(*) n,
                count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000
                    AND prm.median_hhi>=100000) wr
              FROM parcels p
              LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
              WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 AND p.zoning_code IS NOT NULL
              GROUP BY p.zoning_code ORDER BY wr DESC, n DESC""", JID, t)
            for r in rows:
                flag = "  <== wealth-ring" if r['wr'] and r['wr']>=3 else ""
                print(f"  {str(r['zoning_code']):16} n={r['n']:<5} wr>=1.5ac={r['wr']}{flag}")
    finally:
        await c.close()

if __name__=="__main__":
    asyncio.run(main())
