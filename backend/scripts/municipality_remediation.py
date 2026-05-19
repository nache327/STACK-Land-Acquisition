"""Print the remediation playbook for a jurisdiction's municipalities.

Calls `/api/jurisdictions/{id}/_municipalities-remediation` and renders
the ordered action plan per muni — what's broken, what to do, in what
order. Operator pipes this into a worksheet and works top-down.

Usage:
    python scripts/municipality_remediation.py <jurisdiction_id>
    python scripts/municipality_remediation.py <jurisdiction_id> --muni "New Milford"
    python scripts/municipality_remediation.py <jurisdiction_id> --only-actionable
    python scripts/municipality_remediation.py <jurisdiction_id> --json

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

_BAND_ORDER = ["broken", "degraded", "partial", "operational", "empty"]
_SEVERITY_GLYPH = {"must": "❗", "should": "▶", "consider": "·"}


def _print_plan(muni: dict[str, Any]) -> None:
    name = muni.get("municipality") or "(jurisdiction)"
    band = muni.get("trustworthiness", "?")
    plan = muni.get("remediation") or {}
    steps = plan.get("steps") or []
    print()
    print(f"  [{band:<11}] {name}")
    if plan.get("escalate_to_engineer"):
        print("    ⚠ escalate to engineer — ambiguous failure")
    if plan.get("needs_operator_input"):
        for ni in plan["needs_operator_input"]:
            print(f"    ◆ needs input: {ni}")
    for gap in (plan.get("gaps") or [])[:5]:
        print(f"    ▸ {gap}")
    if not steps:
        if band == "operational":
            print("    (no remediation needed)")
        return
    print("    plan:")
    for s in steps:
        glyph = _SEVERITY_GLYPH.get(s.get("severity"), "·")
        deps = (
            f"  ← after {', '.join('#' + str(d) for d in s['dependencies'])}"
            if s.get("dependencies") else ""
        )
        print(f"      {glyph} #{s['step']:<2} {s['action_code']:<28} {s['label']}{deps}")
        if s.get("rationale"):
            print(f"           why: {s['rationale']}")
        if s.get("cli_hint"):
            print(f"           run: {s['cli_hint']}")


def _print_report(data: dict[str, Any], *, only_actionable: bool) -> None:
    print()
    print(f"Jurisdiction: {data.get('jurisdiction_name')} ({data.get('jurisdiction_id')})")
    print(f"  county_with_munis: {data.get('is_county_with_munis')}")
    print(f"  municipality_count: {data.get('municipality_count', 0)}")
    counts = data.get("band_counts") or {}
    if counts:
        line = "  bands: " + "  ".join(
            f"{b}={counts[b]}" for b in _BAND_ORDER if b in counts
        )
        print(line)
    nxt = data.get("next_actionable_municipality")
    if nxt:
        print(f"  next actionable: {nxt}")

    munis = data.get("municipalities") or []
    munis.sort(key=lambda m: (
        _BAND_ORDER.index(m.get("trustworthiness", "operational")),
        -(m.get("parcel_count") or 0),
    ))
    if only_actionable:
        munis = [
            m for m in munis
            if (m.get("remediation") or {}).get("steps")
            and not (m.get("remediation") or {}).get("escalate_to_engineer")
        ]
    for m in munis:
        _print_plan(m)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("jurisdiction_id")
    parser.add_argument("--base-url", default=_DEFAULT_BASE)
    parser.add_argument("--muni", help="Drill down to a single municipality.")
    parser.add_argument("--only-actionable", action="store_true",
                        help="Hide operational munis + engineer-escalated ones.")
    parser.add_argument("--json", action="store_true",
                        help="Emit raw JSON instead of the formatted plan.")
    args = parser.parse_args()

    url = (
        f"{args.base_url.rstrip('/')}"
        f"/api/jurisdictions/{args.jurisdiction_id}/_municipalities-remediation"
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
        _print_report(data, only_actionable=args.only_actionable)
    return 0


if __name__ == "__main__":
    sys.exit(main())
