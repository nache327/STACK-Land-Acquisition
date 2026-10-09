"""Regression tests for the 2026-10-09 crash-email flood (no DB, no network).

The ops cron runs on Railway as a `restartPolicyType = NEVER` service, where
every tick is a one-shot deployment and ANY nonzero exit is reported as "Deploy
Crashed!" and emailed to the account owner. So the process exit code is a pager,
not a log level.

The old `main()` surfaced informational sub-task codes as the process exit. Two
of them are permanent by construction — a queued job no worker ever claimed
(`recover_stale_jobs` only rescues rows with a non-NULL `locked_at`, so it never
clears) and a muni whose ordinance host 403s. One orphaned job queued
2026-08-10 therefore made every tick exit 1: ~144 crash emails a day for two
months. These tests pin the rule that replaced it: sub-task status goes to
`ops_cron_heartbeat`, and the only nonzero exit is a tick that could not record
itself at all.
"""
from __future__ import annotations

import pytest

from scripts import queued_job_watchdog as qjw


@pytest.fixture
def stub_tick(monkeypatch):
    """Stub every sub-task + the heartbeat; return the captured heartbeat args."""

    def _apply(*, watchdog=0, refresh=0, digest=0, sentinel=0, heartbeat_ok=True):
        captured: dict = {}

        async def fake_run(_stale_after_minutes):
            return watchdog

        def fake_heartbeat(w, r, d, s):
            captured["codes"] = (w, r, d, s)
            return heartbeat_ok

        monkeypatch.setattr(qjw, "run", fake_run)
        monkeypatch.setattr(qjw, "_run_refresh_tick", lambda: refresh)
        monkeypatch.setattr(qjw, "_run_digest_tick", lambda: digest)
        monkeypatch.setattr(qjw, "_run_sentinel_tick", lambda: sentinel)
        monkeypatch.setattr(qjw, "_write_heartbeat", fake_heartbeat)
        monkeypatch.setattr("sys.argv", ["queued_job_watchdog.py"])
        return captured

    return _apply


def _exit_code(func) -> int:
    with pytest.raises(SystemExit) as exc:
        func()
    return exc.value.code


def test_clean_tick_exits_zero(stub_tick) -> None:
    stub_tick()
    assert _exit_code(qjw.main) == 0


def test_stuck_queued_job_does_not_crash_the_tick(stub_tick) -> None:
    """watchdog_code=1 means "a queued job is stale" — the exact state that
    flooded the inbox. It is an alert, recorded in the heartbeat, not a crash."""
    stub_tick(watchdog=1)
    assert _exit_code(qjw.main) == 0


def test_sentinel_fetch_errors_do_not_crash_the_tick(stub_tick) -> None:
    """A town site that 403s is permanent and already persisted to
    `ordinance_fingerprints.fetch_error`."""
    stub_tick(sentinel=1)
    assert _exit_code(qjw.main) == 0


def test_every_subtask_failing_still_exits_zero(stub_tick) -> None:
    """Including watchdog_code=2 (the stuck-jobs query itself failed): if the
    heartbeat landed, the failure is queryable from the DB and needs no email."""
    stub_tick(watchdog=2, refresh=1, digest=1, sentinel=1)
    assert _exit_code(qjw.main) == 0


def test_blind_tick_is_the_only_crash(stub_tick) -> None:
    """No heartbeat row means nothing recorded this tick — the one case where an
    email tells us something the DB cannot."""
    stub_tick(heartbeat_ok=False)
    assert _exit_code(qjw.main) == 1


def test_subtask_codes_reach_the_heartbeat(stub_tick) -> None:
    """Exiting 0 must not mean discarding the codes — they are the alert now."""
    captured = stub_tick(watchdog=1, refresh=2, digest=3, sentinel=4)
    assert _exit_code(qjw.main) == 0
    assert captured["codes"] == (1, 2, 3, 4)
