"""Admin API to run long maintenance jobs in the Railway worker.

Replaces "background a script on Nache's laptop and hope it stays awake" — see
app/services/maintenance_jobs for the why and the security model.

Every route here is admin-secret gated at registration (main.py). The job surface
is an ALLOWLIST: a caller picks a job NAME and passes typed parameters, and can
never supply a command, a script path, or a shell string.
"""
from __future__ import annotations

import os

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import long_running_session_maker
from app.services.maintenance_jobs import JOBS, create_run, resolve

router = APIRouter(tags=["admin-maintenance"])


class RunJobRequest(BaseModel):
    job: str = Field(..., description="Allowlisted job name (see GET /admin/maintenance/jobs)")
    args: dict[str, Any] = Field(default_factory=dict)


class RunJobAccepted(BaseModel):
    run_id: int
    job: str
    argv_preview: list[str]


@router.get("/admin/maintenance/jobs")
async def list_jobs() -> dict:
    """The allowlist, with each job's description."""
    return {
        "jobs": {name: spec.description for name, spec in sorted(JOBS.items())},
        "note": "POST /admin/maintenance/run with {job, args}. Poll "
                "GET /admin/maintenance/runs/{run_id}.",
    }


# DECOMMISSIONED 2026-07-29. The enqueue path worked; nothing ever CONSUMED the
# queue. Two rescore_all jobs sat at status='queued' with started_at NULL for two
# days, ops_cron_heartbeat was empty, and the `worker: dramatiq app.worker` process
# type in backend/Procfile was evidently never provisioned as its own Railway
# service. So POST /run wrote a row, called .send(), returned 202 with a run_id --
# and the work vanished. A queue that accepts jobs and silently drops them is worse
# than no queue: the 202 reads as success, and the 409 "one heavy job at a time"
# guard then blocked every LATER job behind a zombie that would never finish.
#
# Refuses work instead of swallowing it. The machinery is left intact -- allowlist,
# argv coercion, auth perimeter, execute_run -- so provisioning a worker and setting
# MAINTENANCE_RUNNER_ENABLED=1 is all it takes to turn back on. Until then heavy
# jobs run locally on the proven path.
#
# GET endpoints stay open: listing jobs and inspecting/abandoning past runs is how
# the zombies were found and cleared.
def _runner_enabled() -> bool:
    return os.getenv("MAINTENANCE_RUNNER_ENABLED", "").strip() in {"1", "true", "TRUE", "yes"}


_DECOMMISSIONED_DETAIL = (
    "maintenance runner decommissioned — no worker provisioned, so a queued job "
    "would never run. Two jobs were silently dropped this way (2026-07-27). Run "
    "heavy jobs locally, or provision the `worker` process from backend/Procfile "
    "as its own Railway service and set MAINTENANCE_RUNNER_ENABLED=1 to re-enable."
)


@router.post("/admin/maintenance/run", status_code=202, response_model=RunJobAccepted)
async def run_job(payload: RunJobRequest) -> RunJobAccepted:
    """Enqueue a job. Returns immediately with a run_id to poll.

    Validation happens HERE (not in the worker) so a bad request is a 400 the
    caller sees, rather than a job row that fails minutes later.
    """
    if not _runner_enabled():
        # 503: the capability is unavailable, not the request malformed.
        raise HTTPException(503, detail=_DECOMMISSIONED_DETAIL)

    try:
        argv = resolve(payload.job, payload.args)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:  # coercion errors from the arg builders
        raise HTTPException(400, detail=f"invalid args: {exc}") from exc

    # Refuse to pile a second heavy job on top of a running one. These jobs are
    # deliberately DB-heavy and serialised: overlapping them is what exhausted
    # the Supabase connection pool and crashloop-ed Railway's boot migrations.
    async with long_running_session_maker() as db:
        busy = (await db.execute(text(
            "SELECT id, job_name FROM ops_job_run "
            " WHERE status IN ('queued','running') ORDER BY id LIMIT 1"
        ))).first()
    if busy is not None:
        raise HTTPException(
            409,
            detail=(f"run {busy[0]} ({busy[1]}) is already {'queued or running'}; "
                    f"heavy jobs are run one at a time. Wait for it or mark it "
                    f"failed via /admin/maintenance/runs/{busy[0]}/abandon."),
        )

    run_id = await create_run(payload.job, payload.args)
    # Imported here so a missing broker at import time can't break the module.
    from app.services.job_queue import run_maintenance_job
    run_maintenance_job.send(run_id, payload.job, payload.args)
    # argv_preview omits the interpreter/script path — it is for confirming the
    # FLAGS were understood, not for reconstructing a command.
    return RunJobAccepted(run_id=run_id, job=payload.job, argv_preview=argv[3:])


@router.get("/admin/maintenance/runs/{run_id}")
async def get_run(run_id: int, tail_lines: int = Query(default=40, ge=1, le=500)) -> dict:
    async with long_running_session_maker() as db:
        row = (await db.execute(text(
            "SELECT id, job_name, args, status, queued_at, started_at, finished_at, "
            "       exit_code, progress, error, log_tail "
            "  FROM ops_job_run WHERE id = :id"
        ), {"id": run_id})).first()
    if row is None:
        raise HTTPException(404, detail="no such run")
    m = row._mapping
    tail = (m["log_tail"] or "").splitlines()
    return {
        **{k: m[k] for k in (
            "id", "job_name", "args", "status", "queued_at", "started_at",
            "finished_at", "exit_code", "progress", "error")},
        "log_tail": tail[-tail_lines:],
    }


@router.get("/admin/maintenance/runs")
async def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    async with long_running_session_maker() as db:
        rows = (await db.execute(text(
            "SELECT id, job_name, status, queued_at, started_at, finished_at, "
            "       exit_code, progress "
            "  FROM ops_job_run ORDER BY id DESC LIMIT :lim"
        ), {"lim": limit})).all()
    return {"runs": [dict(r._mapping) for r in rows]}


@router.post("/admin/maintenance/runs/{run_id}/abandon", status_code=200)
async def abandon_run(run_id: int) -> dict:
    """Mark a run failed so a new one can be enqueued.

    Does NOT kill the process — dramatiq owns that, and a job whose worker died
    (deploy, restart) leaves a row stuck in 'running' with nothing behind it.
    This is the escape hatch for that case; the underlying scripts are all
    resumable, so re-enqueueing after abandoning is safe.
    """
    async with long_running_session_maker() as db:
        res = await db.execute(text(
            "UPDATE ops_job_run SET status='failed', "
            "       error=COALESCE(error,'') || ' [abandoned by operator]', "
            "       finished_at=now() "
            " WHERE id=:id AND status IN ('queued','running')"
        ), {"id": run_id})
        await db.commit()
    if res.rowcount == 0:
        raise HTTPException(409, detail="run is not queued/running")
    return {"run_id": run_id, "status": "failed", "abandoned": True}
