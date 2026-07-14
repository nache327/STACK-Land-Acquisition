"""Union NJ discovery-rank — Phase-0 scan (NOT the report; discovery only).

Per parcels.city (exact casing needed for the buybox join): total parcels,
wealth-ring pass count (parcel_ring_metrics dt=10 HV>=475k & HHI>=100k),
acres>=1.5 wealth-pass count (the needle denominator), and current grounding
(distinct human-reviewed zone_use_matrix rows for that municipality).

Run: cd backend && PYTHONUTF8=1 python scripts/_discover_union_nj.py
"""
import asyncio, asyncpg

JID = "16dc5ad9-8211-47c6-bfad-93bf588b15e4"  # Union County, NJ


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='120s'")
        rows = await con.fetch("""
            WITH p AS (
              SELECT p.id, p.city, p.acres,
                     rm.median_home_value hv, rm.median_hhi hhi
              FROM parcels p
              LEFT JOIN parcel_ring_metrics rm
                     ON rm.parcel_id = p.id AND rm.drive_time_minutes = 10
              WHERE p.jurisdiction_id = $1
            )
            SELECT city,
                   count(*) AS parcels,
                   count(*) FILTER (WHERE hv>=475000 AND hhi>=100000) AS wealth_pass,
                   count(*) FILTER (WHERE hv>=475000 AND hhi>=100000 AND acres>=1.5) AS wealth_acre,
                   round(avg(hv)::numeric,0) AS avg_hv
            FROM p
            GROUP BY city
            ORDER BY wealth_acre DESC NULLS LAST, parcels DESC
        """, JID)
        # grounding state per municipality
        g = await con.fetch("""
            SELECT municipality, count(*) n,
                   count(*) FILTER (WHERE human_reviewed) hr
            FROM zone_use_matrix
            WHERE jurisdiction_id=$1 AND deleted_at IS NULL AND municipality IS NOT NULL
            GROUP BY municipality
        """, JID)
        gmap = {r['municipality']: (r['n'], r['hr']) for r in g}
        print(f"{'city':28} {'parcels':>8} {'wlth':>7} {'wlth+1.5ac':>10} {'avg_hv':>10}  grounded")
        for r in rows:
            n, hr = gmap.get(r['city'], (0, 0))
            gtag = f"{hr}hr/{n}" if n else "-"
            print(f"{(r['city'] or 'NULL'):28} {r['parcels']:>8} {r['wealth_pass'] or 0:>7} "
                  f"{r['wealth_acre'] or 0:>10} {str(r['avg_hv']):>10}  {gtag}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
