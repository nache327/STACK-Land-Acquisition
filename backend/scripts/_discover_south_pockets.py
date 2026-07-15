"""Phase-5 South discovery — per-city jids (SLCo model). Confirm city casing,
zoned%, ring10 coverage, wealth-pass, and existing grounding.
Run: cd backend && PYTHONUTF8=1 python scripts/_discover_south_pockets.py
"""
import asyncio, asyncpg

JIDS = {
    "Brentwood TN":       "e0df78b2-de04-4e43-bf3b-c5244eb4613c",
    "Franklin TN":        "307285f8-9426-4f17-9e66-999c8e01218f",
    "Sandy Springs GA":   "b49ac34f-6394-47ba-87e3-149b6ae0d706",
    "Atlanta-Buckhead GA":"a5d68bcd-ce4b-446a-aefb-23613e6f9013",
}


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        for name, jid in JIDS.items():
            tot = await con.fetchrow("""
                SELECT count(*) n, count(zoning_code) nz,
                       count(DISTINCT zoning_code) dz
                FROM parcels WHERE jurisdiction_id=$1""", jid)
            ring = await con.fetchval("""
                SELECT count(*) FROM parcel_ring_metrics rm
                JOIN parcels p ON p.id=rm.parcel_id
                WHERE p.jurisdiction_id=$1 AND rm.drive_time_minutes=10""", jid)
            cities = await con.fetch("""
                SELECT city, count(*) n FROM parcels WHERE jurisdiction_id=$1
                GROUP BY city ORDER BY n DESC LIMIT 6""", jid)
            grounded = await con.fetchval("""
                SELECT count(*) FROM zone_use_matrix
                WHERE jurisdiction_id=$1 AND human_reviewed AND deleted_at IS NULL""", jid)
            zpct = (100*tot['nz']/tot['n']) if tot['n'] else 0
            print(f"\n=== {name}  [{jid}] ===")
            print(f"  parcels={tot['n']}  zoned={tot['nz']} ({zpct:.1f}%)  distinct_codes={tot['dz']}  "
                  f"ring10={ring}  human_matrix_rows={grounded}")
            print("  cities: " + ", ".join(f"'{c['city']}':{c['n']}" for c in cities))
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
