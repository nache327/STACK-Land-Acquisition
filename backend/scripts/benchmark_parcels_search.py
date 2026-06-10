"""Cross-county latency benchmark for POST /api/parcels/search.

Read-only measurement against a live deployment. Captures cold and
warm wall-clock for each of:

  - whole-county fetch  (no bbox, page 1, page_size=5000, slim=true)
  - bbox viewport fetch (~5km square around the jurisdiction centroid)

3 trials per metric. Cold misses are forced by varying the `sort`
field across trials — each sort changes the SHA256 cache key built
in `app.api.parcels._parcels_search_cache_key`, so trial N+1 cannot
HIT trial N's memo entry. Warm trials repeat the cold payload
immediately to capture the HIT path.

Throttle: 250 ms between requests, max 1 concurrent. The backend's
Supavisor session-mode cap (see docs/OP5_DB_CAPACITY_REPORT.md)
means polite is the only safe pacing for a sweep.

Per-jurisdiction failure: any 5xx or >30 s timeout is logged and the
script moves on — no retry loop.

Outputs:

  /tmp/parcels_search_benchmark_<ISO_DATE>.json   machine-readable
  /tmp/parcels_search_benchmark_<ISO_DATE>.md     markdown report

Usage:

  python backend/scripts/benchmark_parcels_search.py            # full sweep
  python backend/scripts/benchmark_parcels_search.py --smoke    # Bergen+Morris only
  python backend/scripts/benchmark_parcels_search.py --jurisdiction-names "Bergen County, NJ,Morris County, NJ"
  python backend/scripts/benchmark_parcels_search.py --api-base https://...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_API_BASE = (
    "https://capable-serenity-production-0d1a.up.railway.app"
)
DEFAULT_THROTTLE_SECONDS = 0.25
DEFAULT_TRIALS = 3
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_PAGE_SIZE = 5000
# Cycled across cold trials to force distinct cache keys without
# changing the underlying SQL semantics — every sort uses an indexed
# column (acres / apn) so the planner cost is comparable.
COLD_SORTS = ["acres_desc", "acres_asc", "apn_asc"]
# Bbox half-width in degrees. At mid-latitudes (~40°N) 0.025° ≈ 2.8 km
# longitude × ~2.8 km latitude — a ~5 km square. Latitude isn't
# adjusted for cos(lat) because the precise size doesn't matter for
# this measurement; the goal is "small viewport" comparability across
# jurisdictions, not a fixed metric area.
BBOX_HALF_DEG = 0.025
# Big counties on prod can spend 25-30 s on cold whole-county fetches
# (see PR #204 measurements). The dispatch budgets up to 30 s per
# request before logging as a hang and moving on.
SMOKE_JURISDICTIONS = ["Bergen County, NJ", "Morris County, NJ"]


def _centroid(bbox: list[float] | None) -> tuple[float, float] | None:
    if not bbox or len(bbox) != 4:
        return None
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _bbox_around(center: tuple[float, float]) -> list[float]:
    lng, lat = center
    return [
        lng - BBOX_HALF_DEG,
        lat - BBOX_HALF_DEG,
        lng + BBOX_HALF_DEG,
        lat + BBOX_HALF_DEG,
    ]


async def _fetch_inventory(
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Cross-join /api/admin/coverage (for parcel_count + readiness)
    with /api/jurisdictions (for bbox). Returns one record per
    jurisdiction with parcel_count > 0."""
    cov = (await client.get("/api/admin/coverage")).json()
    jurs = (await client.get("/api/jurisdictions")).json()
    bbox_by_id = {j["id"]: j.get("bbox") for j in jurs.get("items", [])}
    out: list[dict[str, Any]] = []
    for row in cov.get("jurisdictions", []):
        pc = int(row.get("parcel_count") or 0)
        if pc <= 0:
            continue
        jid = row.get("jurisdiction_id")
        bbox = bbox_by_id.get(jid)
        out.append({
            "id": jid,
            "name": row.get("jurisdiction_name"),
            "state": row.get("state"),
            "parcel_count": pc,
            "operational_readiness": row.get("operational_readiness"),
            "captured_at": row.get("captured_at"),
            "bbox": bbox,
            "centroid": _centroid(bbox),
        })
    out.sort(key=lambda r: r["parcel_count"], reverse=True)
    return out


def _payload(
    jid: str,
    *,
    sort: str,
    bbox: list[float] | None,
    page_size: int,
) -> dict[str, Any]:
    p: dict[str, Any] = {
        "jurisdiction_id": jid,
        "target_use": "self_storage",
        "filters": {},
        "page": 1,
        "page_size": page_size,
        "sort": sort,
        "slim": True,
    }
    if bbox is not None:
        p["bbox"] = bbox
    return p


async def _post_once(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Single POST. Returns {status, wall_clock_s, bytes, x_cache, error}.
    Bytes is the Content-Length of the response body. Wall-clock is the
    full request including TLS handshake (which is fine — what the
    customer experiences)."""
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            "/api/parcels/search",
            json=payload,
            timeout=timeout,
        )
        elapsed = time.perf_counter() - t0
        return {
            "status": resp.status_code,
            "wall_clock_s": round(elapsed, 3),
            "bytes": len(resp.content),
            "x_cache": resp.headers.get("x-cache"),
            "error": None,
        }
    except (httpx.TimeoutException, httpx.ReadTimeout) as exc:
        return {
            "status": None,
            "wall_clock_s": round(time.perf_counter() - t0, 3),
            "bytes": 0,
            "x_cache": None,
            "error": f"timeout: {exc!r}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": None,
            "wall_clock_s": round(time.perf_counter() - t0, 3),
            "bytes": 0,
            "x_cache": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-metric stats. NaN-safe when all trials failed."""
    times = [t["wall_clock_s"] for t in trials if t["error"] is None]
    sizes = [t["bytes"] for t in trials if t["error"] is None]
    if not times:
        return {
            "trials": trials,
            "min_s": None,
            "p50_s": None,
            "max_s": None,
            "median_bytes": None,
            "ok_count": 0,
            "error_count": len(trials),
        }
    return {
        "trials": trials,
        "min_s": round(min(times), 3),
        "p50_s": round(statistics.median(times), 3),
        "max_s": round(max(times), 3),
        "median_bytes": int(statistics.median(sizes)) if sizes else 0,
        "ok_count": len(times),
        "error_count": len(trials) - len(times),
    }


async def _benchmark_jurisdiction(
    client: httpx.AsyncClient,
    juris: dict[str, Any],
    *,
    trials: int,
    throttle: float,
    timeout: float,
    page_size: int,
) -> dict[str, Any]:
    name = juris["name"]
    jid = juris["id"]
    centroid = juris.get("centroid")
    bbox = _bbox_around(centroid) if centroid else None

    async def _trial_block(
        bbox_arg: list[float] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        # Cold: N trials with DIFFERENT sorts (each forces a unique
        # cache key → MISS). Warm: N trials with the FIRST sort
        # (acres_desc), which is now in the memo from the cold round.
        cold_trials: list[dict[str, Any]] = []
        for i in range(trials):
            sort = COLD_SORTS[i % len(COLD_SORTS)]
            payload = _payload(jid, sort=sort, bbox=bbox_arg, page_size=page_size)
            res = await _post_once(client, payload, timeout)
            res["sort"] = sort
            cold_trials.append(res)
            await asyncio.sleep(throttle)
        warm_payload = _payload(
            jid, sort=COLD_SORTS[0], bbox=bbox_arg, page_size=page_size
        )
        warm_trials: list[dict[str, Any]] = []
        for _ in range(trials):
            res = await _post_once(client, warm_payload, timeout)
            warm_trials.append(res)
            await asyncio.sleep(throttle)
        return cold_trials, warm_trials

    print(f"  {name} (parcels={juris['parcel_count']:,}) …", flush=True)
    cold_whole, warm_whole = await _trial_block(None)
    if bbox is not None:
        cold_bbox, warm_bbox = await _trial_block(bbox)
    else:
        cold_bbox = warm_bbox = []
    return {
        "jurisdiction_id": jid,
        "jurisdiction_name": name,
        "state": juris.get("state"),
        "parcel_count": juris["parcel_count"],
        "operational_readiness": juris.get("operational_readiness"),
        "captured_at": juris.get("captured_at"),
        "centroid": centroid,
        "bbox_used": bbox,
        "cold_whole": _summarize(cold_whole),
        "warm_whole": _summarize(warm_whole),
        "cold_bbox": _summarize(cold_bbox),
        "warm_bbox": _summarize(warm_bbox),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    rows = report["results"]
    # Foreground bbox: this is the customer-facing path. Sort by
    # cold_bbox_p50 descending; whole-county is a sidebar metric.
    rows_sorted = sorted(
        rows,
        key=lambda r: (r["cold_bbox"]["p50_s"] or -1),
        reverse=True,
    )
    lines: list[str] = []
    lines.append(f"# Parcel-search latency baseline — {report['run_started_at']}")
    lines.append("")
    lines.append(f"- API base: `{report['api_base']}`")
    lines.append(f"- Jurisdictions measured: {len(rows)}")
    lines.append(f"- Trials per metric: {report['trials']}")
    lines.append(f"- Throttle: {report['throttle_seconds']}s between requests")
    lines.append(f"- Timeout: {report['timeout_seconds']}s per request")
    lines.append(f"- Bbox window: ±{BBOX_HALF_DEG}° around jurisdiction centroid")
    lines.append(f"- Sweep wall-clock: {report.get('run_elapsed_s', '?')}s")
    lines.append("")
    lines.append("## Methodology — read before quoting numbers")
    lines.append("")
    lines.append(
        "**Bbox p50 is the customer-facing metric.** The dashboard map "
        "uses bbox-filtered queries; whole-county fetches happen only "
        "on the table view (which is paged and not the buyer-blocking "
        "path). Sort and outlier flags are anchored on `cold_bbox_p50`; "
        "whole-county columns are kept as a sidebar so the table view "
        "doesn't silently rot."
    )
    lines.append("")
    lines.append(
        "**Cold = memo-cold, NOT a quiet server.** Each \"cold\" trial "
        "varies the `sort` field, which changes the SHA256 cache key "
        "(`app.api.parcels._parcels_search_cache_key`) — so trial N+1 "
        "cannot HIT the in-process LRU memo. But the underlying "
        "Postgres buffer cache, query plan cache, and TCP/TLS "
        "connection stay warm across trials. The numbers therefore "
        "model **\"first user landing on an already-busy county\"**, "
        "not **\"first user touching a county that's been idle for "
        "hours.\"** True cold-cold would be slower."
    )
    lines.append("")
    lines.append(
        "**Warm** = same payload immediately replayed — HITs the "
        "in-process LRU memo. `payload_kb` = median bytes / 1024 "
        "across cold-bbox trials."
    )
    lines.append("")
    header = (
        "| Jurisdiction | Parcels | Ready | "
        "cold_bbox p50 | warm_bbox p50 | "
        "cold_whole p50 | warm_whole p50 | "
        "payload kb | errs |"
    )
    sep = (
        "|---|---:|---|---:|---:|---:|---:|---:|---:|"
    )
    lines.append(header)
    lines.append(sep)
    for r in rows_sorted:
        cw = r["cold_whole"]
        ww = r["warm_whole"]
        cb = r["cold_bbox"]
        wb = r["warm_bbox"]
        # `payload_kb` keys on bbox (the customer-facing path), not
        # the whole-county sidebar.
        kb = (
            round(cb["median_bytes"] / 1024, 1)
            if cb.get("median_bytes") is not None
            else "—"
        )
        errs = (
            cw["error_count"] + ww["error_count"]
            + cb["error_count"] + wb["error_count"]
        )
        lines.append(
            f"| {r['jurisdiction_name']} | "
            f"{r['parcel_count']:,} | "
            f"{r['operational_readiness']} | "
            f"{cb['p50_s'] if cb['p50_s'] is not None else '—'} | "
            f"{wb['p50_s'] if wb['p50_s'] is not None else '—'} | "
            f"{cw['p50_s'] if cw['p50_s'] is not None else '—'} | "
            f"{ww['p50_s'] if ww['p50_s'] is not None else '—'} | "
            f"{kb} | {errs} |"
        )
    lines.append("")
    lines.append("## Outliers")
    # Thresholds: the 2026-06-09 baseline established a fleet-floor of
    # ~2.3 s for cold_bbox (PG/network constant), so the original 2.0 s
    # flag caught every county. Bumped to 4.0 s — flags only the
    # buyer-blocking outliers (currently just Philadelphia at 6.56 s).
    # cold_whole stays at 8.0 s.
    outliers = [
        r for r in rows_sorted
        if (r["cold_bbox"]["p50_s"] or 0) > 4.0
        or (r["cold_whole"]["p50_s"] or 0) > 8.0
    ]
    lines.append("")
    if outliers:
        lines.append(
            "Flagged: `cold_bbox_p50 > 4s` OR `cold_whole_p50 > 8s`. "
            "Candidates for Phase 3 follow-up — do not fix mid-flight. "
            "`parcel_count` and `payload_kb` are inlined so the "
            "parcel-count-vs-something-else question can be answered "
            "without re-running the harness."
        )
        lines.append("")
        for r in outliers:
            cb = r["cold_bbox"]
            cw = r["cold_whole"]
            kb = (
                round(cb["median_bytes"] / 1024, 1)
                if cb.get("median_bytes") is not None
                else "?"
            )
            lines.append(
                f"- **{r['jurisdiction_name']}** "
                f"(parcels={r['parcel_count']:,}, "
                f"payload_kb={kb}): "
                f"cold_bbox={cb['p50_s']}s, "
                f"cold_whole={cw['p50_s']}s"
            )
    else:
        lines.append("None — every jurisdiction within thresholds.")
    return "\n".join(lines) + "\n"


async def _run(args: argparse.Namespace) -> int:
    api_base = args.api_base.rstrip("/")
    async with httpx.AsyncClient(
        base_url=api_base, timeout=args.timeout
    ) as client:
        print(f"Fetching inventory from {api_base} …", flush=True)
        inventory = await _fetch_inventory(client)
        print(
            f"  {len(inventory)} jurisdictions with parcel_count > 0",
            flush=True,
        )
        if args.smoke:
            inventory = [
                j for j in inventory if j["name"] in SMOKE_JURISDICTIONS
            ]
            print(f"  smoke filter → {len(inventory)}", flush=True)
        elif args.jurisdiction_names:
            wanted = {
                n.strip() for n in args.jurisdiction_names.split(",")
            }
            inventory = [j for j in inventory if j["name"] in wanted]
            print(
                f"  --jurisdiction-names filter → {len(inventory)}",
                flush=True,
            )
        if not inventory:
            print("No jurisdictions selected. Exiting.", file=sys.stderr)
            return 1

        run_started_at = datetime.now(timezone.utc).isoformat()
        run_t0 = time.perf_counter()
        results: list[dict[str, Any]] = []
        print(f"Benchmarking {len(inventory)} jurisdictions:", flush=True)
        for juris in inventory:
            try:
                res = await _benchmark_jurisdiction(
                    client,
                    juris,
                    trials=args.trials,
                    throttle=args.throttle,
                    timeout=args.timeout,
                    page_size=args.page_size,
                )
                results.append(res)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"  {juris['name']} FAILED: {type(exc).__name__}: {exc}",
                    flush=True,
                )
                results.append({
                    "jurisdiction_id": juris["id"],
                    "jurisdiction_name": juris["name"],
                    "parcel_count": juris["parcel_count"],
                    "operational_readiness": juris.get("operational_readiness"),
                    "centroid": juris.get("centroid"),
                    "bbox_used": None,
                    "cold_whole": _summarize([]),
                    "warm_whole": _summarize([]),
                    "cold_bbox": _summarize([]),
                    "warm_bbox": _summarize([]),
                    "fatal_error": f"{type(exc).__name__}: {exc}",
                })
        run_elapsed = time.perf_counter() - run_t0

    report = {
        "run_started_at": run_started_at,
        "run_elapsed_s": round(run_elapsed, 1),
        "api_base": api_base,
        "trials": args.trials,
        "throttle_seconds": args.throttle,
        "timeout_seconds": args.timeout,
        "page_size": args.page_size,
        "results": results,
    }

    iso_date = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    json_path = Path(args.json_out or f"/tmp/parcels_search_benchmark_{iso_date}.json")
    md_path = Path(args.md_out or f"/tmp/parcels_search_benchmark_{iso_date}.md")
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    md_path.write_text(_render_markdown(report))
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Total sweep time: {run_elapsed:.1f}s")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument(
        "--throttle", type=float, default=DEFAULT_THROTTLE_SECONDS
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    parser.add_argument(
        "--page-size", type=int, default=DEFAULT_PAGE_SIZE
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Limit to Bergen + Morris (Phase 1 smoke test)",
    )
    parser.add_argument(
        "--jurisdiction-names",
        help="Comma-separated jurisdiction names to filter (exact match).",
    )
    parser.add_argument("--json-out")
    parser.add_argument("--md-out")
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
