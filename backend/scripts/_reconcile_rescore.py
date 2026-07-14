"""Reconcile re-score (Nache-approved 2026-07-14) for the two shared counties
that were mined by two sessions with per-batch re-score skipped. Runs the
advisory-locked score_jurisdiction against the default self_storage filter so
parcel_buybox_scores reflects the full merged matrix (needle counts were already
accurate via the direct matrix join)."""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402
from _db import get_sync_dsn  # noqa: E402
from app.services.buybox_scoring import score_jurisdiction  # noqa: E402

JIDS = {
    "Chester PA": "7f5293ff-13e8-4641-a420-49bccb13b407",
    "Morris NJ": "746b7604-f362-470f-aa42-70dc8973b4ee",
}


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

    for name, jid in JIDS.items():
        print(f"=== re-scoring {name} …", flush=True)
        n = await score_jurisdiction(uuid.UUID(jid), fid, fj or {})
        print(f"    {name}: parcels_scored={n}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
