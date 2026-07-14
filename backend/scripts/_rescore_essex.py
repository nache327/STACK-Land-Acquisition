"""Batch-end re-score for Essex NJ (solo county) — advisory-locked score_jurisdiction
against the default buybox filter so parcel_buybox_scores reflects the new matrix.
Run:  cd backend && PYTHONUTF8=1 python scripts/_rescore_essex.py
"""
from __future__ import annotations
import asyncio, json, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import asyncpg  # noqa: E402
from _db import get_sync_dsn  # noqa: E402
from app.services.buybox_scoring import score_jurisdiction  # noqa: E402

JID = "67541a18-c599-423b-bf05-d68153af1e2f"

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
    print("=== re-scoring Essex NJ …", flush=True)
    n = await score_jurisdiction(uuid.UUID(JID), fid, fj or {})
    print(f"    Essex NJ: parcels_scored={n}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
