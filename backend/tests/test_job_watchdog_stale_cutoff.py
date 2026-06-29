"""Regression tests for catch #12 Fix A — the watchdog stale cutoff must exceed
the Dramatiq pipeline actor's 60-min time_limit, so recover_stale_jobs does not
re-enqueue a job that is still legitimately running.

Before the fix STALE_AFTER_SECONDS was 25*60: a job whose locked_at was 30 min
old (well within the 60-min actor budget) was declared stale and re-enqueued from
discover_layers — the Montgomery PA pass-1->pass-2 restart and the Bergen
65min/0-row stall. After the fix it is 70*60.

These tests monkeypatch the watchdog's session maker onto the test engine and stub
enqueue_pipeline_job (so no Redis/broker is touched), seed a single running job,
and assert recover_stale_jobs' decision at each side of the 70-min boundary.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.job import Job, JobStatus
from app.services import job_watchdog
from app.services.job_tracking import now_utc


def test_stale_cutoff_exceeds_actor_time_limit() -> None:
    """The cutoff (70 min) must be > the 60-min Dramatiq actor time_limit."""
    assert job_watchdog.STALE_AFTER_SECONDS == 70 * 60
    assert job_watchdog.STALE_AFTER_SECONDS > 60 * 60


async def _run_watchdog_against(db_engine, monkeypatch, *, minutes_stale: int):
    """Seed one running job locked `minutes_stale` ago, run recover_stale_jobs with
    the default cutoff, and return (job_id, enqueue_calls, refreshed_status). Cleans
    up the seeded row afterward."""
    test_maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(job_watchdog, "async_session_maker", test_maker)
    calls: list = []
    monkeypatch.setattr(job_watchdog, "enqueue_pipeline_job", lambda jid: calls.append(jid))

    async with test_maker() as s:
        job = Job(
            jurisdiction_input=f"WatchdogTest-{minutes_stale}m",
            status=JobStatus.running,
            locked_by="test-host",
            locked_at=now_utc() - timedelta(minutes=minutes_stale),
            attempts=0,
        )
        s.add(job)
        await s.commit()
        jid = job.id
    try:
        await job_watchdog.recover_stale_jobs()
        async with test_maker() as s:
            refreshed = await s.get(Job, jid)
            status = refreshed.status if refreshed else None
        return jid, calls, status
    finally:
        async with test_maker() as s:
            j = await s.get(Job, jid)
            if j is not None:
                await s.delete(j)
                await s.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_job_stale_30min_not_reenqueued(db_engine, monkeypatch) -> None:
    """30 min < 70 min cutoff: the job is still alive and must NOT be re-enqueued
    (this is the exact case the old 25-min cutoff got wrong)."""
    jid, calls, status = await _run_watchdog_against(db_engine, monkeypatch, minutes_stale=30)
    assert jid not in calls
    assert status == JobStatus.running


@pytest.mark.asyncio(loop_scope="session")
async def test_job_stale_75min_reenqueued(db_engine, monkeypatch) -> None:
    """75 min > 70 min cutoff (and past the 60-min actor limit): genuinely dead,
    so it SHOULD be re-enqueued and flipped to retrying."""
    jid, calls, status = await _run_watchdog_against(db_engine, monkeypatch, minutes_stale=75)
    assert jid in calls
    assert status == JobStatus.retrying
