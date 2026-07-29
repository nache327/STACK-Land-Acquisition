"""The maintenance runner must REFUSE work, not silently swallow it.

Nothing ever consumed the dramatiq queue: two rescore_all jobs sat at
status='queued' with started_at NULL for two days while POST /run kept returning
202 with a run_id. A queue that accepts jobs and drops them is worse than no
queue — the 202 reads as success, and the "one heavy job at a time" 409 then
blocks every later job behind a zombie that will never finish.

These tests pin the refusal so the endpoint cannot drift back to accepting work,
and pin that re-enabling is a single env var once a worker exists.

NOTE the conftest bypass: `_bypass_admin_auth` is autouse and disables
require_secret suite-wide. These tests pop it where they assert auth ordering,
following tests/test_admin_auth.py.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api._auth import require_secret
from app.config import settings
from app.main import app

pytestmark = pytest.mark.anyio

_RUN = "/api/admin/maintenance/run"
_BODY = {"job": "rescore_all", "args": {}}


async def _post(body=None, headers=None):
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        return await ac.post(_RUN, json=body or _BODY, **({"headers": headers} if headers else {}))


async def test_enqueue_refused_by_default(monkeypatch):
    """No MAINTENANCE_RUNNER_ENABLED => 503, and NO run_id in the body."""
    monkeypatch.delenv("MAINTENANCE_RUNNER_ENABLED", raising=False)
    r = await _post()
    assert r.status_code == 503, r.text
    assert "decommissioned" in r.json()["detail"].lower()
    assert "run_id" not in r.text


@pytest.mark.parametrize("val", ["", "0", "false", "no", "off", "maybe"])
async def test_only_explicit_optin_enables(monkeypatch, val):
    """Anything that isn't an explicit opt-in keeps the runner off — a typo'd
    value must not quietly re-arm a queue with no consumer."""
    monkeypatch.setenv("MAINTENANCE_RUNNER_ENABLED", val)
    r = await _post()
    assert r.status_code == 503


async def test_refusal_happens_before_any_row_or_send(monkeypatch):
    """The refusal must short-circuit BEFORE a run row is written or a message
    enqueued — otherwise it still leaves zombies behind, just with a 503."""
    called = {"create": False, "send": False}

    async def _spy_create(*a, **k):
        called["create"] = True
        return 1

    def _spy_send(*a, **k):
        called["send"] = True

    from app.api import admin_maintenance
    from app.services import job_queue

    monkeypatch.delenv("MAINTENANCE_RUNNER_ENABLED", raising=False)
    monkeypatch.setattr(admin_maintenance, "create_run", _spy_create)
    monkeypatch.setattr(job_queue.run_maintenance_job, "send", _spy_send)

    r = await _post()
    assert r.status_code == 503
    assert not called["create"], "wrote a run row while decommissioned"
    assert not called["send"], "enqueued a message while decommissioned"


async def test_auth_still_precedes_the_refusal(monkeypatch):
    """A caller with no secret gets 401, not the 503 — the decommission notice
    must not leak operational detail to an unauthenticated caller."""
    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    monkeypatch.delenv("MAINTENANCE_RUNNER_ENABLED", raising=False)
    app.dependency_overrides.pop(require_secret, None)  # undo conftest bypass
    r = await _post()
    assert r.status_code == 401


async def test_read_endpoints_remain_open(monkeypatch):
    """Listing jobs/runs is how the zombies were found and abandoned; killing the
    enqueue path must not blind the operator."""
    monkeypatch.delenv("MAINTENANCE_RUNNER_ENABLED", raising=False)
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        jobs = await ac.get("/api/admin/maintenance/jobs")
    assert jobs.status_code == 200
    assert "rescore_all" in jobs.text


async def test_opt_in_reaches_validation(monkeypatch):
    """With the flag set the endpoint proceeds — proving the switch re-enables
    rather than the code being ripped out. An unknown job must then 400, which
    can only happen if execution got past the decommission gate."""
    monkeypatch.setenv("MAINTENANCE_RUNNER_ENABLED", "1")
    r = await _post({"job": "definitely_not_a_job", "args": {}})
    assert r.status_code == 400
    assert "allowed" in r.json()["detail"]
