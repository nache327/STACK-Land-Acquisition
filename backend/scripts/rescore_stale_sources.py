"""Bulk re-score stale zoning_sources rows for one jurisdiction (CLI).

Three modes:

    # Dry-run (default): preview the diff, no DB writes.
    python scripts/rescore_stale_sources.py <jurisdiction_id>

    # Live: apply changes; save the response snapshot for rollback safety.
    python scripts/rescore_stale_sources.py <jurisdiction_id> --apply \\
        --snapshot-out rescore-bergen-$(date +%s).json

    # Rollback: re-submit a saved snapshot to restore prior state.
    python scripts/rescore_stale_sources.py <jurisdiction_id> \\
        --rollback rescore-bergen-1234567890.json

Safeguards:
  - Default is dry-run; --apply is required to mutate.
  - --snapshot-out writes the full response (with `before` payloads) so
    you can re-submit it to rollback if a downstream issue is found.
  - --max-rows caps the batch; the server also enforces an upper bound.
  - Verified + rejected rows are never mutated server-side regardless
    of flags here — this client cannot override that.

Exit codes:
    0  ran cleanly
    1  apply mode without --snapshot-out (refused — would lose rollback safety)
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


def _print_summary(resp: dict[str, Any]) -> None:
    print()
    print(f"Jurisdiction: {resp.get('jurisdiction_name')} ({resp.get('jurisdiction_id')})")
    print(f"Mode: {'DRY-RUN' if resp.get('dry_run') else 'LIVE'}    "
          f"scanned: {resp.get('scanned', 0)}")
    s = resp.get("summary") or {}
    print()
    print(f"  changed:    {s.get('changed', 0)}")
    print(f"  no change:  {s.get('no_change', 0)}")
    print(f"  decreased:  {s.get('score_decreased', 0)}")
    print(f"  increased:  {s.get('score_increased', 0)}")
    print(f"  dropped below 70: {s.get('newly_below_threshold_70', 0)}")
    print(f"  crossed above 70: {s.get('newly_above_threshold_70', 0)}")
    print(f"  live verdict = disjoint: {s.get('live_verdict_disjoint', 0)}")
    print(f"  applied:    {s.get('applied', 0)}")
    print(f"  skipped (verified/rejected): {s.get('skipped_immutable', 0)}")

    dist = s.get("score_delta_distribution") or {}
    if dist:
        print()
        print("  score-delta distribution:")
        order = ["≤-50", "-49..-20", "-19..-1", "0", "1..19", "20..49", "≥50"]
        for k in order:
            if k in dist:
                print(f"    {k:<9}  {dist[k]}")

    changes = resp.get("changes") or []
    if changes:
        print()
        print(f"  showing first 12 of {len(changes)} changes:")
        for c in changes[:12]:
            tag = "✗" if not c.get("applied") else "✓"
            print(f"    {tag} {c['before']['confidence_score']:>3} → "
                  f"{c['after']['confidence_score']:<3} "
                  f"(Δ {c['delta']:+d}, {c.get('live_verdict') or '—'}) "
                  f"{c.get('municipality_name') or '—'} :: {c.get('title')}")
            if c.get("skipped_reason"):
                print(f"           skipped: {c['skipped_reason']}")

    errors = resp.get("errors") or []
    if errors:
        print()
        print(f"  errors: {len(errors)}")
        for e in errors[:5]:
            print(f"    {e.get('source_id')}: {e.get('error')}")


def _run_rescore(args: argparse.Namespace) -> int:
    url = (
        f"{args.base_url.rstrip('/')}"
        f"/api/jurisdictions/{args.jurisdiction_id}/_rescore-stale-sources"
    )
    body = {
        "dry_run": not args.apply,
        "max_rows": args.max_rows,
        "stale_only": not args.all_rows,
        "concurrency": args.concurrency,
    }
    if args.include_verified:
        body["only_status"] = ["pending", "needs_review", "verified", "rejected"]

    try:
        resp = httpx.post(url, json=body, timeout=600.0)
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

    if args.snapshot_out:
        with open(args.snapshot_out, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"snapshot saved to {args.snapshot_out}")

    if args.json:
        json.dump(data, sys.stdout, indent=2, default=str)
        print()
    else:
        _print_summary(data)
    return 0


def _run_rollback(args: argparse.Namespace) -> int:
    with open(args.rollback) as f:
        snapshot = json.load(f)
    # Accept either a full rescore response or a bare list of `before` records.
    if isinstance(snapshot, dict) and "changes" in snapshot:
        rows = [c["before"] for c in snapshot["changes"] if c.get("applied")]
    elif isinstance(snapshot, list):
        rows = snapshot
    else:
        print("rollback file must be a rescore response or a list of `before` records",
              file=sys.stderr)
        return 1
    if not rows:
        print("rollback file has 0 applied rows — nothing to do.", file=sys.stderr)
        return 0

    url = (
        f"{args.base_url.rstrip('/')}"
        f"/api/jurisdictions/{args.jurisdiction_id}/_rescore-rollback"
    )
    try:
        resp = httpx.post(url, json={"snapshots": rows}, timeout=300.0)
    except httpx.HTTPError as exc:
        print(f"network error: {exc!r}", file=sys.stderr)
        return 3
    if resp.status_code >= 400:
        print(f"HTTP {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 2

    data = resp.json()
    print(f"restored: {data.get('restored', 0)}")
    if data.get("skipped"):
        print(f"skipped: {len(data['skipped'])} (post-rescore verify/reject)")
    if data.get("not_found"):
        print(f"not found: {len(data['not_found'])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("jurisdiction_id", help="UUID of the jurisdiction to rescore")
    parser.add_argument("--base-url", default=_DEFAULT_BASE)
    parser.add_argument("--apply", action="store_true",
                        help="Live mode — applies changes. Without this flag, dry-run only.")
    parser.add_argument("--max-rows", type=int, default=200,
                        help="Cap on rows touched (server clamps at 1000).")
    parser.add_argument("--all-rows", action="store_true",
                        help="Re-score every row, not just rows with stale breakdowns.")
    parser.add_argument("--include-verified", action="store_true",
                        help="Scan verified/rejected rows too (still never mutated; "
                             "useful for inspecting how their scores would change).")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Concurrent live probes (default 8, max 32).")
    parser.add_argument("--snapshot-out",
                        help="Write the full response to this file (required for --apply).")
    parser.add_argument("--rollback", metavar="SNAPSHOT_FILE",
                        help="Restore prior state from a previously saved snapshot.")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON instead of formatted summary.")
    args = parser.parse_args()

    if args.rollback:
        return _run_rollback(args)

    if args.apply and not args.snapshot_out:
        print(
            "refusing to --apply without --snapshot-out — "
            "rollback safety requires a saved snapshot.",
            file=sys.stderr,
        )
        return 1

    return _run_rescore(args)


if __name__ == "__main__":
    sys.exit(main())
