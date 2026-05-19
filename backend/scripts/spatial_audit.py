"""Per-jurisdiction spatial-correctness audit CLI.

Calls the deployed `/api/jurisdictions/{id}/_spatial-audit` endpoint and
prints a human-readable report. Default base URL is prod; pass --base-url
to point at a local stack.

Usage:
    python scripts/spatial_audit.py <jurisdiction_id>
    python scripts/spatial_audit.py <jurisdiction_id> --json
    python scripts/spatial_audit.py <jurisdiction_id> --no-districts
    python scripts/spatial_audit.py <jurisdiction_id> --base-url http://localhost:8000

Exit codes:
    0  audit ran (regardless of findings)
    2  endpoint returned an error / jurisdiction not found
    3  network / parse error
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx


_DEFAULT_BASE = "https://capable-serenity-production-0d1a.up.railway.app"


def _fmt_pct(num: int, denom: int) -> str:
    if not denom:
        return "n/a"
    return f"{num}/{denom} ({num / denom:.0%})"


def _print_report(audit: dict[str, Any]) -> None:
    print()
    print(f"Jurisdiction: {audit.get('jurisdiction_name')} ({audit.get('jurisdiction_id')})")
    bbox = audit.get("jurisdiction_bbox")
    if bbox:
        print(f"  bbox: [{bbox[0]:.4f}, {bbox[1]:.4f}] → [{bbox[2]:.4f}, {bbox[3]:.4f}]")
    print(f"  zoning_sources rows: {audit.get('source_count_total', 0)}")

    bsv = audit.get("by_status_x_verdict") or {}
    if bsv:
        print()
        print("  status × live verdict:")
        verdict_order = ["good", "partial", "tiny", "disjoint", "unknown", "error"]
        statuses = sorted(bsv.keys())
        header = "    " + " ".join(f"{v:>9}" for v in verdict_order)
        print(header)
        for st in statuses:
            row = bsv[st]
            cells = " ".join(f"{row.get(v, 0):>9d}" for v in verdict_order)
            print(f"    {st:<14} {cells}")

    stale = audit.get("stale_breakdown_count", 0)
    print()
    print(f"  stale-score rows (no bbox_overlap_* in stored breakdown): {stale}")
    for row in (audit.get("stale_breakdown_sample") or [])[:10]:
        muni = row.get("municipality_name") or "—"
        print(f"    [{row.get('live_verdict'):8}] score={row.get('stored_score')} "
              f"{muni} :: {row.get('title')}")
        print(f"               {row.get('zoning_endpoint')}")

    blocking = audit.get("blocking_verified") or []
    print()
    print(f"  verified rows the spatial gate would now block: {len(blocking)}")
    for row in blocking[:10]:
        print(f"    [{row.get('live_verdict'):8}] "
              f"srid={row.get('layer_extent_srid')} "
              f"{row.get('municipality_name') or '—'} :: {row.get('title')}")
        print(f"               {row.get('zoning_endpoint')}")

    crs_failures = audit.get("crs_failures") or []
    print()
    print(f"  layers with CRS-reprojection failures: {audit.get('crs_failure_count', 0)}")
    for row in crs_failures[:10]:
        print(f"    srid={row.get('layer_extent_srid')} "
              f"raw={row.get('layer_extent_raw')} :: {row.get('title')}")

    districts = audit.get("districts")
    if districts:
        print()
        print("  zoning_districts:")
        print(f"    total: {districts.get('total')}")
        print(f"    invalid geometry: {districts.get('invalid_geom')}")
        if districts.get("extent_wgs84"):
            e = districts["extent_wgs84"]
            print(f"    extent: [{e[0]:.4f}, {e[1]:.4f}] → [{e[2]:.4f}, {e[3]:.4f}]")

    overlap = audit.get("parcel_overlap")
    if overlap:
        print()
        print("  parcel overlay coverage:")
        print(f"    parcels with zoning_code: "
              f"{_fmt_pct(overlap.get('with_zoning', 0), overlap.get('total', 0))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("jurisdiction_id", help="UUID of the jurisdiction to audit")
    parser.add_argument("--base-url", default=_DEFAULT_BASE, help=f"API base (default: {_DEFAULT_BASE})")
    parser.add_argument("--no-districts", action="store_true",
                        help="Skip district + parcel stats (faster, ~1 round trip).")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Concurrent spatial-check probes (default 8, max 32).")
    parser.add_argument("--json", action="store_true",
                        help="Emit the raw JSON response instead of the formatted report.")
    args = parser.parse_args()

    url = (
        f"{args.base_url.rstrip('/')}"
        f"/api/jurisdictions/{args.jurisdiction_id}/_spatial-audit"
    )
    params = {
        "include_district_stats": "false" if args.no_districts else "true",
        "concurrency": str(args.concurrency),
    }

    try:
        # Slow upstream sweeps over 200 sources can take 30-60s; allow up to 5min.
        resp = httpx.get(url, params=params, timeout=300.0)
    except httpx.HTTPError as exc:
        print(f"network error: {exc!r}", file=sys.stderr)
        return 3

    if resp.status_code >= 400:
        print(f"HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 2

    try:
        audit = resp.json()
    except json.JSONDecodeError as exc:
        print(f"parse error: {exc}", file=sys.stderr)
        return 3

    if args.json:
        json.dump(audit, sys.stdout, indent=2, default=str)
        print()
    else:
        _print_report(audit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
