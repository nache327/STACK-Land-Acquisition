"""Precompute garage-condo (LGC) keep-market metrics → parcel_keep_metrics.

Keep-market Phase B (calibration: outputs/KEEP_MARKET_CALIBRATION_2026-10.md). For every
CANDIDATE LGC parcel — acres >= 1.5 and LGC verdict 'permitted' or 'unclear' (the shared
``use_verdicts.lgc_verdict_sql`` over precompute_needles' muni-aware ``_LATERAL``) — this
measures wealth DEPTH around the parcel's census tract and derives the keep lane, price
band and velocity flag via ``app.services.keep_market`` (the single source of the rules).

Tract-clustered exactly like ring_metrics_precompute: each parcel is bucketed into the
census tract containing its centroid (ST_Within against census_tracts), and every
measurement is taken ONCE per tract centroid:

  * ONE Mapbox 20-min driving isochrone per tract → intersect the national cb_2022 tract
    shapes by area share → ACS 2022: hh_200k_20, owner_1m_count/share_20 (B25075 $1M+
    bins), seasonal_share_20, young_old_200k_ratio_20.
  * Drive time to the nearest $1M+ wealth center (Mapbox Matrix, batched ≤25 coords).
  * county_home_ppsf from a Zillow ZHVI county CSV (--zhvi-csv).

Parcels whose centroid falls in no loaded census_tracts row are bucketed LOCALLY against
the same cb_2022 shapes instead — so this script never writes to census_tracts.

MODES
  --out-csv PATH    compute everything, write one row per parcel. DB READS ONLY (the
                    connection is put in default_transaction_read_only).
  --load-csv PATH   bulk-upsert a CSV produced by --out-csv into parcel_keep_metrics
                    (requires migration 0058). No Mapbox / Census calls.
  --dry-run         plan only: candidate parcels / tracts / cached vs needed Mapbox calls
                    and a time estimate. No Mapbox calls, no writes.
  --limit-tracts N  process only the first N tracts (testing).

Resumable: every isochrone and Matrix result is cached per tract under --cache-dir, as
are the tract shapes, the nationwide ACS table and the wealth-center list, so a rerun
only pays for what is missing.

USAGE (from backend/):
  python scripts/precompute_keep_metrics.py --jurisdiction <jid> --dry-run
  python scripts/precompute_keep_metrics.py --zhvi-csv zhvi_county.csv \
      --cache-dir D:/keep_cache --out-csv D:/keep_cache/keep_metrics.csv
  python scripts/precompute_keep_metrics.py --load-csv D:/keep_cache/keep_metrics.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import math
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402
from precompute_needles import _LATERAL  # noqa: E402
from app.services import keep_market  # noqa: E402
from app.services import keep_market_data as kmd  # noqa: E402
from app.services.use_verdicts import lgc_verdict_sql  # noqa: E402

logger = logging.getLogger("precompute_keep_metrics")

# Candidate scope: LGC by-right OR unclear (worth measuring before a human verifies).
CANDIDATE_VERDICTS = ("permitted", "unclear")
MIN_ACRES = 1.5

_LGC_VERDICT = lgc_verdict_sql("v.ss", "v.mw", "v.li", "v.hr")

# One row per candidate parcel; the tract is the census_tracts row containing the
# parcel centroid (ring_metrics_precompute's bucketing), NULL when none is loaded.
_CANDIDATES_SQL = f"""
SELECT p.id AS parcel_id,
       ({_LGC_VERDICT}) AS lgc_verdict,
       ST_X(p.centroid::geometry) AS p_lng, ST_Y(p.centroid::geometry) AS p_lat,
       t.geoid AS geoid, t.lng AS t_lng, t.lat AS t_lat
  FROM parcels p
  {_LATERAL}
  LEFT JOIN LATERAL (
      SELECT ct.geoid,
             ST_X(ST_Centroid(ct.geom)) AS lng, ST_Y(ST_Centroid(ct.geom)) AS lat
        FROM census_tracts ct
       WHERE ST_Within(p.centroid, ct.geom)
       LIMIT 1
  ) t ON true
 WHERE p.jurisdiction_id = $1::uuid
   AND p.centroid IS NOT NULL
   AND p.acres >= {MIN_ACRES}
   AND ({_LGC_VERDICT}) IN {CANDIDATE_VERDICTS!r}
"""

# Columns persisted to parcel_keep_metrics (migration 0058), in CSV order.
TABLE_COLUMNS = [
    "parcel_id", "tract_geoid", "hh_200k_20", "owner_1m_count_20", "owner_1m_share_20",
    "seasonal_share_20", "young_old_200k_ratio_20", "wealth_center_drive_min",
    "wealth_center_km", "wealth_center_label", "county_home_ppsf", "keep_lane",
    "price_band_low", "price_band_high", "velocity_flag",
]
# Diagnostics carried in the CSV only (ignored by --load-csv).
EXTRA_COLUMNS = ["jurisdiction_id", "lgc_verdict", "tract_source"]
CSV_COLUMNS = TABLE_COLUMNS + EXTRA_COLUMNS

_INT_COLS = {"parcel_id", "hh_200k_20", "owner_1m_count_20", "price_band_low", "price_band_high"}
_FLOAT_COLS = {"owner_1m_share_20", "seasonal_share_20", "young_old_200k_ratio_20",
               "wealth_center_drive_min", "wealth_center_km", "county_home_ppsf"}


# ── DB phase (read-only) ─────────────────────────────────────────────────────

async def _fetch_candidates(conn, jids: list[tuple[str, str]]) -> list[dict]:
    out: list[dict] = []
    for i, (jid, name) in enumerate(jids, 1):
        t0 = time.monotonic()
        rows = await conn.fetch(_CANDIDATES_SQL, jid)
        for r in rows:
            d = dict(r)
            d["jurisdiction_id"] = jid
            out.append(d)
        if rows or len(jids) == 1:
            logger.info("[%d/%d] %s: %d candidate parcel(s) (%.0fs)",
                        i, len(jids), name, len(rows), time.monotonic() - t0)
    return out


async def _jurisdictions(conn, jid: str | None) -> list[tuple[str, str]]:
    if jid:
        name = await conn.fetchval("SELECT name FROM jurisdictions WHERE id = $1::uuid", jid)
        if name is None:
            raise SystemExit(f"jurisdiction {jid} not found")
        return [(jid, name)]
    rows = await conn.fetch("SELECT id::text AS id, name FROM jurisdictions ORDER BY name")
    return [(r["id"], r["name"]) for r in rows]


def _bucket_locally(cands: list[dict], tracts) -> int:
    """Assign a tract (and its centroid) to parcels the DB couldn't bucket, using the
    national cb_2022 shapes. Returns how many were bucketed."""
    import geopandas as gpd

    missing = [c for c in cands if not c.get("geoid")]
    if not missing:
        return 0
    pts = gpd.GeoDataFrame(
        {"i": range(len(missing))},
        geometry=gpd.points_from_xy([c["p_lng"] for c in missing], [c["p_lat"] for c in missing]),
        crs=4326).to_crs(kmd.EQUAL_AREA_CRS)
    j = gpd.sjoin(pts, tracts[["GEOID", "geometry"]], predicate="within", how="left")
    j = j[~j.index.duplicated(keep="first")]
    cent = tracts.set_index("GEOID").geometry.centroid
    cent_ll = gpd.GeoSeries(cent, crs=kmd.EQUAL_AREA_CRS).to_crs(4326)
    n = 0
    for idx, geoid in zip(j["i"].values, j["GEOID"].values):
        if isinstance(geoid, str) and geoid:
            c = missing[int(idx)]
            pt = cent_ll.loc[geoid]
            c["geoid"], c["t_lng"], c["t_lat"] = geoid, float(pt.x), float(pt.y)
            c["tract_source"] = "local_cb2022"
            n += 1
    return n


def _is_unpopulated(geoid: str, acs_rows: dict[str, dict]) -> bool:
    """Special-use tracts (98xxxx: parks/airports/bases, 99xxxx: water) and zero-population
    tracts: their polygon centroid can sit in a lake or on a military range, where a
    20-min isochrone measures nobody (Lehi UT 49049980100: a 2.6 sq mi isochrone)."""
    if geoid[5:7] in ("98", "99"):
        return True
    pop = (acs_rows.get(geoid) or {}).get("B01003_001E")
    return pop is None or (isinstance(pop, float) and math.isnan(pop)) or pop <= 0


def _tract_origins(cands: list[dict], acs_rows: dict[str, dict]) -> dict[str, tuple[float, float]]:
    """Measurement origin per tract: the tract centroid (ring_metrics_precompute's
    convention), except for unpopulated tracts, which use the mean of their candidate
    parcels' centroids so the isochrone starts where the land actually is."""
    pts: dict[str, tuple[float, float]] = {}
    parcels: dict[str, list[tuple[float, float]]] = {}
    for c in cands:
        g = c.get("geoid")
        if not g:
            continue
        pts.setdefault(g, (float(c["t_lng"]), float(c["t_lat"])))
        parcels.setdefault(g, []).append((float(c["p_lng"]), float(c["p_lat"])))
    for g, pp in parcels.items():
        if _is_unpopulated(g, acs_rows):
            pts[g] = (sum(x for x, _ in pp) / len(pp), sum(y for _, y in pp) / len(pp))
    return pts


# ── Mapbox phase ─────────────────────────────────────────────────────────────

async def _fetch_isochrones(cache_dir: Path, tract_pts: dict[str, tuple[float, float]],
                            rpm: int) -> dict[str, int]:
    from app.config import settings
    from app.services.mapbox_isochrone import MapboxIsochroneClient

    todo = [g for g in tract_pts if kmd.read_iso(cache_dir, g) is None]
    stats = {"cached": len(tract_pts) - len(todo), "fetched": 0, "failed": 0}
    if not todo:
        return stats
    logger.info("isochrones: %d cached, %d to fetch (rpm=%d)", stats["cached"], len(todo), rpm)
    client = MapboxIsochroneClient(settings.mapbox_token, rate_limit_per_minute=rpm)
    t0 = time.monotonic()
    try:
        async def one(g: str) -> None:
            lng, lat = tract_pts[g]
            try:
                polys = await client.fetch(lng, lat, contours=(kmd.POOL_MINUTES,))
                kmd.write_iso(cache_dir, g, polys[kmd.POOL_MINUTES])
                stats["fetched"] += 1
            except Exception as e:  # noqa: BLE001
                stats["failed"] += 1
                logger.warning("isochrone failed for tract %s: %s", g, kmd._scrub(e))
            done = stats["fetched"] + stats["failed"]
            if done % 200 == 0:
                logger.info("  isochrones %d/%d (%.0fs)", done, len(todo), time.monotonic() - t0)

        for i in range(0, len(todo), 1000):  # bounded task fan-out
            await asyncio.gather(*(one(g) for g in todo[i:i + 1000]))
    finally:
        await client.aclose()
    return stats


async def _fetch_drive_times(cache_dir: Path, tract_pts: dict[str, tuple[float, float]],
                             idx: kmd.WealthCenterIndex, rpm: int
                             ) -> tuple[dict[str, dict], dict[str, int]]:
    """{geoid: {'cands': [(id, km)], 'dur': {id: min}}} for every tract, cached."""
    from app.config import settings

    res: dict[str, dict] = {}
    need: dict[str, list[str]] = {}
    for g, (lng, lat) in tract_pts.items():
        cands = idx.candidates(lat, lng)
        ids = [c for c, _ in cands]
        cached = kmd.read_matrix(cache_dir, g, ids)
        res[g] = {"cands": cands, "dur": (cached or {}).get("dur", {})}
        if ids and cached is None:
            need[g] = ids
    stats = {"cached": len(tract_pts) - len(need), "requests": 0, "failed_requests": 0}
    if not need:
        return res, stats
    batches = kmd.plan_matrix_batches(need)
    logger.info("matrix: %d tract(s) cached, %d to fetch in %d request(s) (rpm=%d)",
                stats["cached"], len(need), len(batches), rpm)
    client = kmd.MatrixClient(settings.mapbox_token, rpm=rpm)
    try:
        async def one(origins: list[str], dests: list[str]) -> None:
            try:
                rows = await client.durations(
                    [tract_pts[g] for g in origins],
                    [(idx.by_id[c].lng, idx.by_id[c].lat) for c in dests])
            except Exception as e:  # noqa: BLE001
                stats["failed_requests"] += 1
                logger.warning("matrix request failed (%d origins): %s", len(origins), kmd._scrub(e))
                return
            stats["requests"] += 1
            for g, row in zip(origins, rows):
                dur = {c: (None if v is None else round(v, 2)) for c, v in zip(dests, row)
                       if c in need[g]}
                kmd.write_matrix(cache_dir, g, dur)
                res[g]["dur"] = dur

        for i in range(0, len(batches), 200):
            await asyncio.gather(*(one(o, d) for o, d in batches[i:i + 200]))
    finally:
        await client.aclose()
    return res, stats


# ── Compute ──────────────────────────────────────────────────────────────────

def _fmt(v, nd=None):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(v, nd) if nd is not None and isinstance(v, float) else v


def _parcel_rows(cands: list[dict], tract_metrics: dict[str, dict],
                 ppsf: dict[str, float]) -> list[dict]:
    out = []
    for c in cands:
        g = c.get("geoid")
        tm = tract_metrics.get(g) if g else None
        home_ppsf = ppsf.get(g[:5]) if g else None
        share = tm["owner_1m_share_20"] if tm else None
        drive = tm["wealth_center_drive_min"] if tm else None
        a = keep_market.assess(share, drive, home_ppsf)
        row = {
            "parcel_id": c["parcel_id"], "tract_geoid": g,
            "county_home_ppsf": home_ppsf,
            "keep_lane": a.keep_lane, "price_band_low": a.price_band_low,
            "price_band_high": a.price_band_high, "velocity_flag": a.velocity_flag,
            "jurisdiction_id": c["jurisdiction_id"], "lgc_verdict": c.get("lgc_verdict"),
            "tract_source": c.get("tract_source", "census_tracts") if g else "none",
        }
        for k in ("hh_200k_20", "owner_1m_count_20", "owner_1m_share_20", "seasonal_share_20",
                  "young_old_200k_ratio_20", "wealth_center_drive_min", "wealth_center_km",
                  "wealth_center_label"):
            row[k] = tm.get(k) if tm else None
        out.append(row)
    return out


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in CSV_COLUMNS})


def _summarise(rows: list[dict]) -> None:
    lanes = Counter(r["keep_lane"] or "NULL" for r in rows)
    vel = Counter(r["velocity_flag"] or "-" for r in rows)
    tracts = {r["tract_geoid"] for r in rows if r["tract_geoid"]}
    print(f"\n=== keep metrics: {len(rows):,} parcel(s) across {len(tracts):,} tract(s) ===")
    for k, v in lanes.most_common():
        print(f"  lane {k:<16} {v:>8,}")
    for k, v in vel.most_common():
        print(f"  velocity {k:<12} {v:>8,}")
    no_ppsf = sum(1 for r in rows if r["tract_geoid"] and r["county_home_ppsf"] is None)
    if no_ppsf:
        print(f"  WARNING: {no_ppsf:,} parcel(s) have no county_home_ppsf (no ZHVI county "
              "match) — lane kept, price band NULL")


async def run_compute(args) -> int:
    from app.config import settings

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, timeout=120)
    try:
        # READ-ONLY by construction: compute/dry-run never write to the DB.
        await conn.execute("SET default_transaction_read_only = on")
        await conn.execute(f"SET statement_timeout = '{int(args.statement_timeout_min)}min'")
        jids = await _jurisdictions(conn, args.jurisdiction)
        cands = await _fetch_candidates(conn, jids)
    finally:
        await conn.close()
    logger.info("candidates: %d parcel(s), %d without a census_tracts match",
                len(cands), sum(1 for c in cands if not c.get("geoid")))

    if args.dry_run:
        tract_pts = {c["geoid"] for c in cands if c.get("geoid")}
        iso_cached = sum(1 for g in tract_pts if kmd.iso_cache_path(cache_dir, g).exists())
        mx_cached = sum(1 for g in tract_pts if kmd.matrix_cache_path(cache_dir, g).exists())
        n = len(tract_pts)
        iso_need, mx_need = n - iso_cached, n - mx_cached
        # ~20 origins per Matrix request after packing (5 destinations each).
        mx_req = math.ceil(mx_need / 20)
        iso_min = iso_need / max(args.iso_rpm, 1)
        mx_min = mx_req / max(args.matrix_rpm, 1)
        print(f"\nDRY RUN — {len(jids)} jurisdiction(s), {len(cands):,} candidate parcel(s), "
              f"{n:,} DB-bucketed tract(s), {sum(1 for c in cands if not c.get('geoid')):,} "
              f"parcel(s) needing local bucketing")
        print(f"  isochrones: {iso_cached:,} cached, {iso_need:,} to fetch "
              f"(~{iso_min:.0f} min at {args.iso_rpm}/min)")
        print(f"  matrix:     {mx_cached:,} cached, ~{mx_req:,} request(s) for {mx_need:,} "
              f"tract(s) (~{mx_min:.0f} min at {args.matrix_rpm}/min, overlaps isochrones)")
        verdicts = Counter(c.get("lgc_verdict") for c in cands)
        print(f"  verdicts: {dict(verdicts)}")
        return 0

    # National reference data (cached).
    t0 = time.monotonic()
    tracts = kmd.load_tracts(cache_dir)
    acs = kmd.ensure_acs(cache_dir, settings.census_api_key)
    acs_rows = acs.to_dict("index")
    logger.info("reference data: %d tract shapes, %d ACS rows (%.0fs)",
                len(tracts), len(acs), time.monotonic() - t0)
    wc_path = cache_dir / "wealth_centers.csv"
    if wc_path.exists():
        centers = kmd.load_wealth_centers(wc_path)
    else:
        centers = kmd.build_wealth_centers(tracts, acs)
        kmd.save_wealth_centers(wc_path, centers)
    idx = kmd.WealthCenterIndex(centers)
    logger.info("wealth centers: %d clusters, %d fallback singles",
                len(idx.clusters), len(idx.singles))

    n_local = _bucket_locally(cands, tracts)
    if n_local:
        logger.info("bucketed %d parcel(s) locally against cb_2022 shapes", n_local)

    tract_pts = _tract_origins(cands, acs_rows)
    if args.limit_tracts:
        keep = set(sorted(tract_pts)[: args.limit_tracts])
        tract_pts = {g: v for g, v in tract_pts.items() if g in keep}
        cands = [c for c in cands if c.get("geoid") in keep]
        logger.info("--limit-tracts %d: %d parcel(s) kept", args.limit_tracts, len(cands))

    iso_stats = await _fetch_isochrones(cache_dir, tract_pts, args.iso_rpm)
    drive, mx_stats = await _fetch_drive_times(cache_dir, tract_pts, idx, args.matrix_rpm)
    logger.info("mapbox: isochrones %s; matrix %s", iso_stats, mx_stats)

    tract_metrics: dict[str, dict] = {}
    t0 = time.monotonic()
    for i, g in enumerate(sorted(tract_pts), 1):
        iso = kmd.read_iso(cache_dir, g)
        if iso is None:
            pool = kmd.PoolMetrics(None, None, None, None, None)
        else:
            pool = kmd.pool_for_isochrone(iso, tracts, acs_rows)
        cid, dmin, km = kmd.pick_center(drive[g]["cands"], drive[g]["dur"])
        tract_metrics[g] = {
            "hh_200k_20": pool.hh_200k_20,
            "owner_1m_count_20": pool.owner_1m_count_20,
            "owner_1m_share_20": pool.owner_1m_share_20,
            "seasonal_share_20": pool.seasonal_share_20,
            "young_old_200k_ratio_20": pool.young_old_200k_ratio_20,
            "wealth_center_drive_min": None if dmin is None else round(dmin, 1),
            "wealth_center_km": None if km is None else round(km, 2),
            "wealth_center_label": idx.by_id[cid].label if cid else None,
        }
        if i % 500 == 0:
            logger.info("  pools %d/%d (%.0fs)", i, len(tract_pts), time.monotonic() - t0)

    ppsf: dict[str, float] = {}
    if args.zhvi_csv:
        year, ppsf = kmd.load_zhvi_county_ppsf(args.zhvi_csv)
        logger.info("ZHVI: %d counties, latest full year %s", len(ppsf), year)
    else:
        logger.warning("no --zhvi-csv: county_home_ppsf and price bands will be NULL")

    rows = _parcel_rows(cands, tract_metrics, ppsf)
    _summarise(rows)
    if args.out_csv:
        _write_csv(Path(args.out_csv), rows)
        print(f"wrote {len(rows):,} row(s) -> {args.out_csv}")
    return 0


# ── Load ─────────────────────────────────────────────────────────────────────

def _parse_csv_row(r: dict) -> tuple:
    out = []
    for c in TABLE_COLUMNS:
        v = r.get(c, "")
        if v == "" or v is None:
            out.append(None)
        elif c in _INT_COLS:
            out.append(int(float(v)))
        elif c in _FLOAT_COLS:
            out.append(float(v))
        else:
            out.append(v)
    return tuple(out)


_LOAD_UPSERT = f"""
INSERT INTO parcel_keep_metrics ({", ".join(TABLE_COLUMNS)}, computed_at)
SELECT {", ".join("s." + c for c in TABLE_COLUMNS)}, now()
  FROM _keep_load s
  JOIN parcels p ON p.id = s.parcel_id
ON CONFLICT (parcel_id) DO UPDATE SET
  {", ".join(f"{c} = EXCLUDED.{c}" for c in TABLE_COLUMNS if c != "parcel_id")},
  computed_at = now()
"""


async def run_load(args) -> int:
    path = Path(args.load_csv)
    with path.open(newline="", encoding="utf-8") as f:
        records = [_parse_csv_row(r) for r in csv.DictReader(f)]
    print(f"load: {len(records):,} row(s) from {path}")
    conn = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, timeout=120)
    try:
        await conn.execute(f"SET statement_timeout = '{int(args.statement_timeout_min)}min'")
        if not await conn.fetchval("SELECT to_regclass('parcel_keep_metrics') IS NOT NULL"):
            raise SystemExit("parcel_keep_metrics does not exist — apply migration 0058 first")
        async with conn.transaction():
            await conn.execute(
                "CREATE TEMP TABLE _keep_load (LIKE parcel_keep_metrics INCLUDING DEFAULTS) "
                "ON COMMIT DROP")
            await conn.copy_records_to_table("_keep_load", records=records, columns=TABLE_COLUMNS)
            status = await conn.execute(_LOAD_UPSERT)
        print(f"load: {status}")
        dist = await conn.fetch(
            "SELECT coalesce(keep_lane,'NULL') lane, count(*) n FROM parcel_keep_metrics "
            "GROUP BY 1 ORDER BY 2 DESC")
        for r in dist:
            print(f"  {r['lane']:<16} {r['n']:>8,}")
    finally:
        await conn.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--jurisdiction", help="limit to one jurisdiction id (uuid)")
    ap.add_argument("--out-csv", help="compute and write per-parcel rows here (DB read-only)")
    ap.add_argument("--load-csv", help="upsert a computed CSV into parcel_keep_metrics")
    ap.add_argument("--dry-run", action="store_true", help="plan only; no Mapbox, no writes")
    ap.add_argument("--limit-tracts", type=int, default=0)
    ap.add_argument("--zhvi-csv", help="Zillow ZHVI county CSV (county_home_ppsf)")
    ap.add_argument("--cache-dir", default=str(Path(__file__).parent / "_keep_cache"),
                    help="isochrone/matrix/tract/ACS cache (resumable)")
    ap.add_argument("--iso-rpm", type=int, default=None,
                    help="isochrone requests/min (default settings.mapbox_isochrone_rpm)")
    ap.add_argument("--matrix-rpm", type=int, default=kmd.MATRIX_RPM)
    ap.add_argument("--statement-timeout-min", type=int, default=15)
    args = ap.parse_args()
    # Windows consoles default to cp1252; never crash a long run on a non-ASCII char.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:  # pragma: no cover - non-TextIOWrapper streams
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx logs full request URLs (with the access token) at INFO — silence it.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.iso_rpm is None:
        from app.config import settings

        args.iso_rpm = settings.mapbox_isochrone_rpm
    if args.load_csv:
        if args.out_csv or args.dry_run:
            ap.error("--load-csv cannot be combined with --out-csv/--dry-run")
        return asyncio.run(run_load(args))
    if not (args.out_csv or args.dry_run):
        ap.error("choose --out-csv PATH, --dry-run, or --load-csv PATH")
    return asyncio.run(run_compute(args))


if __name__ == "__main__":
    raise SystemExit(main())
