"""Batch-end re-score for Middlesex NJ (solo county) — advisory-locked score_jurisdiction
against the default buybox filter. Run: cd backend && PYTHONUTF8=1 python scripts/_rescore_middlesex.py
"""
from __future__ import annotations
import asyncio, json, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import asyncpg  # noqa: E402
from _db import get_sync_dsn  # noqa: E402
from app.services.buybox_scoring import score_jurisdiction  # noqa: E402

JID = "9c039328-c995-41fc-83ce-fb4966fd402b"

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
    print("=== re-scoring Middlesex NJ …", flush=True)
    n = await score_jurisdiction(uuid.UUID(JID), fid, fj or {})
    print(f"    Middlesex NJ: parcels_scored={n}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
