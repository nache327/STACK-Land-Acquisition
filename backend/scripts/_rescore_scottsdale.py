"""Advisory-locked re-score for Scottsdale AZ after the I-G self-storage demote (audit remediation 2026-07-15).
Refreshes parcel_buybox_scores against the default filter so the materialized lead pool drops the 11 former
I-G false needles. (Needle counts are already accurate via the direct matrix join in verify_batch.)
Run: cd backend && PYTHONUTF8=1 python scripts/_rescore_scottsdale.py
"""
from __future__ import annotations
import asyncio, json, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import asyncpg  # noqa: E402
from _db import get_sync_dsn  # noqa: E402
from app.services.buybox_scoring import score_jurisdiction  # noqa: E402

JID = "8e31ce3a-67cd-4e62-b975-a4e799b59876"  # Scottsdale, AZ


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    try:
        f = await con.fetchrow(
            "SELECT id, filter_json FROM buybox_filters WHERE is_default=true ORDER BY updated_at DESC LIMIT 1")
        if f is None:
            raise SystemExit("no default buybox filter")
        fj = f["filter_json"]
        if isinstance(fj, str):
            fj = json.loads(fj)
        fid = f["id"]
    finally:
        await con.close()
    print("=== re-scoring Scottsdale AZ …", flush=True)
    n = await score_jurisdiction(uuid.UUID(JID), fid, fj or {})
    print(f"    Scottsdale AZ: parcels_scored={n}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
