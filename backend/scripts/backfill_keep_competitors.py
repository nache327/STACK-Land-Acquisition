"""Backfill parcel_keep_metrics.competitor_units_30 (migration 0059) for existing rows.

Garage-condo units (built or planned) within 30 km straight-line of each parcel's
census-tract point — a documented proxy for a 30-minute drive, INFORMATION ONLY on the
garage-condo board card (never a gate). The rule and the supply list live in
``app.services.keep_market`` (``competitor_units`` over
``backend/data/keep_supply_campuses.csv``); this script only applies it.

Tract point = centroid of the census_tracts row named by parcel_keep_metrics.tract_geoid
(the same tract-centroid convention as the keep precompute). A row whose tract is not in
census_tracts (bucketed locally by the precompute) or has no tract falls back to the
parcel centroid. A row with neither stays NULL (unmeasured, never 0).

No Mapbox / Census calls; one read, then batched UPDATEs (one transaction per batch, so
a failure mid-run leaves completed batches applied and a rerun converges).

USAGE (from backend/):
  python scripts/backfill_keep_competitors.py --dry-run     # read + tally, no writes
  python scripts/backfill_keep_competitors.py               # apply
  python scripts/backfill_keep_competitors.py --only-null   # just rows still NULL
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402
from app.services import keep_market  # noqa: E402

logger = logging.getLogger("backfill_keep_competitors")

_READ_SQL = """
SELECT k.parcel_id,
       k.competitor_units_30 AS current,
       ST_Y(ST_Centroid(ct.geom)) AS t_lat, ST_X(ST_Centroid(ct.geom)) AS t_lng,
       ST_Y(p.centroid::geometry) AS p_lat, ST_X(p.centroid::geometry) AS p_lng
  FROM parcel_keep_metrics k
  JOIN parcels p ON p.id = k.parcel_id
  LEFT JOIN census_tracts ct ON ct.geoid = k.tract_geoid
 {where}
"""

_UPDATE_SQL = """
UPDATE parcel_keep_metrics k
   SET competitor_units_30 = v.units
  FROM unnest($1::bigint[], $2::int[]) AS v(parcel_id, units)
 WHERE k.parcel_id = v.parcel_id
   AND k.competitor_units_30 IS DISTINCT FROM v.units
"""


def point_for(row: dict) -> tuple[float | None, float | None]:
    """Tract centroid, else parcel centroid, else (None, None)."""
    if row.get("t_lat") is not None and row.get("t_lng") is not None:
        return float(row["t_lat"]), float(row["t_lng"])
    if row.get("p_lat") is not None and row.get("p_lng") is not None:
        return float(row["p_lat"]), float(row["p_lng"])
    return None, None


def compute(rows: list[dict], campuses: list) -> list[tuple[int, int | None]]:
    """(parcel_id, competitor_units_30) per row; one computation per distinct point."""
    cache: dict[tuple, int | None] = {}
    out = []
    for r in rows:
        pt = point_for(r)
        if pt not in cache:
            cache[pt] = keep_market.competitor_units(pt[0], pt[1], campuses)
        out.append((r["parcel_id"], cache[pt]))
    return out


def batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _bucket(n: int | None) -> str:
    if n is None:
        return "NULL"
    if n == 0:
        return "0"
    if n < 100:
        return "1-99"
    if n < 500:
        return "100-499"
    return "500+"


async def run(args) -> int:
    campuses = keep_market.load_supply_campuses()
    print(f"supply: {len(campuses):,} campus(es) with coordinates, "
          f"{sum(c.units for c in campuses):,} unit(s)")
    conn = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, timeout=120)
    try:
        await conn.execute(f"SET statement_timeout = '{int(args.statement_timeout_min)}min'")
        if not await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'parcel_keep_metrics' "
                "AND column_name = 'competitor_units_30')"):
            raise SystemExit("parcel_keep_metrics.competitor_units_30 missing — "
                             "apply migration 0059 first")
        if args.dry_run:
            await conn.execute("SET default_transaction_read_only = on")
        where = "WHERE k.competitor_units_30 IS NULL" if args.only_null else ""
        t0 = time.monotonic()
        rows = [dict(r) for r in await conn.fetch(_READ_SQL.format(where=where))]
        print(f"read: {len(rows):,} row(s) ({time.monotonic() - t0:.0f}s); "
              f"{sum(1 for r in rows if r['t_lat'] is None):,} without a census_tracts "
              "centroid (parcel-centroid fallback)")
        results = compute(rows, campuses)
        current = {r["parcel_id"]: r["current"] for r in rows}
        changed = [(pid, n) for pid, n in results if current.get(pid) != n]
        dist = Counter(_bucket(n) for _, n in results)
        print("competitor_units_30 distribution: "
              + ", ".join(f"{k}={dist[k]:,}" for k in ("NULL", "0", "1-99", "100-499", "500+")))
        print(f"{len(changed):,} row(s) would change")
        if args.dry_run:
            print("DRY RUN — no writes")
            return 0
        done = 0
        for chunk in batches(changed, args.batch_size):
            async with conn.transaction():
                await conn.execute(_UPDATE_SQL, [p for p, _ in chunk], [n for _, n in chunk])
            done += len(chunk)
            logger.info("updated %d/%d", done, len(changed))
        print(f"applied: {done:,} row(s) updated")
        n_null = await conn.fetchval(
            "SELECT count(*) FROM parcel_keep_metrics WHERE competitor_units_30 IS NULL")
        print(f"verify: {n_null:,} row(s) still NULL in parcel_keep_metrics")
    finally:
        await conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="read + tally only; no writes")
    ap.add_argument("--only-null", action="store_true", help="only rows still NULL")
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--statement-timeout-min", type=int, default=10)
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:  # pragma: no cover
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
