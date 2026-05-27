from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from app.db import async_session_maker, engine
from app.models.job import Job, JobStatus
from app.models.jurisdiction import Jurisdiction
from app.services.job_tracking import now_utc

DEFAULT_STALE_AFTER_MINUTES = 10


@dataclass(frozen=True)
class StuckQueuedJob:
    id: str
    jurisdiction: str
    queued_at: datetime | None
    age_minutes: int | None


async def find_stuck_queued_jobs(stale_after_minutes: int) -> list[StuckQueuedJob]:
    cutoff = now_utc() - timedelta(minutes=stale_after_minutes)
    age_anchor = func.coalesce(Job.queued_at, Job.created_at)

    async with async_session_maker() as db:
        result = await db.execute(
            select(
                Job.id,
                Job.jurisdiction_input,
                Job.queued_at,
                Job.created_at,
                Jurisdiction.name,
                Jurisdiction.state,
            )
            .outerjoin(Jurisdiction, Job.jurisdiction_id == Jurisdiction.id)
            .where(
                Job.status == JobStatus.queued,
                Job.finished_at.is_(None),
                age_anchor < cutoff,
            )
            .order_by(age_anchor.asc())
        )
        rows = result.all()

    stuck: list[StuckQueuedJob] = []
    checked_at = now_utc()
    for row in rows:
        jurisdiction = _format_jurisdiction(
            jurisdiction_input=row.jurisdiction_input,
            jurisdiction_name=row.name,
            jurisdiction_state=row.state,
        )
        anchor = row.queued_at or row.created_at
        age_minutes = None
        if anchor is not None:
            age_minutes = int((checked_at - anchor).total_seconds() // 60)
        stuck.append(
            StuckQueuedJob(
                id=str(row.id),
                jurisdiction=jurisdiction,
                queued_at=row.queued_at,
                age_minutes=age_minutes,
            )
        )
    return stuck


def _format_jurisdiction(
    *,
    jurisdiction_input: str | None,
    jurisdiction_name: str | None,
    jurisdiction_state: str | None,
) -> str:
    if jurisdiction_name and jurisdiction_state:
        return f"{jurisdiction_name}, {jurisdiction_state}"
    if jurisdiction_name:
        return jurisdiction_name
    if jurisdiction_input:
        return jurisdiction_input
    return "(unknown)"


def print_stuck_jobs(stuck_jobs: list[StuckQueuedJob], stale_after_minutes: int) -> None:
    print(
        f"queued-job watchdog found {len(stuck_jobs)} queued job(s) older than "
        f"{stale_after_minutes} minutes:",
        file=sys.stderr,
    )
    for job in stuck_jobs:
        queued_at = job.queued_at.isoformat() if job.queued_at else "(null)"
        age = f"{job.age_minutes}m" if job.age_minutes is not None else "unknown"
        print(
            f"  job_id={job.id} jurisdiction={job.jurisdiction!r} "
            f"queued_at={queued_at} age={age}",
            file=sys.stderr,
        )


async def run(stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES) -> int:
    try:
        stuck_jobs = await find_stuck_queued_jobs(stale_after_minutes)
    except Exception as exc:
        print(f"queued-job watchdog query failed: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()

    if not stuck_jobs:
        print(
            f"queued-job watchdog OK: no queued jobs older than {stale_after_minutes} minutes",
            file=sys.stderr,
        )
        return 0

    print_stuck_jobs(stuck_jobs, stale_after_minutes)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail when queued jobs are stuck.")
    parser.add_argument(
        "--stale-after-minutes",
        type=int,
        default=DEFAULT_STALE_AFTER_MINUTES,
        help="Queued jobs older than this threshold are reported as stuck.",
    )
    return parser.parse_args()


def _run_digest_tick() -> int:
    """Launch the daily digest as a subprocess and return its exit code.

    Why here: the cron service's config-as-code ``startCommand`` (meant to
    run the digest alongside this watchdog) never took effect on Railway —
    only the watchdog command ran, so the digest went 4 days dark
    (May 23–27) despite eligible deals. The watchdog tick provably fires
    every 10 min, so we launch the digest from it. A fresh subprocess
    avoids event-loop / engine-reuse issues from a second ``asyncio.run``
    in this process, and reuses the exact ``_cli`` entrypoint — which
    self-gates to ``DIGEST_SEND_HOUR_UTC`` (default 12) and is idempotent
    via the 23h ``last_email_sent_at`` cooldown. Its stdout/stderr flow
    into the cron logs so ``digest done: {...}`` / ``digest skip: ...`` is
    visible. Failure here never masks the watchdog's own alert exit code.
    """
    import subprocess

    backend_dir = str(Path(__file__).resolve().parent.parent)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "app.workers.daily_email"],
            cwd=backend_dir,
            timeout=600,
        )
        return proc.returncode
    except Exception as exc:  # noqa: BLE001 — never let the digest sink the tick
        print(f"digest tick failed to launch: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    args = parse_args()
    watchdog_code = asyncio.run(run(args.stale_after_minutes))
    digest_code = _run_digest_tick()
    # Exit-code precedence: a stuck-jobs query failure (2) is the loudest
    # signal and wins. Otherwise surface a digest failure (non-zero), then
    # fall back to the watchdog's own code (0 = clean, 1 = stuck jobs).
    if watchdog_code == 2:
        raise SystemExit(2)
    if digest_code != 0:
        raise SystemExit(digest_code)
    raise SystemExit(watchdog_code)


if __name__ == "__main__":
    main()
