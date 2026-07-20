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


def _run_refresh_tick() -> int:
    """Once/day, BEFORE the digest: fresh-score the LGC email lane's listed parcels
    and refresh the needle snapshot, so ``/needles`` and the LGC Hot deals email
    reflect CURRENT listings + grounding. A copied/stale score silently drifts as
    new CoStar listings land (a real bug we hit — a newly-listed parcel was missing
    its +15 listing boost), so this always re-scores through the canonical scorer.

    Piggybacks the watchdog tick (like the digest) because the config-as-code cron
    never took effect on Railway. Gated to ``DIGEST_SEND_HOUR_UTC`` + a 23h
    staleness check on needle_snapshot so it runs once/day, and single-flighted
    with a pg advisory lock so overlapping 10-min ticks never double-run the heavy
    (~7 min) work. Failure never sinks the tick."""
    import os

    try:
        send_hour = int(os.getenv("DIGEST_SEND_HOUR_UTC", "12"))
        if not 0 <= send_hour <= 23:
            send_hour = 12
    except (TypeError, ValueError):
        send_hour = 12
    from datetime import timezone

    if datetime.now(timezone.utc).hour != send_hour:
        return 0
    try:
        return asyncio.run(_refresh_locked())
    except Exception as exc:  # noqa: BLE001 — never let refresh sink the tick
        print(f"refresh tick failed: {exc}", file=sys.stderr)
        return 1


async def _refresh_locked() -> int:
    import subprocess
    from datetime import timezone

    import asyncpg

    from app.config import settings

    # Session-mode (5432) DSN so the advisory lock actually holds (the 6543
    # transaction pooler resets locks between statements).
    dsn = (
        settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        .replace(":6543/", ":5432/")
    )
    conn = await asyncpg.connect(dsn)
    try:
        if not await conn.fetchval(
            "SELECT pg_try_advisory_lock(hashtextextended('nightly_refresh', 42))"
        ):
            return 0  # another tick is already refreshing
        ts = await conn.fetchval("SELECT max(computed_at) FROM needle_snapshot")
        if ts is not None and (datetime.now(timezone.utc) - ts) < timedelta(hours=23):
            return 0  # already refreshed today
        scripts_dir = Path(__file__).resolve().parent
        backend_dir = scripts_dir.parent
        code = 0
        # LGC listed-scores FIRST (so they're fresh before the digest selects
        # them); then the needle snapshot, whose computed_at drives the gate above.
        for script in ("refresh_lgc_hotdeals_scores.py", "precompute_needles.py"):
            try:
                proc = subprocess.run(
                    [sys.executable, str(scripts_dir / script)],
                    cwd=str(backend_dir), timeout=1800,
                )
                if proc.returncode != 0:
                    print(f"refresh: {script} exited {proc.returncode}", file=sys.stderr)
                    code = 1
            except Exception as exc:  # noqa: BLE001
                print(f"refresh: {script} failed to launch: {exc}", file=sys.stderr)
                code = 1
        return code
    finally:
        await conn.close()  # releases the advisory lock


def _write_heartbeat(watchdog_code: int, refresh_code: int, digest_code: int) -> None:
    """Record one row per tick so cron liveness is observable from the DB.

    The ops cron rides restartPolicyType=NEVER one-shots with no external
    health signal, so "is the cron firing?" (and "did it fire at 12:00 UTC?")
    was only answerable from Railway logs. This heartbeat is UNCONDITIONAL —
    independent of the hour gate, email flags, and the dashboard DSN — so a
    missing heartbeat means the cron itself did not run, full stop. Best-effort:
    a heartbeat failure never sinks the tick (and if the table doesn't exist yet
    because the web service hasn't migrated, the INSERT just no-ops via except)."""
    try:
        asyncio.run(_write_heartbeat_async(watchdog_code, refresh_code, digest_code))
    except Exception as exc:  # noqa: BLE001 — never let the heartbeat sink the tick
        print(f"heartbeat write failed: {exc}", file=sys.stderr)


async def _write_heartbeat_async(
    watchdog_code: int, refresh_code: int, digest_code: int
) -> None:
    import os
    import socket

    import asyncpg

    from app.config import settings

    dsn = (
        settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        .replace(":6543/", ":5432/")
    )
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "INSERT INTO ops_cron_heartbeat "
            "(watchdog_code, refresh_code, digest_code, host) VALUES ($1, $2, $3, $4)",
            watchdog_code,
            refresh_code,
            digest_code,
            os.getenv("RAILWAY_SERVICE_NAME") or socket.gethostname(),
        )
    finally:
        await conn.close()


def main() -> None:
    args = parse_args()
    watchdog_code = asyncio.run(run(args.stale_after_minutes))
    refresh_code = _run_refresh_tick()  # before the digest, so its scores are fresh
    digest_code = _run_digest_tick()
    _write_heartbeat(watchdog_code, refresh_code, digest_code)  # cron-liveness trace
    # Exit-code precedence: a stuck-jobs query failure (2) is the loudest
    # signal and wins. Otherwise surface a digest failure, then a refresh
    # failure, then fall back to the watchdog's own code (0 = clean, 1 = stuck).
    if watchdog_code == 2:
        raise SystemExit(2)
    if digest_code != 0:
        raise SystemExit(digest_code)
    if refresh_code != 0:
        raise SystemExit(refresh_code)
    raise SystemExit(watchdog_code)


if __name__ == "__main__":
    main()
