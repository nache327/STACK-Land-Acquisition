"""Advisory-locked county re-score for Union County NJ (solo — batch end).
Refreshes parcel_buybox_scores against the default self_storage filter so the
scored lead pool reflects the newly grounded matrix (needle counts were already
accurate via the direct matrix join in verify_batch).
Run: cd backend && PYTHONUTF8=1 python scripts/_rescore_union.py
"""
from __future__ import annotations
import asyncio, json, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import asyncpg  # noqa: E402
from _db import get_sync_dsn  # noqa: E402
from app.services.buybox_scoring import score_jurisdiction  # noqa: E402

JID = "16dc5ad9-8211-47c6-bfad-93bf588b15e4"  # Union County, NJ


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
    print("=== re-scoring Union County NJ …", flush=True)
    n = await score_jurisdiction(uuid.UUID(JID), fid, fj or {})
    print(f"    Union NJ: parcels_scored={n}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
