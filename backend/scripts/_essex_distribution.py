"""Essex post-bind report: bound_pct, spot-check, and THE DISTRIBUTION. Read-only."""
import asyncio, asyncpg
from scripts._db import get_sync_dsn
JID='67541a18-c599-423b-bf05-d68153af1e2f'
WEALTHY=['Livingston township','Fairfield township','Millburn township','Montclair township','West Orange township',
         'Verona township','West Caldwell township','North Caldwell borough','Roseland borough','Essex Fells borough']

async def main():
    c=await asyncpg.connect(get_sync_dsn(),timeout=120,statement_cache_size=0)
    try:
        await c.execute("SET statement_timeout=0")
        # 1. bound_pct
        tot=await c.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid",JID)
        bnd=await c.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL",JID)
        print(f"=== 1. BOUND_PCT === {bnd}/{tot} = {100.0*bnd/tot:.2f}%")
        pt=await c.fetch("""SELECT city, count(*) tot, count(*) FILTER (WHERE zoning_code IS NOT NULL) bnd
            FROM parcels WHERE jurisdiction_id=$1::uuid AND city=ANY($2::text[]) GROUP BY city ORDER BY city""",JID,WEALTHY)
        for r in pt: print(f"   {r['city']}: {r['bnd']}/{r['tot']} = {100.0*r['bnd']/r['tot']:.1f}%")

        # 2. 20-parcel spot-check across wealthy towns
        print("\n=== 2. SPOT-CHECK (4 parcels x 5 towns) ===")
        for t in ['Livingston township','Fairfield township','Millburn township','Montclair township','West Orange township']:
            rows=await c.fetch("""SELECT id, zoning_code, round(acres::numeric,2) acres, zone_binding_method m
                FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2 AND zoning_code IS NOT NULL
                ORDER BY acres DESC NULLS LAST LIMIT 4""",JID,t)
            print(f"  {t}:")
            for r in rows: print(f"    id={r['id']} zone={r['zoning_code']!r} acres={r['acres']} via={r['m']}")

        # 3. THE DISTRIBUTION — wealth-eligible >=1.5ac parcels by zone code, ranked
        print("\n=== 3. DISTRIBUTION — wealth-ring & >=1.5ac parcels by (city, zone_code), ranked ===")
        print("    (wealth ring = dt10 median_home_value>=475k AND median_hhi>=100k)")
        rows=await c.fetch("""
          SELECT p.city, p.zoning_code, count(*) n, round(avg(prm.median_home_value)) hv, round(avg(prm.median_hhi)) hhi
            FROM parcels p
            JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
           WHERE p.jurisdiction_id=$1::uuid AND p.acres>=1.5
             AND prm.median_home_value>=475000 AND prm.median_hhi>=100000
             AND p.zoning_code IS NOT NULL
           GROUP BY p.city, p.zoning_code
          HAVING count(*)>=3
           ORDER BY n DESC LIMIT 60""",JID)
        print(f"  {'city':28} {'zone':10} {'n':>5}  {'~HV':>8} {'~HHI':>7}")
        for r in rows:
            print(f"  {r['city']:28} {str(r['zoning_code']):10} {r['n']:>5}  {int(r['hv']):>8} {int(r['hhi']):>7}")

        # 3b. same but ONLY plausibly industrial/commercial-industrial codes for the wealthy targets
        print("\n=== 3b. INDUSTRIAL/COMMERCIAL-INDUSTRIAL candidate zones in wealth ring (wealthy towns) ===")
        cand = {
            'Livingston township': ['CI','I','R-L','R-L2','B-1','B-2','B'],
            'Fairfield township': ['L-1','L-2','L-3','C-3','C-1','C-2','H-D','O-P','CO'],
            'Millburn township': ['I','B','C','O','ML','O-R'],
            'Montclair township': ['I','C-1','C-2','C-3','B','LI'],
            'West Orange township': ['I','C','B','LI','SE','RP'],
            'Verona township': ['I','C','B'],
            'West Caldwell township': ['I','LI','B','C','O'],
            'Roseland borough': ['I','LI','B','C','OB','RE'],
            'North Caldwell borough': ['I','B','C'],
            'Essex Fells borough': ['B','C'],
        }
        for t, codes in cand.items():
            rows=await c.fetch("""
              SELECT p.zoning_code, count(*) n
                FROM parcels p
                JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
               WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 AND p.acres>=1.5
                 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000
                 AND p.zoning_code = ANY($3::text[])
               GROUP BY p.zoning_code ORDER BY n DESC""",JID,t,codes)
            if rows:
                s=", ".join(f"{r['zoning_code']}={r['n']}" for r in rows)
                print(f"  {t}: {s}")
            else:
                print(f"  {t}: (none of {codes} carry wealth-ring >=1.5ac lots)")

        # 3c. residential-vs-nonresidential split of the wealth-eligible pool (heuristic: R* = residential)
        print("\n=== 3c. wealth-ring >=1.5ac pool: residential (R*/AH/adult) vs other, per town ===")
        for t in WEALTHY:
            r=await c.fetchrow("""
              SELECT count(*) tot,
                count(*) FILTER (WHERE zoning_code ~ '^(R|AH)') res
                FROM parcels p
                JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
               WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 AND p.acres>=1.5
                 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000
                 AND p.zoning_code IS NOT NULL""",JID,t)
            other=r['tot']-r['res']
            print(f"  {t}: total={r['tot']}  residential={r['res']}  non-residential={other}")
    finally:
        await c.close()

if __name__=="__main__":
    asyncio.run(main())
