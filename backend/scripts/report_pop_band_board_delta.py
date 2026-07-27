"""Report the board-membership impact of the 3-mi population HYSTERESIS BAND.

Run AFTER the post-migration re-score completes. Answers the three questions the
re-harden has to be judged on, per board filter:

  newly hard-dropped   parcels that satisfy every OTHER board criterion but now
                       fall below floor*(1-BAND) — these leave the board. Before
                       the re-harden the population gate was soft, so nothing was
                       dropped on population at all; this is the whole delta.
  in the Verify band   between floor*(1-BAND) and floor*(1+BAND) — kept, flagged,
                       demoted to the Verify tier rather than decided by noise.
  ex-poison un-dropped parcels in the 8 jurisdictions whose pre-fix population was
                       a poisoned 0 and now measures >= the hard floor. Under the
                       re-hardened gate a stale 0 would have dropped them; the
                       migration is what saves them. This is the offset that
                       should partially cancel the new drops.

Expectation to judge against: corrected (area-weighted) population runs LOWER
than the old tract-centric values, so a MODEST net increase in sub-floor drops is
healthy and expected. A mass shift in either direction is a stop signal.

Deliberately mirrors _top_parcels_for_filter's non-population predicates rather
than re-deriving them, so the counts describe the real board.

USAGE (from backend/):
    python scripts/report_pop_band_board_delta.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402

# The 8 jurisdictions whose pre-fix rows carried the poisoned population=0.
POISON_JIDS = [
    "40b9028b-22fa-4480-803e-34aea5d3d2bd",  # Utah County, UT
    "1339c5a6-42ad-4c99-949a-ccdf8f020e95",  # Saratoga Springs, UT
    "2302220a-16b2-4dc7-965e-b78bb65573f3",  # Snohomish County, WA
    "038e93cf-4457-4f74-825d-d78f241e4724",  # Lehi, UT
    "eb8a2fc8-c0a6-4155-a4d3-d49bf46d44a6",  # Maricopa County, AZ
    "66230887-aabe-4d62-aebb-856939ba77bb",  # Fairfield County, CT
    "1f0d6f93-8e5c-462b-88ed-9d6a9e107bc1",  # Eagle Mountain, UT
    "666dc28d-a877-43bc-9763-06a100b4f89b",  # Fountain Hills, AZ
]

# Board-eligible EXCEPT for population, bucketed by where the parcel lands
# relative to the band. Mirrors the digest's other hard predicates: a current
# matched listing when requireListed, the min-score floor, acreage bounds, and
# the prohibited-verdict exclusion.
_BUCKETS = """
WITH elig AS (
    SELECT p.id,
           p.jurisdiction_id,
           prm3.population AS pop
      FROM parcel_buybox_scores pbs
      JOIN parcels p ON p.id = pbs.parcel_id
      LEFT JOIN parcel_radial_metrics prm3
             ON prm3.parcel_id = p.id AND prm3.radius_miles = 3.0
      LEFT JOIN LATERAL (
          SELECT self_storage
            FROM zone_use_matrix
           WHERE jurisdiction_id = p.jurisdiction_id
             AND zone_code = p.zoning_code
             AND (municipality IS NULL OR municipality = p.city)
             AND deleted_at IS NULL
           ORDER BY (municipality IS NULL) ASC
           LIMIT 1
      ) zum ON true
     WHERE pbs.buybox_filter_id = $1::uuid
       AND pbs.score >= $2
       AND (p.acres IS NULL OR (p.acres >= $3 AND p.acres <= $4))
       AND COALESCE(zum.self_storage::text, '') <> 'prohibited'
       AND ($5::bool IS NOT TRUE OR EXISTS (
             SELECT 1 FROM forsale_listings l
              WHERE l.matched_parcel_id = p.id
                AND l.is_current = true
                AND l.match_confidence >= 0.85))
)
SELECT count(*) FILTER (WHERE pop IS NOT NULL AND pop <  $6)              AS newly_dropped,
       count(*) FILTER (WHERE pop >= $6 AND pop < $7)                     AS verify_band,
       count(*) FILTER (WHERE pop >= $7)                                  AS clean_pass,
       count(*) FILTER (WHERE pop IS NULL)                                AS unmeasured,
       count(*)                                                           AS total,
       count(*) FILTER (WHERE pop IS NOT NULL AND pop >= $6
                          AND p_jid = ANY($8::uuid[]))                    AS expoison_saved
  FROM (SELECT id, pop, jurisdiction_id AS p_jid FROM elig) x
"""


async def main() -> int:
    conn = await asyncpg.connect(get_sync_dsn(), timeout=30)
    await conn.execute("SET statement_timeout = 0")
    try:
        filters = await conn.fetch(
            "SELECT id, name, filter_json FROM buybox_filters "
            " WHERE (filter_json->>'dashboardEnabled') = 'true' ORDER BY name")
        print(f"Board filters: {len(filters)}\n")
        grand = {"newly_dropped": 0, "verify_band": 0, "expoison_saved": 0,
                 "clean_pass": 0, "unmeasured": 0, "total": 0}
        for f in filters:
            fj = f["filter_json"]
            fj = json.loads(fj) if isinstance(fj, str) else (fj or {})
            floor = fj.get("minPop3mi")
            if not floor:
                print(f"{f['name']}: no minPop3mi configured — band not applied")
                continue
            band = 0.10  # keep in lock-step with daily_email._POP_FLOOR_BAND
            hard = int(round(floor * (1 - band)))
            soft = int(round(floor * (1 + band)))
            require_listed = bool(fj.get("requireListed"))
            min_score = 70 if require_listed else 40
            r = await conn.fetchrow(
                _BUCKETS, f["id"], min_score,
                float(fj.get("minAcres") or 0), float(fj.get("maxAcres") or 1e9),
                require_listed, hard, soft, POISON_JIDS)
            print(f"{f['name']}  (floor {floor:,}; hard <{hard:,}; band {hard:,}-{soft:,})")
            print(f"   newly hard-dropped (<{hard:,}) : {r['newly_dropped']:,}")
            print(f"   in Verify band                : {r['verify_band']:,}")
            print(f"   clean pass (>={soft:,})         : {r['clean_pass']:,}")
            print(f"   unmeasured (passes, flagged)  : {r['unmeasured']:,}")
            print(f"   ex-poison saved by migration  : {r['expoison_saved']:,}")
            print(f"   board-eligible total          : {r['total']:,}\n")
            for k in grand:
                grand[k] += r[k] or 0

        kept = grand["total"] - grand["newly_dropped"]
        pct = (100.0 * grand["newly_dropped"] / grand["total"]) if grand["total"] else 0.0
        print("=" * 62)
        print(f"NET across board filters: {grand['newly_dropped']:,} dropped of "
              f"{grand['total']:,} eligible ({pct:.1f}%); {kept:,} remain")
        print(f"  Verify band (kept, flagged): {grand['verify_band']:,}")
        print(f"  ex-poison saved            : {grand['expoison_saved']:,}")
        verdict = ("HEALTHY - modest, explainable" if pct < 25
                   else "MASS SHIFT - investigate before deleting the legacy path")
        print(f"  sanity read: {pct:.1f}% dropped -> {verdict}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
