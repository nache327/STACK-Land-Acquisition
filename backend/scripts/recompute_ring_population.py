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
import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

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
    where_j = "AND p.jurisdiction_id = CAST(:jid AS uuid)" if jid else ""
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


async def _by_ids(db, ids: list[int]) -> list[tuple[int, float, float, str]]:
    """Resolve an explicit parcel-id list (the --ids / detector-pipe path)."""
    rows = (await db.execute(text(
        """
        SELECT p.id,
               ST_X(ST_Centroid(COALESCE(p.centroid, ST_Centroid(p.geom)))) AS lng,
               ST_Y(ST_Centroid(COALESCE(p.centroid, ST_Centroid(p.geom)))) AS lat,
               p.jurisdiction_id::text AS jid
          FROM parcels p
         WHERE p.id = ANY(:ids)
           AND COALESCE(p.centroid, p.geom) IS NOT NULL
         ORDER BY p.id
        """
    ), {"ids": ids})).all()
    return [(r[0], float(r[1]), float(r[2]), r[3]) for r in rows]


_QUARANTINE = """
QUARANTINED — do not run this script.

It writes POPULATION ONLY and stamps computed_at = NOW():

    ON CONFLICT (parcel_id, drive_time_minutes) DO UPDATE
       SET population = EXCLUDED.population, computed_at = NOW()

median_home_value and median_hhi are left exactly as they were — including NULL,
including stale, including wrong. The fresh stamp then tells every staleness
detector (the ring API's 90d filter, the drawer's 180d banner,
detect_stale_ring_metrics) that the row is current. That is the audit's TRUST TRAP:
the row looks repaired while the wealth gate still fails on NULL, so the parcel
silently drops out of the needle count and reads as a FINDING rather than a defect.

This is not hypothetical. A 2026-07-29 census found 69,347 rows carrying a non-epoch
stamp with NULL wealth — 5,558 at dt=10, of which 3,311 are population-present, which
is precisely this script's signature.

Note it also crashes on the async-driver trap (create_async_engine on a sync DSN).
Do NOT "fix" that and run it — the crash is the only thing that has been stopping it.

USE INSTEAD:
    python scripts/repair_dt10_rings.py --jurisdiction <uuid>

which recomputes population AND wealth together from the same isochrone, advances
computed_at only when all three gate-bearing metrics landed, and writes the epoch
sentinel to_timestamp(0) when they did not — so a NULL-wealth row can never carry a
stamp that claims otherwise. It is capture-first and revertible.

If you genuinely need population-only for a one-off, understand that you are
re-creating the trust trap, and set RECOMPUTE_RING_POP_I_ACCEPT_TRUST_TRAP=1.
"""


async def main() -> None:
    if os.getenv("RECOMPUTE_RING_POP_I_ACCEPT_TRUST_TRAP") != "1":
        print(_QUARANTINE, flush=True)
        sys.exit(3)

    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", type=str, default=None)
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--ids", type=str, default=None,
                    help="Comma-separated parcel ids, or '-' to read whitespace-"
                         "separated ids from stdin. This is the documented pipe "
                         "target of detect_stale_ring_metrics.py --ids-only, "
                         "which previously had nowhere to pipe TO: this script "
                         "only ever selected its own surfaced set.")
    args = ap.parse_args()

    explicit_ids: list[int] | None = None
    if args.ids:
        raw = sys.stdin.read() if args.ids.strip() == "-" else args.ids
        explicit_ids = [int(tok) for tok in raw.replace(",", " ").split() if tok.strip()]
        if not explicit_ids:
            print("--ids given but no parcel ids parsed", flush=True)
            return

    # get_sync_dsn (session mode, :5432) NOT get_dsn: on the TRANSACTION pooler
    # (:6543) a `SET statement_timeout = 0` applies only to the current implicit
    # transaction, so the heavy _surfaced scan below then ran under the server
    # default and was killed. That is the real cause of this script "timing out".
    # NullPool for the same leak-safety reason as backfill_radial_population.
    engine = create_async_engine(get_sync_dsn(), poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    async with sf() as db:
        await db.execute(text("SET statement_timeout = 0"))
        parcels = (
            await _by_ids(db, explicit_ids) if explicit_ids is not None
            else await _surfaced(db, args.jurisdiction, args.limit)
        )

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
                # Write `pop` AS COMPUTED. `pop or None` turned a legitimate 0
                # into NULL and the UPSERT's DO UPDATE then overwrote a
                # previously-good population with NULL. A 0 from a real isochrone
                # is a finding worth recording; skip only a genuine None.
                if pop is None:
                    continue
                await db.execute(_UPSERT_POP, {"pid": pid, "dt": dt, "pop": pop})
            await db.commit()
            fixed += 1
            if i % 50 == 0 or i == len(parcels):
                print(f"  [{i}/{len(parcels)}] recomputed", flush=True)

    await engine.dispose()
    print(f"Done. {fixed} parcels recomputed (population only), {failed} isochrone failures.",
          flush=True)


if __name__ == "__main__":
    asyncio.run(main())
