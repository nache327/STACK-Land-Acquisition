"""Per-municipality operational-trustworthiness CLI.

Calls the deployed `/api/jurisdictions/{id}/_municipalities-health`
endpoint and prints a formatted table sorted by band severity, so an
operator can see at a glance which munis under a county are operational
vs. broken.

Usage:
    python scripts/municipality_health.py <jurisdiction_id>
    python scripts/municipality_health.py <jurisdiction_id> --json
    python scripts/municipality_health.py <jurisdiction_id> --muni "New Milford"
    python scripts/municipality_health.py <jurisdiction_id> --only-broken

Exit codes:
    0  report ran (regardless of findings)
    2  HTTP / server error
    3  network / parse error
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx


_DEFAULT_BASE = "https://capable-serenity-production-0d1a.up.railway.app"

# Bands ordered worst → best so the operator's eye lands on broken first.
_BAND_ORDER = ["broken", "degraded", "partial", "operational", "empty"]


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return " — "
    return f"{v:.0%}"


def _fmt_extent(b: list[float] | None) -> str:
    if not b:
        return "—"
    return f"[{b[0]:.3f},{b[1]:.3f}]→[{b[2]:.3f},{b[3]:.3f}]"


def _print_report(data: dict[str, Any], *, only_broken: bool) -> None:
    print()
    print(f"Jurisdiction: {data.get('jurisdiction_name')} "
          f"({data.get('jurisdiction_id')})")
    print(f"  municipalities: {data.get('municipality_count', 0)}")

    counts = data.get("band_counts") or {}
    if counts:
        print()
        print("  band counts:")
        for band in _BAND_ORDER:
            if band in counts:
                print(f"    {band:<13} {counts[band]}")

    munis = data.get("municipalities") or []
    munis.sort(key=lambda m: (
        _BAND_ORDER.index(m.get("trustworthiness", "operational")),
        -(m.get("parcel_count") or 0),
    ))
    if only_broken:
        munis = [m for m in munis if m.get("trustworthiness") in ("broken", "degraded")]

    print()
    print("  muni  /  parcels  /  zoning%  /  classes%  /  districts  /  extent_overlap  /  band")
    for m in munis:
        name = m.get("municipality") or "(jurisdiction)"
        print(f"    [{m.get('trustworthiness'):<11}] "
              f"{name:<28} "
              f"p={m.get('parcel_count', 0):>6}  "
              f"z%={_fmt_pct(m.get('parcel_zoning_pct')):<5}  "
              f"c%={_fmt_pct(m.get('parcel_class_pct')):<5}  "
              f"d={m.get('district_count', 0):>4}  "
              f"ext={_fmt_pct(m.get('extent_overlap_ratio')):<5}")
        for gap in (m.get("gaps") or [])[:4]:
            print(f"                  ▸ {gap}")

    thr = data.get("thresholds") or {}
    if thr and not only_broken:
        print()
        print("  thresholds:")
        for k in ("min_parcel_count_for_operational",
                  "min_parcel_zoning_pct_operational",
                  "min_parcel_zoning_pct_partial",
                  "min_parcel_class_pct_partial",
                  "min_district_count_for_operational",
                  "max_district_overlap_ratio",
                  "min_extent_overlap_ratio"):
            if k in thr:
                print(f"    {k}: {thr[k]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("jurisdiction_id", help="UUID of the jurisdiction")
    parser.add_argument("--base-url", default=_DEFAULT_BASE)
    parser.add_argument("--muni", help="Drill down to a single municipality by name.")
    parser.add_argument("--only-broken", action="store_true",
                        help="Print only rows in 'broken' or 'degraded' bands.")
    parser.add_argument("--json", action="store_true",
                        help="Emit the raw JSON response instead of the formatted table.")
    args = parser.parse_args()

    url = (
        f"{args.base_url.rstrip('/')}"
        f"/api/jurisdictions/{args.jurisdiction_id}/_municipalities-health"
    )
    params: dict[str, str] = {}
    if args.muni:
        params["municipality"] = args.muni

    try:
        resp = httpx.get(url, params=params, timeout=300.0)
    except httpx.HTTPError as exc:
        print(f"network error: {exc!r}", file=sys.stderr)
        return 3

    if resp.status_code >= 400:
        print(f"HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 2

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        print(f"parse error: {exc}", file=sys.stderr)
        return 3

    if args.json:
        json.dump(data, sys.stdout, indent=2, default=str)
        print()
    else:
        _print_report(data, only_broken=args.only_broken)
    return 0


if __name__ == "__main__":
    sys.exit(main())
