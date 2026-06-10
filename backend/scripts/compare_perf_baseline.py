"""Compare a benchmark JSON against the committed baseline JSON.

Used by `.github/workflows/perf-baseline.yml` to gate PRs that touch
the parcels-search code path, and to fire issues on the weekly cron.
Stdlib-only on purpose — runs on a vanilla Actions runner with no
extra `pip install`.

Inputs
------
--baseline   Path to the committed baseline (e.g.
             docs/PERF_BASELINE_2026_06_10.json).
--current    Path to the latest benchmark output (from
             benchmark_parcels_search.py).
--signal-threshold      Fractional movement above which a jurisdiction
                        appears in the diff table (either direction).
                        Default 0.25.
--regression-threshold  Fractional regression that triggers a non-zero
                        exit on cold_bbox_p50 or cold_whole_p50.
                        Default 0.50.
--min-absolute-regression-s
                        Minimum absolute (current - baseline) increase
                        in seconds required IN ADDITION TO the relative
                        threshold before a metric is gated as a
                        regression. Default 3.0. The first cross-run
                        (workflow run 27248352894 vs 2026-06-09 baseline)
                        showed fleet-wide ±25-50% drift between
                        identical prod code measured at different
                        times — three metrics crossed 50% relative
                        with absolute deltas of +1.47 / +2.07 / +2.85 s,
                        all noise. 3.0 s clears that noise band while
                        still catching real ≥3 s absolute regressions.
--diff-out   Where to write the markdown diff. Default stdout.

Exit codes
----------
0   No regressions above `--regression-threshold` on cold_bbox_p50 or
    cold_whole_p50. The diff may still list movements (improvements
    or sub-threshold regressions) for human review.
1   At least one jurisdiction regressed cold_bbox_p50 OR
    cold_whole_p50 by more than `--regression-threshold`.

What it skips by design
-----------------------
- Jurisdictions in `current` but not `baseline` → noted as "new" in
  the diff; never a regression (no baseline to compare against).
- Jurisdictions in `baseline` but not `current` → noted as "missing";
  not a regression. The cron may want to investigate why coverage
  shrank, but that's a separate signal.
- Warm metrics → listed in the diff table when they move >signal but
  never failure-gated. Warm path is the in-process LRU memo; if it
  regresses it's a code change, not infrastructure drift, and the
  cold gate will already have caught the underlying problem.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# Failure gate is anchored on the customer-facing cold paths. Warm
# metrics are surfaced in the diff but not enforced.
GATED_METRICS = ("cold_bbox", "cold_whole")
ALL_METRICS = ("cold_bbox", "warm_bbox", "cold_whole", "warm_whole")


def _index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index a benchmark report by jurisdiction_id for O(1) lookup."""
    return {r["jurisdiction_id"]: r for r in report.get("results", [])}


def _p50(row: dict[str, Any], metric: str) -> float | None:
    """Pull a metric's p50_s, tolerating shape drift / missing fields."""
    bucket = row.get(metric)
    if not isinstance(bucket, dict):
        return None
    val = bucket.get("p50_s")
    return float(val) if val is not None else None


def _pct(delta: float | None) -> str:
    if delta is None:
        return "—"
    return f"{delta * 100:+.1f}%"


def _fmt_seconds(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "—"


def _compute_movement(
    base: dict[str, Any] | None,
    cur: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """For each metric, compute baseline / current / fractional delta."""
    out: dict[str, dict[str, Any]] = {}
    for m in ALL_METRICS:
        b = _p50(base or {}, m)
        c = _p50(cur or {}, m)
        if b is None or c is None or b <= 0:
            delta = None
        else:
            delta = (c - b) / b
        out[m] = {"baseline": b, "current": c, "delta_frac": delta}
    return out


def _render_diff_markdown(
    baseline_meta: dict[str, Any],
    current_meta: dict[str, Any],
    rows: list[dict[str, Any]],
    new_jurisdictions: list[dict[str, Any]],
    missing_jurisdictions: list[dict[str, Any]],
    regression_threshold: float,
    signal_threshold: float,
    min_absolute_regression_s: float,
    regressions: list[dict[str, Any]],
) -> str:
    out: list[str] = []
    out.append("# Perf-baseline diff")
    out.append("")
    out.append(
        f"- Baseline: `{baseline_meta.get('run_started_at', 'unknown')}` "
        f"({baseline_meta.get('api_base', 'unknown')})"
    )
    out.append(
        f"- Current:  `{current_meta.get('run_started_at', 'unknown')}` "
        f"({current_meta.get('api_base', 'unknown')})"
    )
    out.append(f"- Signal threshold (listed): ±{signal_threshold * 100:.0f}%")
    out.append(
        f"- Regression threshold (gates the workflow): "
        f"+{regression_threshold * 100:.0f}% relative AND "
        f"+{min_absolute_regression_s:.1f}s absolute on cold_bbox_p50 "
        f"OR cold_whole_p50"
    )
    out.append("")
    if regressions:
        out.append(
            f"## ❌ {len(regressions)} regression(s) above "
            f"+{regression_threshold * 100:.0f}% AND "
            f"+{min_absolute_regression_s:.1f}s absolute"
        )
        out.append("")
        out.append(
            "| Jurisdiction | Metric | Baseline | Current | "
            "Δ (rel) | Δ (abs) |"
        )
        out.append("|---|---|---:|---:|---:|---:|")
        for r in regressions:
            out.append(
                f"| {r['name']} | `{r['metric']}` | "
                f"{_fmt_seconds(r['baseline'])} s | "
                f"{_fmt_seconds(r['current'])} s | "
                f"**{_pct(r['delta_frac'])}** | "
                f"+{r.get('delta_s', 0):.2f} s |"
            )
        out.append("")
    else:
        out.append(
            f"## ✅ No regressions above +{regression_threshold * 100:.0f}% "
            f"AND +{min_absolute_regression_s:.1f}s absolute "
            f"on cold_bbox_p50 or cold_whole_p50."
        )
        out.append("")
    if rows:
        out.append(
            f"## Movements above ±{signal_threshold * 100:.0f}% "
            f"(all metrics, signal floor)"
        )
        out.append("")
        out.append(
            "| Jurisdiction | Metric | Baseline | Current | Δ |"
        )
        out.append("|---|---|---:|---:|---:|")
        for r in rows:
            out.append(
                f"| {r['name']} | `{r['metric']}` | "
                f"{_fmt_seconds(r['baseline'])} s | "
                f"{_fmt_seconds(r['current'])} s | "
                f"{_pct(r['delta_frac'])} |"
            )
        out.append("")
    else:
        out.append(
            f"_No metrics moved more than ±{signal_threshold * 100:.0f}% "
            f"in any jurisdiction._"
        )
        out.append("")
    if new_jurisdictions:
        out.append("## New jurisdictions (no baseline yet)")
        out.append("")
        for j in new_jurisdictions:
            out.append(f"- {j['name']}")
        out.append("")
    if missing_jurisdictions:
        out.append("## Missing in current (in baseline, not in this run)")
        out.append("")
        for j in missing_jurisdictions:
            out.append(f"- {j['name']}")
        out.append("")
    return "\n".join(out) + "\n"


def _diff(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    regression_threshold: float,
    signal_threshold: float,
    min_absolute_regression_s: float,
) -> tuple[str, list[dict[str, Any]]]:
    base_idx = _index(baseline)
    cur_idx = _index(current)

    rows: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    new_jurisdictions: list[dict[str, Any]] = []
    missing_jurisdictions: list[dict[str, Any]] = []

    for jid, cur_row in cur_idx.items():
        base_row = base_idx.get(jid)
        name = cur_row.get("jurisdiction_name") or jid
        if base_row is None:
            new_jurisdictions.append({"id": jid, "name": name})
            continue
        movements = _compute_movement(base_row, cur_row)
        for metric, mv in movements.items():
            delta = mv["delta_frac"]
            if delta is None:
                continue
            if abs(delta) >= signal_threshold:
                rows.append({
                    "name": name,
                    "metric": metric,
                    "baseline": mv["baseline"],
                    "current": mv["current"],
                    "delta_frac": delta,
                })
            # Two-gate: BOTH relative > regression_threshold AND
            # absolute (current - baseline) > min_absolute_regression_s.
            # The absolute floor filters cross-run noise on cheap
            # metrics — empirical evidence in workflow run
            # 27248352894 showed 3 noise crossings of the 50% gate at
            # absolute deltas of +1.47 / +2.07 / +2.85 s while prod
            # code was unchanged. 3.0 s default clears that noise band
            # without masking real ≥3 s regressions.
            base = mv["baseline"]
            cur = mv["current"]
            abs_delta = (cur - base) if (cur is not None and base is not None) else None
            if (
                metric in GATED_METRICS
                and delta > regression_threshold
                and abs_delta is not None
                and abs_delta > min_absolute_regression_s
            ):
                regressions.append({
                    "name": name,
                    "metric": metric,
                    "baseline": base,
                    "current": cur,
                    "delta_frac": delta,
                    "delta_s": abs_delta,
                })
    for jid, base_row in base_idx.items():
        if jid not in cur_idx:
            missing_jurisdictions.append({
                "id": jid,
                "name": base_row.get("jurisdiction_name") or jid,
            })

    # Sort the diff table by absolute movement (biggest signal first),
    # regression table by delta descending (worst first), missing/new
    # alphabetically.
    rows.sort(key=lambda r: abs(r["delta_frac"]), reverse=True)
    regressions.sort(key=lambda r: r["delta_frac"], reverse=True)
    new_jurisdictions.sort(key=lambda r: r["name"])
    missing_jurisdictions.sort(key=lambda r: r["name"])

    md = _render_diff_markdown(
        baseline_meta=baseline,
        current_meta=current,
        rows=rows,
        new_jurisdictions=new_jurisdictions,
        missing_jurisdictions=missing_jurisdictions,
        regression_threshold=regression_threshold,
        signal_threshold=signal_threshold,
        min_absolute_regression_s=min_absolute_regression_s,
        regressions=regressions,
    )
    return md, regressions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument(
        "--regression-threshold", type=float, default=0.50,
        help="Fractional regression that triggers exit 1. Default 0.50 (=+50%).",
    )
    parser.add_argument(
        "--signal-threshold", type=float, default=0.25,
        help="Fractional movement that lists a row in the diff. Default 0.25.",
    )
    parser.add_argument(
        "--min-absolute-regression-s", type=float, default=3.0,
        help=(
            "Minimum absolute (current - baseline) increase in seconds "
            "REQUIRED in addition to the relative threshold before a "
            "metric is gated. Default 3.0. Filters cross-run noise on "
            "cheap metrics."
        ),
    )
    parser.add_argument(
        "--diff-out",
        help="Path to write the markdown diff. Default stdout.",
    )
    args = parser.parse_args()

    baseline = json.loads(Path(args.baseline).read_text())
    current = json.loads(Path(args.current).read_text())
    md, regressions = _diff(
        baseline,
        current,
        regression_threshold=args.regression_threshold,
        signal_threshold=args.signal_threshold,
        min_absolute_regression_s=args.min_absolute_regression_s,
    )
    if args.diff_out:
        Path(args.diff_out).write_text(md)
    else:
        sys.stdout.write(md)
    if regressions:
        sys.stderr.write(
            f"\n❌ {len(regressions)} regression(s) above "
            f"+{args.regression_threshold * 100:.0f}% "
            f"AND +{args.min_absolute_regression_s:.1f}s absolute.\n"
        )
        return 1
    sys.stderr.write(
        f"\n✅ no regressions above +{args.regression_threshold * 100:.0f}% "
        f"AND +{args.min_absolute_regression_s:.1f}s absolute.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
