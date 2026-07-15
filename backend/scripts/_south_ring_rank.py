"""Phase-5 South in-ring discovery-rank. For a per-city jid: parcels with dt10
ring wealth-pass (HV>=475k & HHI>=100k) AND acres>=1.5, grouped by zoning_code,
so we see which industrial/flex zones carry the in-ring needle candidates.
Also prints total ring10 coverage (to confirm precompute landed).
Run: cd backend && PYTHONUTF8=1 python scripts/_south_ring_rank.py <jid> [<jid> ...]
     (no arg -> all 4 South per-city jids)
"""
import asyncio, sys, asyncpg

ALL = {
    "Brentwood TN": "e0df78b2-de04-4e43-bf3b-c5244eb4613c",
    "Franklin TN": "307285f8-9426-4f17-9e66-999c8e01218f",
    "Sandy Springs GA": "b49ac34f-6394-47ba-87e3-149b6ae0d706",
    "Atlanta-Buckhead GA": "a5d68bcd-ce4b-446a-aefb-23613e6f9013",
}


async def main(jids):
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        inv = {v: k for k, v in ALL.items()}
        for jid in jids:
            name = inv.get(jid, jid)
            ring = await con.fetchval("""SELECT count(*) FROM parcel_ring_metrics rm
                JOIN parcels p ON p.id=rm.parcel_id
                WHERE p.jurisdiction_id=$1 AND rm.drive_time_minutes=10""", jid)
            wpass = await con.fetchval("""SELECT count(*) FROM parcel_ring_metrics rm
                JOIN parcels p ON p.id=rm.parcel_id
                WHERE p.jurisdiction_id=$1 AND rm.drive_time_minutes=10
                  AND rm.median_home_value>=475000 AND rm.median_hhi>=100000""", jid)
            print(f"\n=== {name}  ring10={ring}  wealth-pass={wpass} ===")
            if not ring:
                print("  (ring metrics NOT yet computed)")
                continue
            rows = await con.fetch("""
                SELECT p.zoning_code zc, count(*) n
                FROM parcels p JOIN parcel_ring_metrics rm ON rm.parcel_id=p.id AND rm.drive_time_minutes=10
                WHERE p.jurisdiction_id=$1 AND rm.median_home_value>=475000 AND rm.median_hhi>=100000
                  AND p.acres>=1.5
                GROUP BY zc ORDER BY n DESC""", jid)
            print(f"  in-ring wealth+1.5ac by zone ({sum(r['n'] for r in rows)} total):")
            for r in rows:
                print(f"    {str(r['zc']):12} {r['n']:>5}")
    finally:
        await con.close()


if __name__ == "__main__":
    args = sys.argv[1:] or list(ALL.values())
    asyncio.run(main(args))
