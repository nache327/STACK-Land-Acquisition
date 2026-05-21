"""One-shot: force a refresh of census_tracts coverage for Burlington
County, NJ.

Why: opening a Burlington parcel in the drawer rendered the MARKET
SATURATION panel with `Pop` 246,106 at 10 mi but `Pop 0` at 1/3/5 mi.

Root cause (confirmed via diagnostic 2026-05-21): Burlington County NJ
(FIPS 34-005) has only ~8 of its ~110 census tracts cached. The bbox
also intersects Philadelphia (PA-42-101 has 406 tracts cached) and
neighboring NJ counties, so `ensure_census_tracts(...)` sees 638
populated tracts in the bbox and short-circuits — it never realises
that Burlington itself is barely covered. Inner rings (1/3/5 mi)
around mid-county parcels find ZERO intersecting tracts and the
weighted-sum returns 0. The 10-mi ring reaches Philly+Camden tracts
and renders 246K.

Fix: age out the `fetched_at` column for every tract whose geometry
intersects the Burlington bbox. The cache-coverage check filters on
`fetched_at > 90-days-ago`, so this makes the check return 0 → the
service re-fetches the full TIGER + ACS bbox → INSERTs the missing
Burlington tracts and UPDATEs the existing rows via ON CONFLICT.

No DELETE, no data loss — only the staleness timestamp is moved
backwards. Re-running is idempotent (no-op once tracts have been
re-fetched and their `fetched_at` is fresh again).

Verification afterwards:
  1. Open any Burlington parcel drawer.
  2. MARKET SATURATION should show non-zero Pop for all 4 rings.
"""
from __future__ import annotations

import asyncio
import sys

import asyncpg

DB_URL = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
BURLINGTON_JID = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"

# Pad the parcel bbox by 0.20° (~14 mi) to match the lazy-fetch radius
# used by the saturation service so the 10-mile ring's edges still
# have tracts to intersect after refetch.
BBOX_PAD_DEG = 0.20


async def main() -> int:
    conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
    try:
        # 1. Bbox from parcel centroids.
        row = await conn.fetchrow(
            """
            SELECT
                ST_XMin(ST_Extent(centroid)) AS xmin,
                ST_YMin(ST_Extent(centroid)) AS ymin,
                ST_XMax(ST_Extent(centroid)) AS xmax,
                ST_YMax(ST_Extent(centroid)) AS ymax,
                COUNT(*) AS n_parcels
              FROM parcels
             WHERE jurisdiction_id = $1::uuid
               AND centroid IS NOT NULL
            """,
            BURLINGTON_JID,
        )
        if not row or row["xmin"] is None:
            print("  no parcels with centroids — aborting")
            return 1
        xmin = float(row["xmin"]) - BBOX_PAD_DEG
        ymin = float(row["ymin"]) - BBOX_PAD_DEG
        xmax = float(row["xmax"]) + BBOX_PAD_DEG
        ymax = float(row["ymax"]) + BBOX_PAD_DEG
        print(f"  jurisdiction: Burlington County, NJ ({row['n_parcels']:,} parcels)")
        print(f"  bbox (padded {BBOX_PAD_DEG} deg): "
              f"({xmin:.4f}, {ymin:.4f}) -> ({xmax:.4f}, {ymax:.4f})")

        # 2. Pre-state breakdown.
        pre = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE population IS NULL) AS null_pop,
                COUNT(*) FILTER (WHERE population IS NOT NULL) AS with_pop
              FROM census_tracts
             WHERE ST_Intersects(
                     geom,
                     ST_MakeEnvelope($1, $2, $3, $4, 4326)
                   )
            """,
            xmin, ymin, xmax, ymax,
        )
        print(f"  pre:  {pre['total']:,} tracts in bbox "
              f"({pre['with_pop']:,} populated, {pre['null_pop']:,} NULL-pop)")

        # 3. Age out fetched_at so the cache-coverage check returns 0.
        # The check is "fetched_at > now() - 90 days AND population IS NOT
        # NULL AND ST_Intersects(bbox)". We set fetched_at to epoch so
        # the cutoff filter excludes every tract; the next lazy call
        # then re-fetches TIGER+ACS for the whole bbox and INSERTs the
        # ~100 missing Burlington tracts (UPSERT on geoid handles the
        # existing rows).
        result = await conn.execute(
            """
            UPDATE census_tracts
               SET fetched_at = TIMESTAMPTZ 'epoch'
             WHERE ST_Intersects(
                     geom,
                     ST_MakeEnvelope($1, $2, $3, $4, 4326)
                   )
            """,
            xmin, ymin, xmax, ymax,
        )
        # `result` is e.g. "UPDATE 638"
        print(f"  {result}")

        # 4. Post-state — these rows are now considered stale.
        nj_005 = await conn.fetchval(
            "SELECT COUNT(*) FROM census_tracts WHERE state_fips='34' AND county_fips='005'"
        )
        print(f"  NJ-005 (Burlington Co.) tracts currently in DB: {nj_005}")
        print()
        print("  Next step: open any Burlington parcel drawer in the UI.")
        print("  The MARKET SATURATION panel will trigger a fresh fetch of")
        print("  TIGER geometries + ACS population for the bbox; missing")
        print("  Burlington tracts will be INSERTed and all 4 rings should")
        print("  then show non-zero Pop.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
