"""Recompute drive-time ring POPULATION for surfaced parcels using a true
per-parcel isochrone (not the bulk tract-centroid approximation), and write
ONLY the population column back.

This is the quarantined fix for the 11k-vs-49k defect. The bulk precompute
anchors every parcel on its census-tract centroid and shares one isochrone
per tract, which mis-estimates population for parcels near a tract edge /
water / county line. For the small set of parcels we actually surface, we can
afford a real per-parcel isochrone.

CRITICAL — needle stability: this writes population + computed_at ONLY. It
NEVER touches median_hhi / median_home_value / hnw_households, so the
wealth-gated needle count (which keys on dt=10 HV/HHI) cannot move. A full
refresh including those columns is a separate, deliberately-gated operation
(the bulk precompute) and is NOT done here.

Population uses the same whole-tract SUM convention as
ring_metrics_aggregation.compute_ring_metrics (total_population = Σ tract
population over intersecting tracts) so the recomputed value is consistent
with the other rings — the ONLY thing that changes is the isochrone anchor.

Surfaced set = parcel_buybox_scores rows that reach the board/digest
(lead_eligible AND score >= 70). No cross-DB access to deal_prospect needed.

USAGE (from backend/):
    python scripts/recompute_ring_population.py --limit 500
    python scripts/recompute_ring_population.py --jurisdiction <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _db import get_dsn  # noqa: E402

from app.services.census import ensure_census_tracts  # noqa: E402
from app.services.mapbox_isochrone import fetch_isochrone  # noqa: E402
from app.services.ring_metrics_precompute import DRIVE_TIMES  # noqa: E402

SURFACED_SCORE_FLOOR = 70

# Population-only UPSERT. On CONFLICT it updates population + computed_at and
# nothing else, so median_hhi/median_home_value/hnw_households are preserved.
_UPSERT_POP = text(
    """
    INSERT INTO parcel_ring_metrics (parcel_id, drive_time_minutes, population)
    VALUES (:pid, :dt, :pop)
    ON CONFLICT (parcel_id, drive_time_minutes) DO UPDATE
       SET population = EXCLUDED.population, computed_at = NOW()
    """
)

# Whole-tract population sum for an isochrone polygon (WKT), matching the
# frozen aggregation convention (sum of intersecting tracts' population).
_POP_IN_POLY = text(
    """
    SELECT COALESCE(SUM(population), 0)::int
      FROM census_tracts
     WHERE population IS NOT NULL AND population > 0
       AND ST_Intersects(geom, ST_GeomFromText(:wkt, 4326))
    """
)


async def _surfaced(db, jid: str | None, limit: int) -> list[tuple[int, float, float, str]]:
    where_j = "AND p.jurisdiction_id = :jid::uuid" if jid else ""
    rows = (await db.execute(text(
        f"""
        SELECT p.id,
               ST_X(ST_Centroid(COALESCE(p.centroid, ST_Centroid(p.geom)))) AS lng,
               ST_Y(ST_Centroid(COALESCE(p.centroid, ST_Centroid(p.geom)))) AS lat,
               p.jurisdiction_id::text AS jid
          FROM parcel_buybox_scores pbs
          JOIN parcels p ON p.id = pbs.parcel_id
         WHERE pbs.lead_eligible = TRUE
           AND pbs.score >= {SURFACED_SCORE_FLOOR}
           AND COALESCE(p.centroid, p.geom) IS NOT NULL
           {where_j}
         GROUP BY p.id, p.centroid, p.geom, p.jurisdiction_id
         ORDER BY p.id
         LIMIT :lim
        """
    ), {"jid": jid, "lim": limit})).all()
    return [(r[0], float(r[1]), float(r[2]), r[3]) for r in rows]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", type=str, default=None)
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()

    engine = create_async_engine(get_dsn(), pool_pre_ping=True)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    async with sf() as db:
        await db.execute(text("SET statement_timeout = 0"))
        parcels = await _surfaced(db, args.jurisdiction, args.limit)

    print(f"Recomputing ring population for {len(parcels)} surfaced parcel(s)…", flush=True)

    # Ensure census coverage once per jurisdiction bbox (buffered a little so a
    # 10-min isochrone spilling across the line still finds tracts).
    ensured: set[str] = set()
    fixed = failed = 0
    for i, (pid, lng, lat, jid) in enumerate(parcels, 1):
        async with sf() as db:
            await db.execute(text("SET statement_timeout = 0"))
            if jid not in ensured:
                bbox = (lng - 0.4, lat - 0.4, lng + 0.4, lat + 0.4)
                try:
                    await ensure_census_tracts(bbox, db)
                    await db.commit()
                except Exception as e:  # noqa: BLE001
                    print(f"  census ensure failed for {jid}: {e}", flush=True)
                ensured.add(jid)
            try:
                polys = await fetch_isochrone(lng, lat, contours=DRIVE_TIMES)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  [{i}/{len(parcels)}] parcel {pid} isochrone failed: {e}", flush=True)
                continue
            for dt in DRIVE_TIMES:
                geom = polys.get(dt)
                if geom is None:
                    continue
                pop = (await db.execute(_POP_IN_POLY, {"wkt": geom.wkt})).scalar() or 0
                await db.execute(_UPSERT_POP, {"pid": pid, "dt": dt, "pop": pop or None})
            await db.commit()
            fixed += 1
            if i % 50 == 0 or i == len(parcels):
                print(f"  [{i}/{len(parcels)}] recomputed", flush=True)

    await engine.dispose()
    print(f"Done. {fixed} parcels recomputed (population only), {failed} isochrone failures.",
          flush=True)


if __name__ == "__main__":
    asyncio.run(main())
