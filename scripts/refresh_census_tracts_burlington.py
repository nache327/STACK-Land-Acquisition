"""One-shot: force a refresh of census_tracts coverage for Burlington
County, NJ.

Why: opening a Burlington parcel in the drawer rendered the MARKET
SATURATION panel with `Pop` 246,106 at 10 mi but `Pop 0` at 1/3/5 mi.
Root cause: the lazy `ensure_census_tracts(...)` call in
`saturation.py:86` short-circuits when ANY populated tract intersects
the bbox — but for Burlington the first lazy fetch landed some tracts
without ACS population (likely a partial fetch). Inner rings happened
to overlap the NULL-pop tracts; the 10-mile ring overlapped outer
populated tracts and rendered fine.

Fix: delete every cached `census_tracts` row whose geometry intersects
the Burlington bbox. Next time any user opens a Burlington parcel
drawer, `ensure_census_tracts(...)` will see zero cached coverage and
do a full fetch (TIGER geometries + ACS population) for the bbox.

Idempotent: re-running just re-deletes (no-op if already refetched).
Safe to run any time — only affects this jurisdiction's footprint.

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
        print(f"  bbox (padded {BBOX_PAD_DEG}°): "
              f"({xmin:.4f}, {ymin:.4f}) → ({xmax:.4f}, {ymax:.4f})")

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

        # 3. Wipe the bbox so the next lazy fetch refetches cleanly.
        result = await conn.execute(
            """
            DELETE FROM census_tracts
             WHERE ST_Intersects(
                     geom,
                     ST_MakeEnvelope($1, $2, $3, $4, 4326)
                   )
            """,
            xmin, ymin, xmax, ymax,
        )
        # `result` is e.g. "DELETE 1234"
        print(f"  {result}")

        # 4. Post-state.
        post_total = await conn.fetchval(
            """
            SELECT COUNT(*) FROM census_tracts
             WHERE ST_Intersects(
                     geom,
                     ST_MakeEnvelope($1, $2, $3, $4, 4326)
                   )
            """,
            xmin, ymin, xmax, ymax,
        )
        print(f"  post: {post_total:,} tracts remain in bbox (expect 0)")
        print()
        print("  Next step: open any Burlington parcel drawer in the UI.")
        print("  The MARKET SATURATION panel will trigger a fresh fetch of")
        print("  TIGER geometries + ACS population for the bbox; all 4 rings")
        print("  should then show non-zero Pop.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
