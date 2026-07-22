"""Backfill parcel_radial_metrics.population at radius 3.0 miles per jurisdiction.

This is the trustworthy "population within 3 miles" — area-weighted areal
interpolation against census_tracts, the exact math the saturation panel
computes live (census.compute_population_in_ring). Precomputing it lets the
scorer + digest apply Nache's "too rural" floor (3-mi pop < 30k) without a
live per-parcel census query.

Set-based: one INSERT…SELECT per jurisdiction (not a per-parcel loop), so a
county resolves in a single spatial GROUP BY. Ensures the jurisdiction's
census tracts are loaded first (idempotent Census upsert), then runs the
aggregate with statement_timeout disabled.

USAGE (from backend/):
    python scripts/backfill_radial_population.py                    # all
    python scripts/backfill_radial_population.py --jurisdiction <uuid>
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
    INSERT INTO parcel_radial_metrics (parcel_id, radius_miles, population)
    SELECT p.id, :radius_miles,
           -- NO coalesce-to-0: when zero populated tracts intersect the ring
           -- (a census data gap, e.g. tract population not loaded), SUM is
           -- NULL and we store NULL = "unmeasured" (passes the gate, flagged)
           -- rather than 0 = "too rural" (penalized + dropped). Only a genuine
           -- populated-tract intersection yields a number.
           SUM(
               ct.population::float
               * ST_Area(ST_Intersection(ct.geom, rg.ring)::geography)
               / NULLIF(ST_Area(ct.geom::geography), 0)
           )::int AS pop
      FROM parcels p
      CROSS JOIN LATERAL (
           SELECT ST_Buffer(p.centroid::geography, :radius_m)::geometry AS ring
      ) rg
      LEFT JOIN census_tracts ct
             ON ST_Intersects(ct.geom, rg.ring)
            AND ct.population IS NOT NULL
            AND ct.population > 0
     WHERE p.jurisdiction_id = CAST(:jid AS uuid)
       AND p.centroid IS NOT NULL
     GROUP BY p.id
    ON CONFLICT (parcel_id, radius_miles) DO UPDATE
       SET population = EXCLUDED.population, computed_at = now()
    """
)

# Second pass: competitor storage sqft within 3 miles + sqft-per-capita, using
# the same competitor_facilities distance query + default-sqft as
# saturation._compute_single_ring. Runs after the population pass so the row
# exists and prm3.population is available for the per-capita divide. Feeds the
# lane-split saturation factor in buybox_scoring.
_BACKFILL_SATURATION_SQL = text(
    """
    UPDATE parcel_radial_metrics prm
       SET competitor_sqft = sub.total_sqft,
           sqft_per_capita = CASE
               WHEN prm.population > 0 AND sub.total_sqft > 0
                    THEN ROUND(sub.total_sqft::numeric / prm.population, 2)
               WHEN prm.population > 0 THEN 0
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
    async with session_factory() as db:
        rows = (await db.execute(text(
            """
            SELECT jurisdiction_id::text, COUNT(*) AS n
              FROM parcels
             WHERE jurisdiction_id IS NOT NULL AND centroid IS NOT NULL
             GROUP BY jurisdiction_id
             ORDER BY n DESC
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


async def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill 3-mi radial population.")
    ap.add_argument("--jurisdiction", type=str, default=None)
    args = ap.parse_args()

    engine = create_async_engine(get_dsn(), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jids = await _jurisdiction_ids(session_factory, args.jurisdiction)
    print(f"Backfilling 3-mi population for {len(jids)} jurisdiction(s)…", flush=True)

    for i, jid in enumerate(jids, 1):
        t0 = time.monotonic()
        async with session_factory() as db:
            await db.execute(text("SET statement_timeout = 0"))
            bbox = await _bbox(db, jid)
            if bbox is None:
                print(f"  [{i}/{len(jids)}] {jid}  no geometry — skip", flush=True)
                continue
            # Load/refresh census coverage for the jurisdiction bbox first.
            try:
                n_tracts = await ensure_census_tracts(bbox, db)
            except Exception as e:
                print(f"  [{i}/{len(jids)}] {jid}  census fetch failed: {e}", flush=True)
                n_tracts = -1
            res = await db.execute(_BACKFILL_SQL, {
                "radius_miles": RADIUS_MILES,
                "radius_m": RADIUS_MILES * _MILES_TO_METERS,
                "jid": jid,
            })
            sat = await db.execute(_BACKFILL_SATURATION_SQL, {
                "radius_miles": RADIUS_MILES,
                "radius_m": RADIUS_MILES * _MILES_TO_METERS,
                "sqft_default": settings.competitor_sqft_default,
                "jid": jid,
            })
            await db.commit()
            print(f"  [{i}/{len(jids)}] {jid}  rows={res.rowcount}  sat={sat.rowcount}  "
                  f"tracts={n_tracts}  ({time.monotonic() - t0:.1f}s)", flush=True)

    await engine.dispose()
    print("Done.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
