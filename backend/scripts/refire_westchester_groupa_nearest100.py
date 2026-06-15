"""Group A re-fire on Westchester sub-coverage munis at nearest_within_meters=100.

Background: PR #238 ingested 37 Westchester munis. 5 fell below the 70 %
coverage gate. Task 6 diagnostic (PR #241) found that 3 of them
(Bedford / Port Chester / Yorktown — "Group A") can clear both gates
(coverage ≥ 70 %, nearest_* share < 30 %) if the nearest fallback is
extended from 50 m to 100 m. The other 2 (North Salem, Somers — Group B)
cannot clear both gates at any nearest threshold; those stay as-is.

This script is the Group A re-fire. **Pass-2-only** by design:

  - zoning_districts already loaded for these munis (PR #238); no
    re-INSERT.
  - Pass 1 (ST_Within contained) already ran in PR #238; no re-stamp
    of already-bound parcels.
  - This script only does Pass 2: ST_DWithin nearest_100m fallback,
    scoped to parcels still NULL on `zone_binding_method`.

Run:

  python3 backend/scripts/refire_westchester_groupa_nearest100.py \
      --i-know-this-writes-to-prod

The script halts per-muni on any anomaly and reports counts.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

logger = logging.getLogger("wc_groupa_refire")

WESTCHESTER_JID = uuid.UUID("3e706886-919f-4ecf-b5aa-567040e295e8")

# (muni_name as stamped in raw_attributes, prod_city_value as
#  used on parcels.city). Both must be supplied separately per
#  the PR #233 collision-fix lesson.
GROUP_A = [
    ("Bedford",      "Bedford"),
    ("Port Chester", "Port Chester"),
    ("Yorktown",     "Yorktown"),
]
NEAREST_M = 100.0


def _session_db_url() -> str:
    return settings.database_url.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _refire_one(
    conn: asyncpg.Connection,
    muni_name: str,
    city: str,
    nearest_m: float,
) -> dict[str, int]:
    """Pass-2-only nearest_<N>m re-fire for a single muni.

    Only updates parcels whose `zone_binding_method` is still NULL —
    i.e. unmatched at PR #238 fire time. Already-bound parcels keep
    their `contained` or `nearest_50m` binding.
    """
    binding_label = f"nearest_{int(round(nearest_m))}m"
    # First, observe state.
    before = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE zone_binding_method IS NOT NULL) AS bound,
            COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
            COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest,
            COUNT(*) FILTER (WHERE zone_binding_method IS NULL) AS unmatched
        FROM parcels
        WHERE jurisdiction_id = $1::uuid AND city = $2 AND geom IS NOT NULL
        """, str(WESTCHESTER_JID), city,
    )
    logger.info(
        "%s — before: total=%d bound=%d contained=%d nearest=%d unmatched=%d",
        muni_name, before["total"], before["bound"], before["contained"],
        before["nearest"], before["unmatched"],
    )

    # Pass-2-only UPDATE. Same shape as the production
    # ingest_westchester_class_b_proof._fire pass-2 query, scoped to
    # currently-unmatched parcels only.
    status = await conn.execute(
        """
        UPDATE parcels target
        SET zone_class = sub.zone_class,
            zone_binding_method = $4,
            zoning_code = COALESCE(NULLIF(target.zoning_code, ''), sub.zone_code)
        FROM (
            SELECT p.id AS parcel_id, m.zone_class, m.zone_code
            FROM parcels p,
            LATERAL (
                SELECT zd.zone_class, zd.zone_code
                FROM zoning_districts zd
                WHERE zd.jurisdiction_id = $1::uuid
                  AND zd.raw_attributes->>'muni_name' = $2
                  AND zd.geom IS NOT NULL
                  AND ST_DWithin(
                      zd.geom::geography,
                      ST_Centroid(p.geom)::geography,
                      $5
                  )
                ORDER BY ST_Distance(
                    zd.geom::geography,
                    ST_Centroid(p.geom)::geography
                )
                LIMIT 1
            ) m
            WHERE p.jurisdiction_id = $1::uuid
              AND p.city = $3
              AND p.geom IS NOT NULL
              AND p.zone_binding_method IS NULL
        ) sub
        WHERE target.id = sub.parcel_id
        """,
        str(WESTCHESTER_JID), muni_name, city, binding_label, float(nearest_m),
    )
    try:
        n_updated = int(status.split()[-1])
    except (ValueError, IndexError):
        n_updated = -1
    logger.info("%s — Pass 2 %s: UPDATEd %d parcels", muni_name, binding_label, n_updated)

    after = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE zone_binding_method IS NOT NULL) AS bound,
            COUNT(*) FILTER (WHERE zone_binding_method = 'contained') AS contained,
            COUNT(*) FILTER (WHERE zone_binding_method LIKE 'nearest_%') AS nearest,
            COUNT(*) FILTER (WHERE zone_binding_method IS NULL) AS unmatched
        FROM parcels
        WHERE jurisdiction_id = $1::uuid AND city = $2 AND geom IS NOT NULL
        """, str(WESTCHESTER_JID), city,
    )
    cov = after["bound"] / after["total"] * 100 if after["total"] else 0
    near_share = after["nearest"] / after["bound"] * 100 if after["bound"] else 0
    logger.info(
        "%s — after: bound=%d (cov %.2f%%), nearest share %.2f%%",
        muni_name, after["bound"], cov, near_share,
    )

    return {
        "before_unmatched": before["unmatched"],
        "newly_bound": n_updated,
        "after_total": after["total"],
        "after_bound": after["bound"],
        "after_nearest": after["nearest"],
        "after_coverage_pct": round(cov, 2),
        "after_nearest_share_pct": round(near_share, 2),
    }


async def main(confirm: bool) -> int:
    if not confirm:
        print("Refusing to fire without --i-know-this-writes-to-prod", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(_session_db_url(), statement_cache_size=0, command_timeout=1800)
    try:
        # Allow long Pass-2 update on Yorktown's 4,700 unmatched × 155 districts.
        await conn.execute("SET statement_timeout = 0")
        results = {}
        for muni_name, city in GROUP_A:
            print(f"\n=== {muni_name} (city={city!r}) — Pass-2-only @ nearest_{int(NEAREST_M)}m ===")
            results[muni_name] = await _refire_one(conn, muni_name, city, NEAREST_M)
            r = results[muni_name]
            # Gate check + halt if either gate fails post-fire.
            if r["after_coverage_pct"] < 70.0:
                print(
                    f"\nHALT: {muni_name} coverage post-fire = "
                    f"{r['after_coverage_pct']}% < 70% gate",
                    file=sys.stderr,
                )
                return 3
            if r["after_nearest_share_pct"] >= 30.0:
                print(
                    f"\nHALT: {muni_name} nearest share post-fire = "
                    f"{r['after_nearest_share_pct']}% >= 30% cap",
                    file=sys.stderr,
                )
                return 4
        print("\n=== Group A re-fire complete; all three munis pass both gates ===")
        for m, r in results.items():
            print(
                f"  {m:13s}: +{r['newly_bound']:>4} bound, "
                f"cov {r['after_coverage_pct']:>5.2f}%, "
                f"near share {r['after_nearest_share_pct']:>5.2f}%"
            )
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--i-know-this-writes-to-prod", action="store_true",
        help="Confirmation flag. Required because this writes "
             "parcels.zone_binding_method / zoning_code on prod.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    raise SystemExit(asyncio.run(main(args.i_know_this_writes_to_prod)))
