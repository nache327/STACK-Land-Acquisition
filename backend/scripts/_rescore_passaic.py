"""Advisory-locked county re-score for Passaic NJ (solo county, batch end).

Runs score_jurisdiction against the default self_storage buybox filter so
parcel_buybox_scores reflects the batch-1 Wayne/Hawthorne/Wanaque grounding.
(Needle counts are already accurate via the direct matrix join in verify_batch;
this refreshes the product's scored table.)
"""
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

JID = "7a9ed95d-df89-4864-a203-f831a987b562"


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    try:
        f = await con.fetchrow(
            "SELECT id, filter_json FROM buybox_filters WHERE is_default=true "
            "ORDER BY updated_at DESC LIMIT 1")
        if f is None:
            raise SystemExit("no default buybox filter")
        fj = f["filter_json"]
        if isinstance(fj, str):
            fj = json.loads(fj)
        fid = f["id"]
    finally:
        await con.close()
    print("=== re-scoring Passaic County, NJ …", flush=True)
    n = await score_jurisdiction(uuid.UUID(JID), fid, fj or {})
    print(f"    Passaic: parcels_scored={n}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
