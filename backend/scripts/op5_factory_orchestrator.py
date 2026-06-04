"""Op-5 factory orchestrator — per-county dispatch.

Per docs/OP5_FACTORY_72H_PLAN.md Pre-build A, this script lifts the proof
orchestrator into a per-county runner. It dispatches `op5_per_muni_runner.py`
as an isolated subprocess for every muni in the county directory, with a
6-hour per-muni wall-clock budget (failure-modes table). Results are
aggregated into ``/tmp/op5_factory/{county}_orchestrator_report.json``.

The orchestrator does NOT launch a real Phase-0 sweep on import — that is a
separate Master-authorized dispatch. This script is the executable surface;
the factory orchestrator agent imports / invokes it from its own runtime.

Idempotency: re-running on a county picks up only munis that are not yet
marked ``complete`` in the report file.

CLI:
    python backend/scripts/op5_factory_orchestrator.py \\
        --county bergen [--max-parallel 14] [--dry-run]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from op5_per_muni_runner import (  # noqa: E402
    ARTIFACT_ROOT,
    DATA_DIR,
    DEFAULT_NEAREST_WITHIN_METERS,
    DEFAULT_PREVIEW_BRANCH,
    EXIT_CARVE_OUT,
    EXIT_COMPLETE_NOT_OPERATIONAL,
    EXIT_COMPLETE_OPERATIONAL,
    EXIT_TRANSIENT_ERROR,
    MuniRecord,
    load_county_directory,
)

LOGGER = logging.getLogger("op5_factory_orchestrator")

PER_MUNI_WALL_CLOCK_S = 6 * 60 * 60  # 6 hours per OP5_FACTORY_72H_PLAN.md
# Default capped at 14 per CP-Pre Finding 1 (master decision; 20 was the
# spec ask, 14 is the DB-capacity-safe ceiling after the connection-pool
# review in docs/OP5_PRE_BUILD_REPORT.md).
DEFAULT_MAX_PARALLEL = 14

EXIT_TO_STATUS = {
    EXIT_COMPLETE_OPERATIONAL: "complete_operational",
    EXIT_COMPLETE_NOT_OPERATIONAL: "complete_not_operational",
    EXIT_CARVE_OUT: "carve_out",
    EXIT_TRANSIENT_ERROR: "transient_error",
}
COMPLETE_STATUSES = {"complete_operational", "complete_not_operational", "carve_out"}


@dataclass
class MuniReport:
    muni_code: str
    muni_name: str
    status: str
    exit_code: int
    coverage_pct: Optional[float] = None
    spot_check_pct: Optional[float] = None
    wall_clock_s: float = 0.0
    error: Optional[str] = None
    summary_path: Optional[str] = None
    log_tail: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "muni_code": self.muni_code,
            "muni_name": self.muni_name,
            "status": self.status,
            "exit_code": self.exit_code,
            "coverage_pct": self.coverage_pct,
            "spot_check_pct": self.spot_check_pct,
            "wall_clock_s": self.wall_clock_s,
            "error": self.error,
            "summary_path": self.summary_path,
            "log_tail": self.log_tail,
        }


def orchestrator_report_path(county: str, root: Path = ARTIFACT_ROOT) -> Path:
    return root / f"{county.strip().lower()}_orchestrator_report.json"


def load_prior_report(path: Path) -> dict[str, MuniReport]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("malformed prior report at %s; ignoring for idempotency", path)
        return {}
    rows = data.get("munis", []) if isinstance(data, dict) else data
    prior: dict[str, MuniReport] = {}
    for r in rows:
        key = (r.get("muni_code") or r.get("muni_name") or "").lower()
        if not key:
            continue
        prior[key] = MuniReport(
            muni_code=r.get("muni_code", ""),
            muni_name=r.get("muni_name", ""),
            status=r.get("status", ""),
            exit_code=int(r.get("exit_code", EXIT_TRANSIENT_ERROR)),
            coverage_pct=r.get("coverage_pct"),
            spot_check_pct=r.get("spot_check_pct"),
            wall_clock_s=float(r.get("wall_clock_s", 0.0)),
            error=r.get("error"),
            summary_path=r.get("summary_path"),
            log_tail=r.get("log_tail"),
        )
    return prior


def write_report(
    county: str,
    munis: dict[str, MuniReport],
    *,
    root: Path = ARTIFACT_ROOT,
) -> Path:
    path = orchestrator_report_path(county, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    totals = {"total": len(munis)}
    for st in EXIT_TO_STATUS.values():
        totals[st] = 0
    totals["factory_failed"] = 0
    for r in munis.values():
        totals[r.status] = totals.get(r.status, 0) + 1
    payload = {
        "county": county,
        "totals": totals,
        "munis": [r.to_dict() for r in munis.values()],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _run_per_muni_subprocess(
    county: str,
    muni: MuniRecord,
    *,
    preview_branch: str,
    nearest_within_meters: float,
    artifact_root: Path,
    data_dir: Path,
    runner_path: Path,
    per_muni_timeout_s: int,
) -> MuniReport:
    """Invoke `op5_per_muni_runner.py` as a subprocess so a per-muni crash
    can't take the orchestrator down. Returns a MuniReport with status/exit.
    """
    t0 = time.time()
    cmd = [
        sys.executable,
        str(runner_path),
        "--county", county,
        "--muni", muni.muni_name,
        "--preview-branch", preview_branch,
        "--nearest-within-meters", str(nearest_within_meters),
        "--artifact-root", str(artifact_root),
        "--data-dir", str(data_dir),
    ]
    LOGGER.info("subprocess[%s/%s] start: %s", county, muni.muni_name, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=per_muni_timeout_s,
            check=False,
        )
        exit_code = result.returncode
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        error: Optional[str] = None
    except subprocess.TimeoutExpired as exc:
        wall = time.time() - t0
        LOGGER.warning(
            "subprocess[%s/%s] TIMED OUT after %.0fs (budget %ds); marking factory_failed",
            county, muni.muni_name, wall, per_muni_timeout_s,
        )
        return MuniReport(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            status="factory_failed",
            exit_code=124,
            wall_clock_s=round(wall, 2),
            error=f"per-muni budget exceeded: {per_muni_timeout_s}s",
            log_tail=str(exc)[:512],
        )
    except Exception as exc:  # noqa: BLE001
        wall = time.time() - t0
        return MuniReport(
            muni_code=muni.muni_code,
            muni_name=muni.muni_name,
            status="factory_failed",
            exit_code=125,
            wall_clock_s=round(wall, 2),
            error=f"subprocess invocation failed: {exc}",
        )

    wall = round(time.time() - t0, 2)
    status = EXIT_TO_STATUS.get(exit_code, "factory_failed")
    coverage_pct: Optional[float] = None
    spot_check_pct: Optional[float] = None
    summary_path = None

    # Try to read the cp3_summary.json the runner wrote.
    from op5_per_muni_runner import cp3_summary_path  # local import to avoid cycle on import
    sp = cp3_summary_path(county, muni.muni_name, root=artifact_root)
    if sp.exists():
        try:
            payload = json.loads(sp.read_text(encoding="utf-8"))
            coverage_pct = payload.get("parcel_zoning_code_coverage_pct")
            spot_check_pct = payload.get("spot_check_pass_pct")
            summary_path = str(sp)
        except json.JSONDecodeError:
            pass

    return MuniReport(
        muni_code=muni.muni_code,
        muni_name=muni.muni_name,
        status=status,
        exit_code=exit_code,
        coverage_pct=coverage_pct,
        spot_check_pct=spot_check_pct,
        wall_clock_s=wall,
        error=stderr[-512:] if stderr and exit_code != EXIT_COMPLETE_OPERATIONAL else None,
        summary_path=summary_path,
        log_tail=(stdout[-512:] + ("\n--stderr--\n" + stderr[-512:] if stderr else "")),
    )


def orchestrate(
    county: str,
    *,
    max_parallel: int = DEFAULT_MAX_PARALLEL,
    preview_branch: str = DEFAULT_PREVIEW_BRANCH,
    nearest_within_meters: float = DEFAULT_NEAREST_WITHIN_METERS,
    artifact_root: Path = ARTIFACT_ROOT,
    data_dir: Path = DATA_DIR,
    runner_path: Optional[Path] = None,
    per_muni_timeout_s: int = PER_MUNI_WALL_CLOCK_S,
    dry_run: bool = False,
) -> dict:
    runner_path = runner_path or (Path(__file__).resolve().parent / "op5_per_muni_runner.py")
    if not runner_path.exists():
        raise FileNotFoundError(f"per-muni runner not found at {runner_path}")

    all_munis = load_county_directory(county, data_dir=data_dir)
    report_path = orchestrator_report_path(county, root=artifact_root)
    prior = load_prior_report(report_path)

    # Idempotent skip set.
    to_run: list[MuniRecord] = []
    munis_state: dict[str, MuniReport] = {}
    for m in all_munis:
        key = (m.muni_code or m.muni_name).lower()
        if key in prior and prior[key].status in COMPLETE_STATUSES:
            munis_state[key] = prior[key]
        else:
            to_run.append(m)
            # seed a pending entry so dry-run output is informative
            munis_state[key] = prior.get(key) or MuniReport(
                muni_code=m.muni_code,
                muni_name=m.muni_name,
                status="pending",
                exit_code=-1,
            )

    LOGGER.info(
        "%s: %d munis total, %d already complete, %d to run",
        county, len(all_munis), len(all_munis) - len(to_run), len(to_run),
    )

    if dry_run:
        return {
            "county": county,
            "total": len(all_munis),
            "already_complete": len(all_munis) - len(to_run),
            "to_run": [m.muni_name for m in to_run],
            "max_parallel": max_parallel,
        }

    # ThreadPoolExecutor — subprocess.run already isolates the child; the
    # parent thread just blocks. Plenty fast for ~5 in-flight munis.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, max_parallel)) as ex:
        futures = {
            ex.submit(
                _run_per_muni_subprocess,
                county, m,
                preview_branch=preview_branch,
                nearest_within_meters=nearest_within_meters,
                artifact_root=artifact_root,
                data_dir=data_dir,
                runner_path=runner_path,
                per_muni_timeout_s=per_muni_timeout_s,
            ): m for m in to_run
        }
        for fut in concurrent.futures.as_completed(futures):
            m = futures[fut]
            try:
                report = fut.result()
            except Exception as exc:  # noqa: BLE001
                report = MuniReport(
                    muni_code=m.muni_code,
                    muni_name=m.muni_name,
                    status="factory_failed",
                    exit_code=126,
                    error=f"orchestrator caught: {exc}",
                )
            key = (m.muni_code or m.muni_name).lower()
            munis_state[key] = report
            # Persist after each completion — partial-progress resumability.
            write_report(county, munis_state, root=artifact_root)
            LOGGER.info(
                "completed %s/%s -> %s (exit=%d, cov=%s, spot=%s, %.1fs)",
                county, m.muni_name, report.status, report.exit_code,
                report.coverage_pct, report.spot_check_pct, report.wall_clock_s,
            )

    final_path = write_report(county, munis_state, root=artifact_root)
    totals: dict[str, int] = {}
    for r in munis_state.values():
        totals[r.status] = totals.get(r.status, 0) + 1
    return {
        "county": county,
        "report_path": str(final_path),
        "totals": totals,
        "total": len(munis_state),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--county", required=True)
    ap.add_argument("--max-parallel", type=int, default=DEFAULT_MAX_PARALLEL)
    ap.add_argument("--preview-branch", default=DEFAULT_PREVIEW_BRANCH)
    ap.add_argument(
        "--nearest-within-meters", type=float, default=DEFAULT_NEAREST_WITHIN_METERS,
    )
    ap.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT)
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument(
        "--per-muni-timeout-s", type=int, default=PER_MUNI_WALL_CLOCK_S,
        help="Per-muni wall-clock budget. Default 6h.",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default=os.environ.get("OP5_LOG_LEVEL", "INFO"))
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    try:
        out = orchestrate(
            args.county,
            max_parallel=args.max_parallel,
            preview_branch=args.preview_branch,
            nearest_within_meters=args.nearest_within_meters,
            artifact_root=args.artifact_root,
            data_dir=args.data_dir,
            per_muni_timeout_s=args.per_muni_timeout_s,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, KeyError) as exc:
        LOGGER.error("orchestrate failed: %s", exc)
        return 2
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
