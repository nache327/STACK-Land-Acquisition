"""Nassau NY — populate parcels.city from the ingest raw->>'MUNI_NAME' (the NYS assessing
municipality: village name where incorporated, else town — Oyster Bay/Hempstead/North Hempstead).
parcels.city is NULL for all 420,577 Nassau parcels, which breaks the buybox join
(municipality = parcels.city). MUNI_NAME is authoritative and already in the ingest blob, so this is
the municipality bind — no spatial join needed. Idempotent (only fills NULL). city_source='raw_muni_name'.
Run:  cd backend && PYTHONUTF8=1 python scripts/_backfill_nassau_city.py [--apply]
"""
import asyncio, sys, asyncpg
from scripts._db import get_sync_dsn

JID = "c72002c7-1f3e-48e4-be98-04e420776fdb"

async def main(apply: bool):
    c = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    try:
        await c.execute("SET statement_timeout=0")
        # preview distinct MUNI_NAME + counts
        rows = await c.fetch(
            "SELECT raw->>'MUNI_NAME' muni, count(*) n FROM parcels "
            "WHERE jurisdiction_id=$1::uuid AND city IS NULL AND raw->>'MUNI_NAME' IS NOT NULL "
            "GROUP BY raw->>'MUNI_NAME' ORDER BY n DESC", JID)
        print(f"distinct MUNI_NAME to set: {len(rows)}  (top: " +
              ", ".join(f"{r['muni']}={r['n']}" for r in rows[:6]) + ")")
        null_muni = await c.fetchval(
            "SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND city IS NULL "
            "AND (raw->>'MUNI_NAME' IS NULL OR btrim(raw->>'MUNI_NAME')='')", JID)
        print(f"parcels with NULL/blank MUNI_NAME (will stay NULL): {null_muni}")
        if not apply:
            print("[DRY-RUN] pass --apply to write.")
            return
        res = await c.execute(
            "UPDATE parcels SET city = btrim(raw->>'MUNI_NAME'), city_source='raw_muni_name' "
            "WHERE jurisdiction_id=$1::uuid AND city IS NULL "
            "AND raw->>'MUNI_NAME' IS NOT NULL AND btrim(raw->>'MUNI_NAME') <> ''", JID)
        print(f"[APPLY] {res}")
        got = await c.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND city IS NOT NULL", JID)
        tot = await c.fetchval("SELECT count(*) FROM parcels WHERE jurisdiction_id=$1::uuid", JID)
        print(f"[APPLY] city now set on {got}/{tot} ({100.0*got/tot:.1f}%)")
    finally:
        await c.close()

if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
