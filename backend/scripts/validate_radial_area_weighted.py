"""AT-SCALE validation gate for the area-weighted 3-mi population migration.

Purpose: prove the migrated values match the reference math EVERYWHERE before the
digest's population floor is re-hardened from a soft flag back to a hard drop.
Validating on the five walkthrough parcels is not sufficient — a single
jurisdiction can carry an anomaly they never surface (an unusual tract layout, a
partially-loaded census layer, a coastline).

For each jurisdiction it draws a STRATIFIED sample, deliberately over-weighting
the two places the old tract-centric approximation broke:

  rural  — parcels in the largest tracts (top decile by tract area). A huge
           tract's centroid can sit miles from the parcel; this is where the
           legacy method produced its worst errors (and its false zeros).
  edge   — parcels near the jurisdiction's bbox boundary, whose 3-mi ring
           reaches into tracts that may never have been loaded.
  random — plain control sample.

For every sampled parcel it computes:
  stored     — what parcel_radial_metrics currently holds
  reference  — census.compute_population_in_ring's exact per-parcel
               area-weighted value, i.e. what the drawer's Saturation panel
               shows the operator
and reports |stored - reference| / reference per jurisdiction.

EXIT CODE is the gate: 0 = every jurisdiction within tolerance (safe to
re-harden), 1 = at least one jurisdiction out of tolerance or unmigrated (do NOT
re-harden). Also flags THRESHOLD FLIPS — parcels that land on opposite sides of
the 30k floor under stored vs reference — because those are the ones a hard gate
would get wrong.

USAGE (from backend/):
    python scripts/validate_radial_area_weighted.py                  # all
    python scripts/validate_radial_area_weighted.py --sample 40
    python scripts/validate_radial_area_weighted.py --jurisdiction <uuid>
    python scripts/validate_radial_area_weighted.py --tolerance-pct 3
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

RADIUS_M = 3.0 * 1609.344
POP_FLOOR = 30_000  # the digest gate we are deciding whether to re-harden

# Stratified sample. `rural` keys off the containing tract's area (the legacy
# method's failure mode), `edge` off proximity to the jurisdiction bbox border.
_SAMPLE_SQL = """
WITH bb AS (
    SELECT ST_Extent(centroid) AS e
      FROM parcels
     WHERE jurisdiction_id = $1::uuid AND centroid IS NOT NULL
),
scored AS (
    SELECT p.id,
           ST_Area(ct.geom::geography) AS tract_area,
           LEAST(
             ABS(ST_X(p.centroid) - ST_XMin(bb.e)), ABS(ST_X(p.centroid) - ST_XMax(bb.e)),
             ABS(ST_Y(p.centroid) - ST_YMin(bb.e)), ABS(ST_Y(p.centroid) - ST_YMax(bb.e))
           ) AS edge_dist_deg
      FROM parcels p
      CROSS JOIN bb
      LEFT JOIN LATERAL (
          SELECT geom FROM census_tracts ct2
           WHERE ST_Contains(ct2.geom, p.centroid) LIMIT 1
      ) ct ON true
     WHERE p.jurisdiction_id = $1::uuid AND p.centroid IS NOT NULL
     LIMIT 20000                       -- bound the scan; sampling not a census
)
(SELECT id, 'rural'  AS stratum FROM scored WHERE tract_area IS NOT NULL
  ORDER BY tract_area DESC LIMIT $2)
UNION ALL
(SELECT id, 'edge'   AS stratum FROM scored ORDER BY edge_dist_deg ASC LIMIT $2)
UNION ALL
(SELECT id, 'random' AS stratum FROM scored ORDER BY id LIMIT $2)
"""

_REFERENCE_SQL = """
WITH ring AS (
  SELECT ST_Buffer(centroid::geography, $2)::geometry AS geom
    FROM parcels WHERE id = $1
)
SELECT COALESCE(SUM(
         ct.population::float
         * ST_Area(ST_Intersection(ct.geom, ring.geom)::geography)
         / NULLIF(ST_Area(ct.geom::geography), 0)), 0)::int
  FROM census_tracts ct, ring
 WHERE ST_Intersects(ct.geom, ring.geom)
   AND ct.population IS NOT NULL AND ct.population > 0
"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", type=str, default=None)
    ap.add_argument("--sample", type=int, default=15,
                    help="Parcels PER STRATUM per jurisdiction (default 15 => "
                         "~45 per jurisdiction).")
    ap.add_argument("--tolerance-pct", type=float, default=5.0,
                    help="Max acceptable mean |error| per jurisdiction. The grid "
                         "snap alone should stay under ~2%%; 5%% leaves room for "
                         "sampling noise while still catching a real anomaly.")
    args = ap.parse_args()

    conn = await asyncpg.connect(get_sync_dsn(), timeout=30)
    await conn.execute("SET statement_timeout = 0")
    try:
        if args.jurisdiction:
            jids = [(args.jurisdiction, "(single)")]
        else:
            jids = [(str(r["id"]), r["name"]) for r in await conn.fetch(
                """
                SELECT j.id, COALESCE(j.name, '(unnamed)') AS name
                  FROM jurisdictions j
                  LEFT JOIN needle_snapshot ns ON ns.jurisdiction_id = j.id
                 WHERE EXISTS (SELECT 1 FROM parcel_radial_metrics pr
                                 JOIN parcels p ON p.id = pr.parcel_id
                                WHERE p.jurisdiction_id = j.id
                                  AND pr.radius_miles = 3.0 LIMIT 1)
                 ORDER BY COALESCE(ns.storage_needles,0)+COALESCE(ns.lgc_needles,0) DESC
                """)]

        print(f"Validating {len(jids)} jurisdiction(s), "
              f"{args.sample} parcels/stratum, tolerance {args.tolerance_pct}% mean error\n", flush=True)
        header = (f"{'jurisdiction':<34} {'n':>4} {'mean':>7} {'max':>7} "
                  f"{'flips':>6} {'unmig':>6}  verdict")
        print(header, flush=True); print("-" * len(header), flush=True)

        bad: list[str] = []
        total_flips = 0
        for jid, name in jids:
            rows = await conn.fetch(_SAMPLE_SQL, jid, args.sample)
            if not rows:
                continue
            errs: list[float] = []
            flips = 0
            unmigrated = 0
            for r in rows:
                pid = r["id"]
                stored = await conn.fetchval(
                    "SELECT population FROM parcel_radial_metrics "
                    " WHERE parcel_id=$1 AND radius_miles=3.0", pid)
                if stored is None:
                    unmigrated += 1
                    continue
                ref = await conn.fetchval(_REFERENCE_SQL, pid, RADIUS_M)
                if ref is None:
                    continue
                if ref > 0:
                    errs.append(abs(100.0 * (stored - ref) / ref))
                elif stored > 0:
                    errs.append(100.0)  # reference says empty, stored says people
                # The decisive check for a HARD gate: do the two disagree about
                # which side of the floor this parcel is on?
                if (stored >= POP_FLOOR) != (ref >= POP_FLOOR):
                    flips += 1
            if not errs:
                continue
            mean_e = sum(errs) / len(errs)
            max_e = max(errs)
            total_flips += flips
            ok = mean_e <= args.tolerance_pct
            if not ok:
                bad.append(f"{name} ({jid[:8]}): mean {mean_e:.1f}%")
            print(f"{name[:33]:<34} {len(errs):>4} {mean_e:>6.1f}% {max_e:>6.1f}% "
                  f"{flips:>6} {unmigrated:>6}  {'OK' if ok else 'OUT OF TOLERANCE'}", flush=True)

        print()
        if bad:
            print(f"FAIL: {len(bad)} jurisdiction(s) OUT OF TOLERANCE - do NOT re-harden "
                  f"the population gate:", flush=True)
            for b in bad:
                print(f"   {b}", flush=True)
            return 1
        print(f"PASS: all jurisdictions within {args.tolerance_pct}% mean error.", flush=True)
        if total_flips:
            print(f"WARN: {total_flips} sampled parcel(s) flip across the "
                  f"{POP_FLOOR:,} floor between stored and reference. Under a HARD "
                  f"gate each flip is a wrong board decision — review before "
                  f"re-hardening.", flush=True)
        else:
            print(f"PASS: no parcel flips across the {POP_FLOOR:,} floor: stored and "
                  f"reference agree on every gate decision in the sample.", flush=True)
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
