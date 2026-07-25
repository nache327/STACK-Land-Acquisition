"""Backfill parcel_radial_metrics @ radius 3.0 miles per jurisdiction.

Precomputes the "population within 3 miles" that the scorer's too-rural factor
and the digest's minPop3mi gate read, so neither needs a live census query.

WHAT THIS ACTUALLY COMPUTES (do not mistake it for the panel's number):
a TRACT-CENTRIC approximation — the 3-mile ring population is computed once per
census-tract centroid and assigned to every parcel that tract contains, summing
each neighbouring tract's FULL population when its centroid falls inside the
ring. It is NOT `census.compute_population_in_ring`, which buffers the PARCEL
and area-weights each tract by its intersection share; the drawer's Saturation
panel shows that one. The two therefore disagree — most in rural/large-tract
geographies — while wearing the same "3-mi population" label, which is a live
trust bug (a card can read "12,400 < 30,000 floor  -20" beside a panel saying
49,000). Making them one number is a follow-up: compute per-parcel
area-weighted, batched by snapped centroid for speed.

The earlier form of this docstring claimed the two were "the exact same math",
which is what let the divergence go unnoticed.

Set-based: one INSERT…SELECT per jurisdiction (not a per-parcel loop). Ensures
census tracts are loaded first (idempotent upsert), then runs with
statement_timeout disabled. Resumable — re-running skips jurisdictions that
already have rows unless --redo.

USAGE (from backend/):
    python scripts/backfill_radial_population.py                    # all
    python scripts/backfill_radial_population.py --jurisdiction <uuid>
    python scripts/backfill_radial_population.py --skip-saturation
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _db import get_dsn  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.census import ensure_census_tracts  # noqa: E402

RADIUS_MILES = 3.0
_MILES_TO_METERS = 1609.344

# Area-weighted areal interpolation — mirrors census.compute_population_in_ring,
# but batched over every parcel in a jurisdiction and written to the table.
_BACKFILL_SQL = text(
    """
    -- Tract-centric (matches the drive-time ring precompute convention): the
    -- 3-mile ring population is computed ONCE per census tract centroid, then
    -- assigned to every parcel that tract contains. This is O(tracts² +
    -- parcels) with index-assisted lookups instead of the O(parcels × tracts)
    -- per-parcel buffer+area-weight (which took 35+ min on a single big
    -- county). The bbox envelope bounds the tract set to the jurisdiction plus
    -- a ~7mi margin so a 3-mile ring near the edge still sees its neighbours.
    --
    -- NULL semantics — load-bearing, because a measured value below the floor is
    -- HARD-DROPPED from the board while NULL only earns a soft flag. So a value
    -- may only be written when we can actually measure it:
    --   * parcel not contained by any loaded tract  -> no row  -> NULL
    --   * parcel's own tract has UNKNOWN population -> no row  -> NULL
    --     (tc_all requires population IS NOT NULL). Without this the ring sum
    --     silently EXCLUDED the parcel's own residents — a systematic
    --     understatement, and 0 ("genuinely rural") whenever no populated
    --     neighbour happened to fall within 3mi.
    --   * own tract known, no populated tract within 3mi -> 0 = really rural.
    -- The caller additionally skips the whole jurisdiction when the census load
    -- failed or the bbox holds no populated tracts, so an ACS outage can't write
    -- 0 across an entire county.
    WITH tc_all AS (
        SELECT geoid, ST_Centroid(geom)::geography AS gc
          FROM census_tracts
         WHERE geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
           AND population IS NOT NULL
    ),
    tc_pop AS (
        SELECT geoid, ST_Centroid(geom)::geography AS gc, population
          FROM census_tracts
         WHERE population IS NOT NULL AND population > 0
           AND geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
    ),
    ring_pop AS (
        SELECT a.geoid, COALESCE(SUM(b.population), 0)::int AS pop
          FROM tc_all a
          LEFT JOIN tc_pop b ON ST_DWithin(a.gc, b.gc, :radius_m)
         GROUP BY a.geoid
    )
    INSERT INTO parcel_radial_metrics (parcel_id, radius_miles, population)
    SELECT p.id, :radius_miles, rp.pop
      FROM parcels p
      JOIN LATERAL (
           SELECT ct.geoid FROM census_tracts ct
            WHERE ST_Contains(ct.geom, p.centroid)
            LIMIT 1
      ) pt ON true
      JOIN ring_pop rp ON rp.geoid = pt.geoid
     WHERE p.jurisdiction_id = CAST(:jid AS uuid)
       AND p.centroid IS NOT NULL
    ON CONFLICT (parcel_id, radius_miles) DO UPDATE
       SET population = EXCLUDED.population, computed_at = now()
    """
)

# Second pass: competitor storage sqft within 3 miles + sqft-per-capita, using
# the same competitor_facilities distance query + default-sqft as
# saturation._compute_single_ring. Runs after the population pass so the row
# exists and prm3.population is available for the per-capita divide. Feeds the
# lane-split saturation factor in buybox_scoring.
#
# PRECONDITION (enforced by the caller via _has_competitor_coverage): this only
# runs for a geography that HAS competitor facilities. That is what makes the
# `THEN 0` branch below honest — with coverage present, a parcel with no
# competitor inside 3mi really is underserved, and the +8 bonus is earned. Run it
# without that guard and every parcel in an unsynced county gets 0, i.e. the best
# possible market score for a market nobody measured.
_BACKFILL_SATURATION_SQL = text(
    """
    UPDATE parcel_radial_metrics prm
       SET competitor_sqft = sub.total_sqft,
           sqft_per_capita = CASE
               WHEN prm.population > 0 AND sub.total_sqft > 0
                    THEN ROUND(sub.total_sqft::numeric / prm.population, 2)
               -- genuinely zero competitors nearby (coverage confirmed by caller)
               WHEN prm.population > 0 THEN 0
               -- population unmeasured/zero -> per-capita is undefined, not 0
               ELSE NULL END,
           computed_at = now()
      FROM (
          SELECT p.id AS parcel_id,
                 COALESCE(SUM(COALESCE(cf.sq_ft, :sqft_default)), 0)::bigint AS total_sqft
            FROM parcels p
            LEFT JOIN competitor_facilities cf
              ON ST_DWithin(cf.geom::geography, p.centroid::geography, :radius_m)
           WHERE p.jurisdiction_id = CAST(:jid AS uuid)
             AND p.centroid IS NOT NULL
           GROUP BY p.id
      ) sub
     WHERE prm.parcel_id = sub.parcel_id
       AND prm.radius_miles = :radius_miles
    """
)


async def _jurisdiction_ids(session_factory, only: str | None) -> list[str]:
    if only:
        return [only]
    # Enumerate from the small jurisdictions table (instant) rather than a
    # GROUP BY over all ~millions of parcels (which blows the statement
    # timeout). Order by needle count so board-relevant counties process
    # first — if the long tail runs late, the data that matters is already in.
    # Empty jurisdictions are cheap-skipped later (bbox None).
    async with session_factory() as db:
        await db.execute(text("SET statement_timeout = 0"))
        rows = (await db.execute(text(
            """
            SELECT j.id::text
              FROM jurisdictions j
              LEFT JOIN needle_snapshot ns ON ns.jurisdiction_id = j.id
             ORDER BY COALESCE(ns.storage_needles, 0) + COALESCE(ns.lgc_needles, 0) DESC,
                      j.id
            """
        ))).all()
    return [r[0] for r in rows]


async def _bbox(db, jid: str) -> tuple[float, float, float, float] | None:
    row = (await db.execute(text(
        """
        SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)
          FROM (SELECT ST_Extent(centroid) AS e FROM parcels
                 WHERE jurisdiction_id = CAST(:jid AS uuid) AND centroid IS NOT NULL) s
        """
    ), {"jid": jid})).first()
    if not row or row[0] is None:
        return None
    return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))


async def _populated_tracts_in_env(db, env: dict) -> int:
    """How many tracts inside the (buffered) bbox carry a usable population.

    Zero means the census layer is unusable for this jurisdiction — either the
    ACS merge never landed or the fetch failed — and the backfill MUST NOT run:
    every parcel would be written 0, which the digest reads as "genuinely rural"
    and hard-drops. Cheap: census_tracts is small and && uses the GiST index.
    """
    row = (await db.execute(text(
        """
        SELECT COUNT(*) FROM census_tracts
         WHERE geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
           AND population IS NOT NULL AND population > 0
        """
    ), env)).first()
    return int(row[0]) if row else 0


async def _has_competitor_coverage(db, env: dict) -> bool:
    """True when at least one competitor facility sits inside the jurisdiction's
    (buffered) bbox.

    Guards the saturation pass. `competitor_facilities` is populated by an
    operator-triggered per-jurisdiction sync, so in a county where that sync
    never ran the SUM is 0 -> sqft_per_capita 0 -> which every consumer reads as
    the BEST possible market: the scorer adds SAT_UNDERSERVED_BONUS (+8) and the
    drawer paints a green "Underserved" badge. Unmeasured must stay NULL.

    Bbox-based (not per-parcel ST_DWithin) so it's a single GiST probe rather
    than a competitor x parcel join.
    """
    row = (await db.execute(text(
        """
        SELECT EXISTS (
            SELECT 1 FROM competitor_facilities cf
             WHERE cf.geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
        )
        """
    ), env)).first()
    return bool(row[0]) if row else False


async def _already_done(db, jid: str) -> bool:
    """True if this jurisdiction already has 3-mi radial rows. Each jurisdiction
    commits atomically (one transaction), so 'has any row' == 'fully done' —
    this makes the whole backfill resumable: re-running skips completed
    jurisdictions and continues where an interrupted run left off."""
    result = await db.execute(text(
        """
        SELECT EXISTS (
            SELECT 1 FROM parcel_radial_metrics pr
              JOIN parcels p ON p.id = pr.parcel_id
             WHERE p.jurisdiction_id = CAST(:jid AS uuid)
               AND pr.radius_miles = 3.0
             LIMIT 1
        )
        """
    ), {"jid": jid})
    return bool(result.scalar())


async def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill 3-mi radial population.")
    ap.add_argument("--jurisdiction", type=str, default=None)
    ap.add_argument("--skip-saturation", action="store_true",
                    help="Population pass only. The competitor-sqft pass is an "
                         "O(parcels x competitors) join that can stall for many "
                         "minutes on a large metro; population is what drives the "
                         "3-mi floor, so it can land first and saturation run "
                         "separately.")
    ap.add_argument("--redo", action="store_true",
                    help="Reprocess jurisdictions even if already backfilled "
                         "(default: skip done ones so the run is resumable).")
    args = ap.parse_args()

    # NullPool: hold NO idle connections between jurisdictions. The script is
    # sequential (one session at a time), so a persistent pool buys nothing and
    # risks leaking session-mode connections into Supabase's pooler if the
    # process is killed mid-run — which is exactly how a long backfill once
    # exhausted the pool and crashloop-ed Railway's boot migrations. With
    # NullPool an abrupt kill leaks at most one connection.
    engine = create_async_engine(get_dsn(), poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jids = await _jurisdiction_ids(session_factory, args.jurisdiction)
    print(f"Backfilling 3-mi population for {len(jids)} jurisdiction(s)…", flush=True)

    for i, jid in enumerate(jids, 1):
        t0 = time.monotonic()
        async with session_factory() as db:
            await db.execute(text("SET statement_timeout = 0"))
            if not args.redo and await _already_done(db, jid):
                print(f"  [{i}/{len(jids)}] {jid}  already done — skip", flush=True)
                continue
            bbox = await _bbox(db, jid)
            if bbox is None:
                print(f"  [{i}/{len(jids)}] {jid}  no geometry — skip", flush=True)
                continue
            # Load/refresh census coverage for the jurisdiction bbox first.
            census_failed = False
            try:
                n_tracts = await ensure_census_tracts(bbox, db)
            except Exception as e:
                print(f"  [{i}/{len(jids)}] {jid}  census fetch failed: {e}", flush=True)
                n_tracts = -1
                census_failed = True
            # Expand the bbox ~0.12° (~8mi > the 3mi ring) so an edge parcel's
            # ring still sees neighbouring tracts.
            xmin, ymin, xmax, ymax = bbox
            m = 0.12
            env = {"xmin": xmin - m, "ymin": ymin - m,
                   "xmax": xmax + m, "ymax": ymax + m}

            # HARD PRECONDITION: never write when we can't measure. A measured
            # population below the 30k floor is a hard board drop, so writing 0
            # for a county whose ACS load failed silently removed every one of
            # its parcels from the board. Previously this path logged the failure
            # and ran the INSERT anyway, and _already_done() then marked the
            # poisoned county complete forever (only --redo would revisit it).
            populated = await _populated_tracts_in_env(db, env)
            if census_failed or populated == 0:
                why = "census fetch failed" if census_failed else "no populated tracts in bbox"
                print(
                    f"  [{i}/{len(jids)}] {jid}  SKIPPED ({why}) — leaving population "
                    f"NULL rather than writing 0; re-run once census data loads",
                    flush=True,
                )
                continue

            res = await db.execute(_BACKFILL_SQL, {
                "radius_miles": RADIUS_MILES,
                "radius_m": RADIUS_MILES * _MILES_TO_METERS,
                "jid": jid,
                **env,
            })
            # Saturation: only when this geography actually HAS competitor data.
            # Otherwise leave sqft_per_capita NULL — "not measured" — instead of
            # writing 0, which reads as a perfectly underserved market (+8 score
            # bonus, green badge) for every storage parcel in the county.
            sat_rc: object = "skipped"
            if args.skip_saturation:
                sat_rc = "skipped (--skip-saturation)"
            elif not await _has_competitor_coverage(db, env):
                sat_rc = "skipped (no competitor data — left NULL)"
            else:
                sat = await db.execute(_BACKFILL_SATURATION_SQL, {
                    "radius_miles": RADIUS_MILES,
                    "radius_m": RADIUS_MILES * _MILES_TO_METERS,
                    "sqft_default": settings.competitor_sqft_default,
                    "jid": jid,
                })
                sat_rc = sat.rowcount
            await db.commit()
            print(f"  [{i}/{len(jids)}] {jid}  rows={res.rowcount}  sat={sat_rc}  "
                  f"tracts={n_tracts}  ({time.monotonic() - t0:.1f}s)", flush=True)

    await engine.dispose()
    print("Done.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
