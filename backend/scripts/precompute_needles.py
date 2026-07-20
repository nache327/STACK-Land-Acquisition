"""Precompute wealth-gated needle metrics per jurisdiction into needle_snapshot.

The needle count is a heavy per-parcel matrix LATERAL over the wealth ring, so
the in-app needles-by-county view reads this precomputed table instead of
scanning live. Run nightly (cron / watchdog) or on demand.

Computes BOTH assets:
  - storage_needles : grounded self_storage permitted/conditional
  - lgc_needles     : LGC-effective (derived from ss/mw/li — the owner's rule)
  - lgc_incremental : LGC-viable AND storage-NOT-viable (the hidden pool)
  - storage_deals / lgc_deals : current CoStar listings sitting on a needle parcel

Wealth gate (shared): acres>=1.5, dt10 ring median_home_value>=475k &
median_hhi>=100k, human_reviewed matrix row (muni-aware LATERAL, town wins over
county default). Mirrors verify_batch + the 2026-07-17 audit query; the LGC
derivation matches services/use_verdicts.

The refresh is DELETE-all + INSERT inside one transaction, so a jurisdiction
that drops to zero needles doesn't leave a stale row.

USAGE (from backend/):  python scripts/precompute_needles.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

# LGC-effective verdict over the muni-aware LATERAL alias v (ss/mw/li). Matches
# services/use_verdicts._LGC_VERDICT_SQL — keep in sync.
_LGC_VIABLE = (
    "(v.ss IN ('permitted','conditional') OR v.mw IN ('permitted','conditional') "
    "OR v.li IN ('permitted','conditional'))"
)
_STORAGE_VIABLE = "v.ss IN ('permitted','conditional')"

_LATERAL = """
    JOIN LATERAL (
        SELECT self_storage::text AS ss, mini_warehouse::text AS mw,
               light_industrial::text AS li
          FROM zone_use_matrix m
         WHERE m.jurisdiction_id = p.jurisdiction_id
           AND m.zone_code = p.zoning_code
           AND (m.municipality IS NULL OR m.municipality = p.city)
           AND m.deleted_at IS NULL
           AND m.human_reviewed
         ORDER BY (m.municipality IS NULL) ASC
         LIMIT 1
    ) v ON true
"""
_WEALTH = ("p.acres >= 1.5 AND prm.median_home_value >= 475000 "
           "AND prm.median_hhi >= 100000")

_NEEDLES_SQL = f"""
SELECT j.id AS jid, j.name AS name, j.state AS state,
       count(*) FILTER (WHERE {_STORAGE_VIABLE})                       AS storage_needles,
       count(*) FILTER (WHERE {_LGC_VIABLE})                           AS lgc_needles,
       count(*) FILTER (WHERE {_LGC_VIABLE} AND NOT ({_STORAGE_VIABLE})) AS lgc_incremental
  FROM parcels p
  JOIN parcel_ring_metrics prm ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
  {_LATERAL}
  JOIN jurisdictions j ON j.id = p.jurisdiction_id
 WHERE {_WEALTH}
 GROUP BY j.id, j.name, j.state
HAVING count(*) FILTER (WHERE {_LGC_VIABLE}) > 0
"""

_DEALS_SQL = f"""
SELECT p.jurisdiction_id AS jid,
       count(*) FILTER (WHERE {_STORAGE_VIABLE}) AS storage_deals,
       count(*) FILTER (WHERE {_LGC_VIABLE})     AS lgc_deals
  FROM forsale_listings f
  JOIN parcels p ON p.id = f.matched_parcel_id
  JOIN parcel_ring_metrics prm ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
  {_LATERAL}
 WHERE f.is_current = true AND f.match_confidence >= 0.85 AND {_WEALTH}
 GROUP BY p.jurisdiction_id
"""

_UPSERT = """
INSERT INTO needle_snapshot (jurisdiction_id, jurisdiction_name, state,
 storage_needles, lgc_needles, lgc_incremental, storage_deals, lgc_deals, computed_at)
VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8, now())
"""


async def main() -> int:
    conn = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0)
    t0 = time.monotonic()
    try:
        await conn.execute("SET statement_timeout = 0")
        print("precompute_needles: computing needle counts…", flush=True)
        needles = await conn.fetch(_NEEDLES_SQL)
        print(f"  {len(needles)} jurisdiction(s) with LGC needles "
              f"({time.monotonic()-t0:.0f}s)", flush=True)
        print("precompute_needles: computing on-needle CoStar deals…", flush=True)
        deals = {r["jid"]: r for r in await conn.fetch(_DEALS_SQL)}
        print(f"  {len(deals)} jurisdiction(s) with on-needle deals "
              f"({time.monotonic()-t0:.0f}s)", flush=True)

        async with conn.transaction():
            await conn.execute("DELETE FROM needle_snapshot")
            for r in needles:
                d = deals.get(r["jid"])
                await conn.execute(
                    _UPSERT, r["jid"], r["name"], r["state"],
                    r["storage_needles"], r["lgc_needles"], r["lgc_incremental"],
                    d["storage_deals"] if d else 0, d["lgc_deals"] if d else 0,
                )
        tot_s = sum(r["storage_needles"] for r in needles)
        tot_l = sum(r["lgc_needles"] for r in needles)
        print(f"precompute_needles: wrote {len(needles)} rows — "
              f"storage {tot_s:,} / LGC {tot_l:,} needles "
              f"({time.monotonic()-t0:.0f}s)", flush=True)
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
