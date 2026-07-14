"""Middlesex NJ wealth-ring distribution — rank in-ring industrial/CI zones. Read-only."""
import asyncio, asyncpg
from scripts._db import get_sync_dsn
JID='9c039328-c995-41fc-83ce-fb4966fd402b'

async def main():
    c=await asyncpg.connect(get_sync_dsn(),timeout=180,statement_cache_size=0)
    try:
        await c.execute("SET statement_timeout=0")
        bnd=await c.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL",JID)
        tot=await c.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid",JID)
        print(f"BOUND: {bnd}/{tot} = {100.0*bnd/tot:.2f}%")

        # spot-check
        print("\n=== spot-check (3 towns) ===")
        for t in ['Edison township','Cranbury township','South Plainfield borough']:
            rows=await c.fetch("""SELECT zoning_code, round(acres::numeric,2) ac, zoning_code_source s
                FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2 AND zoning_code IS NOT NULL
                ORDER BY acres DESC NULLS LAST LIMIT 2""",JID,t)
            for r in rows: print(f"  {t}: {r['zoning_code']!r} ac={r['ac']} via={r['s']}")

        # wealth-ring pool per town
        print("\n=== wealth-ring (dt10 HV>=475k,HHI>=100k) + acres>=1.5 by town ===")
        rows=await c.fetch("""
          SELECT p.city, count(*) n
            FROM parcels p JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
           WHERE p.jurisdiction_id=$1::uuid AND p.acres>=1.5
             AND prm.median_home_value>=475000 AND prm.median_hhi>=100000
           GROUP BY p.city ORDER BY n DESC""",JID)
        for r in rows: print(f"  {r['city']}: {r['n']}")

        # distribution by (city, zone) in-ring, industrial-ish flagged
        print("\n=== in-ring wealth+1.5ac lots by (city, zone), n>=3 ===")
        rows=await c.fetch("""
          SELECT p.city, p.zoning_code, count(*) n
            FROM parcels p JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
           WHERE p.jurisdiction_id=$1::uuid AND p.acres>=1.5
             AND prm.median_home_value>=475000 AND prm.median_hhi>=100000
             AND p.zoning_code IS NOT NULL
           GROUP BY p.city, p.zoning_code HAVING count(*)>=3 ORDER BY n DESC LIMIT 70""",JID)
        IND=('I','LI','L-I','GI','HI','M','M-1','M-2','IP','OR','O-R','ROM','RM','IND','LM','BP','PID','C-I','CI','MU','ROR','O-S','O-R')
        for r in rows:
            zc=str(r['zoning_code'])
            flag=" <== industrial/CI?" if any(zc.upper().startswith(x) or zc.upper()==x for x in IND) else ""
            print(f"  {r['city']:28} {zc:12} {r['n']:>5}{flag}")
    finally:
        await c.close()

if __name__=="__main__":
    asyncio.run(main())
