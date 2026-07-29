"""Run long maintenance scripts inside the Railway worker instead of on a laptop.

WHY THIS EXISTS. The heavy data jobs — radial population backfills, full
re-scores, ring recomputes — take hours. Orchestrated from Nache's machine they
die when it sleeps, so they can never use the overnight window: one such run lost
9 of 151 counties overnight, and every one of them needed retry logic bolted on
because the home-network link kept dropping mid-query. Meanwhile the actual work
already executes on Supabase; the local process is just orchestration sitting in
`await`. Moving that orchestration next to the database removes both the fragile
link and the overnight deadline.

SECURITY — read before adding a job. This is reachable over HTTP (admin-secret
gated), so it must never become a remote shell:

  * Jobs are an ALLOWLIST of names defined in this module. A caller chooses a
    name; it cannot supply a command, a module path, or a script filename.
  * Every parameter is coerced and range-checked by an explicit builder below.
    Nothing from the request is interpolated into a shell string.
  * Subprocesses are spawned WITHOUT a shell (list argv), so shell metacharacters
    in any value are inert even if a builder were sloppy.

Add a job by adding a JobSpec here — never by widening the parameter surface.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import long_running_session_maker

logger = logging.getLogger(__name__)

# backend/ — scripts live in backend/scripts and expect that as cwd.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Keep the retained output bounded: a multi-hour job can emit a lot, and this
# column is for diagnosis, not archival.
_LOG_TAIL_MAX_CHARS = 20_000


# ─── Parameter coercion helpers (never trust the request) ──────────────────

def _opt_int(v: Any, lo: int, hi: int) -> int | None:
    if v is None:
        return None
    n = int(v)
    if not lo <= n <= hi:
        raise ValueError(f"value {n} outside allowed range {lo}..{hi}")
    return n


def _opt_float(v: Any, lo: float, hi: float) -> float | None:
    if v is None:
        return None
    f = float(v)
    if not lo <= f <= hi:
        raise ValueError(f"value {f} outside allowed range {lo}..{hi}")
    return f


def _opt_uuid(v: Any) -> str | None:
    """Accept only a real UUID, returned in canonical form — so nothing
    resembling a flag or a path can reach argv."""
    if v is None:
        return None
    import uuid as _uuid
    return str(_uuid.UUID(str(v)))


def _opt_uuid_csv(v: Any) -> str | None:
    if v is None:
        return None
    parts = [p.strip() for p in str(v).split(",") if p.strip()]
    if not parts:
        return None
    import uuid as _uuid
    return ",".join(str(_uuid.UUID(p)) for p in parts)


def _opt_iso_ts(v: Any) -> str | None:
    """Validate as an ISO timestamp and re-emit it, so only a well-formed
    timestamp can be passed through."""
    if v is None:
        return None
    from datetime import datetime
    return datetime.fromisoformat(str(v)).isoformat()


def _flag(args: dict, name: str) -> bool:
    return bool(args.get(name))


# ─── Job registry ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class JobSpec:
    script: str                              # filename under backend/scripts
    build_argv: Callable[[dict], list[str]]  # validated extra argv
    description: str


def _rescore_argv(a: dict) -> list[str]:
    argv: list[str] = []
    if (jid := _opt_uuid(a.get("jurisdiction"))) is not None:
        argv += ["--jurisdiction", jid]
    if (fl := _opt_uuid_csv(a.get("filter"))) is not None:
        argv += ["--filter", fl]
    if (si := _opt_int(a.get("start_index"), 0, 100_000)) is not None:
        argv += ["--start-index", str(si)]
    if (ei := _opt_int(a.get("end_index"), 0, 100_000)) is not None:
        argv += ["--end-index", str(ei)]
    if (r := _opt_int(a.get("retries"), 1, 20)) is not None:
        argv += ["--retries", str(r)]
    return argv


def _backfill_radial_argv(a: dict) -> list[str]:
    argv: list[str] = []
    if _flag(a, "area_weighted"):
        argv.append("--area-weighted")
    if _flag(a, "redo"):
        argv.append("--redo")
    if _flag(a, "skip_saturation"):
        argv.append("--skip-saturation")
    if (jid := _opt_uuid(a.get("jurisdiction"))) is not None:
        argv += ["--jurisdiction", jid]
    if (ts := _opt_iso_ts(a.get("redo_after"))) is not None:
        argv += ["--redo-after", ts]
    if (g := _opt_float(a.get("grid_deg"), 0.0005, 0.05)) is not None:
        argv += ["--grid-deg", str(g)]
    if (r := _opt_int(a.get("retries"), 1, 20)) is not None:
        argv += ["--retries", str(r)]
    return argv


def _validate_radial_argv(a: dict) -> list[str]:
    argv: list[str] = []
    if (jid := _opt_uuid(a.get("jurisdiction"))) is not None:
        argv += ["--jurisdiction", jid]
    if (s := _opt_int(a.get("sample"), 1, 200)) is not None:
        argv += ["--sample", str(s)]
    if (t := _opt_float(a.get("tolerance_pct"), 0.1, 100.0)) is not None:
        argv += ["--tolerance-pct", str(t)]
    return argv


def _recompute_ring_argv(a: dict) -> list[str]:
    argv: list[str] = []
    if (jid := _opt_uuid(a.get("jurisdiction"))) is not None:
        argv += ["--jurisdiction", jid]
    if (lim := _opt_int(a.get("limit"), 1, 200_000)) is not None:
        argv += ["--limit", str(lim)]
    return argv


def _detect_stale_argv(a: dict) -> list[str]:
    argv: list[str] = []
    if (jid := _opt_uuid(a.get("jurisdiction"))) is not None:
        argv += ["--jurisdiction", jid]
    if (lim := _opt_int(a.get("limit"), 1, 100_000)) is not None:
        argv += ["--limit", str(lim)]
    return argv


def _push_dashboard_argv(a: dict) -> list[str]:
    argv: list[str] = []
    # filter_id is buybox_filters.id, a UUID. It was coerced as an int here at
    # first, mirroring the CLI's own `type=int` — but the PK is uuid, so an int
    # could never match and the single-filter smoke test was impossible.
    if (fid := _opt_uuid(a.get("filter_id"))) is not None:
        argv += ["--filter-id", fid]
    return argv


JOBS: dict[str, JobSpec] = {
    "push_dashboard": JobSpec(
        "push_dashboard.py", _push_dashboard_argv,
        "Push buy-box deals to the dashboard Deal Pipeline board. Must run on "
        "Railway — PORTFOLIO_DASHBOARD_DATABASE_URL is not set on dev machines, "
        "where it silently no-ops. Never deletes a triaged card and never writes "
        "the disposition columns; it does refresh score/tier facts.",
    ),
    "rescore_all": JobSpec(
        "rescore_all_jurisdictions.py", _rescore_argv,
        "Re-score parcels (all jurisdictions, or one) under the seed + board filters.",
    ),
    "backfill_radial": JobSpec(
        "backfill_radial_population.py", _backfill_radial_argv,
        "Backfill 3-mi radial population (use area_weighted=true).",
    ),
    "validate_radial": JobSpec(
        "validate_radial_area_weighted.py", _validate_radial_argv,
        "At-scale validation gate for the radial population values.",
    ),
    "recompute_ring_population": JobSpec(
        "recompute_ring_population.py", _recompute_ring_argv,
        "Per-parcel isochrone recompute of dt ring POPULATION only.",
    ),
    "detect_stale_rings": JobSpec(
        "detect_stale_ring_metrics.py", _detect_stale_argv,
        "Report dt=10 ring rows inconsistent with the 3-mi radial population.",
    ),
    "pop_band_delta": JobSpec(
        "report_pop_band_board_delta.py", lambda a: [],
        "Report the board impact of the 3-mi population hysteresis band.",
    ),
}


def resolve(job_name: str, args: dict | None) -> list[str]:
    """Validate a request and return the full argv. Raises ValueError on
    anything unrecognised — callers surface that as a 400, never a 500."""
    spec = JOBS.get(job_name)
    if spec is None:
        raise ValueError(
            f"unknown job {job_name!r}; allowed: {sorted(JOBS)}"
        )
    script = _BACKEND_ROOT / "scripts" / spec.script
    if not script.is_file():
        raise ValueError(f"job {job_name!r} script missing: {spec.script}")
    # sys.executable, not "python": the container's interpreter, and never a
    # shell. Argv is a list, so metacharacters in values cannot be interpreted.
    return [sys.executable, "-u", str(script), *spec.build_argv(args or {})]


# ─── Run + record ─────────────────────────────────────────────────────────

async def _update(run_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    async with long_running_session_maker() as db:
        await db.execute(
            text(f"UPDATE ops_job_run SET {sets} WHERE id = :id"),
            {**fields, "id": run_id},
        )
        await db.commit()


async def create_run(job_name: str, args: dict | None) -> int:
    async with long_running_session_maker() as db:
        row = (await db.execute(
            text(
                "INSERT INTO ops_job_run (job_name, args, status) "
                "VALUES (:n, CAST(:a AS jsonb), 'queued') RETURNING id"
            ),
            {"n": job_name, "a": json.dumps(args or {})},
        )).first()
        await db.commit()
    return int(row[0])


async def execute_run(run_id: int, job_name: str, args: dict | None) -> int:
    """Run the job as a subprocess, streaming its output into ops_job_run.

    Subprocess rather than importing the script: these scripts own their argparse
    entrypoints and their own DB engines/pools, and a crash stays contained
    instead of taking the worker down with it.
    """
    try:
        argv = resolve(job_name, args)
    except ValueError as exc:
        await _update(run_id, status="failed", error=str(exc),
                      finished_at=_now_sql())
        return 2

    await _update(run_id, status="running", started_at=_now_sql())
    logger.info("maintenance job %s (run %s) starting: %s", job_name, run_id, argv[2:])

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=str(_BACKEND_ROOT), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )

    tail: list[str] = []
    last_flush = 0.0
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        line = raw.decode("utf-8", "replace").rstrip()
        if not line:
            continue
        tail.append(line)
        # Keep the retained tail bounded.
        while sum(len(x) + 1 for x in tail) > _LOG_TAIL_MAX_CHARS:
            tail.pop(0)
        # Throttle DB writes: progress is for humans polling, not a log sink.
        now = asyncio.get_running_loop().time()
        if now - last_flush > 10.0:
            last_flush = now
            try:
                await _update(run_id, progress=line[:500], log_tail="\n".join(tail))
            except Exception:  # noqa: BLE001 — never let logging kill the job
                logger.warning("maintenance job %s: progress write failed", run_id)

    code = await proc.wait()
    await _update(
        run_id,
        status="succeeded" if code == 0 else "failed",
        exit_code=code,
        finished_at=_now_sql(),
        progress=(tail[-1][:500] if tail else None),
        log_tail="\n".join(tail),
    )
    logger.info("maintenance job %s (run %s) finished rc=%s", job_name, run_id, code)
    return code


def _now_sql():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
