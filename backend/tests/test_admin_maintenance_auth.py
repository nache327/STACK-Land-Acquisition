"""The maintenance runner's PERIMETER: every route requires the admin secret.

The allowlist / coerced params / inert-argv work in
test_maintenance_jobs_allowlist.py is defense-in-depth INSIDE the perimeter. This
file pins the perimeter itself — no /admin/maintenance/* route is reachable
without X-Admin-Secret, and auth is enforced BEFORE any job row is written or any
subprocess spawned.

NOTE the conftest bypass: `_bypass_admin_auth` is autouse and disables
require_secret suite-wide (every test env has ADMIN_API_SECRET unset, so gated
routes would otherwise 503 instead of testing their behavior). These tests pop it,
following the convention established in tests/test_admin_auth.py — without that
pop this file would assert nothing, which is exactly the trap it exists to avoid.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.api._auth import require_secret
from app.config import settings
from app.main import app

pytestmark = pytest.mark.anyio

# Every route the maintenance router exposes, with a safe method/body.
ROUTES = [
    ("get", "/api/admin/maintenance/jobs", None),
    ("get", "/api/admin/maintenance/runs", None),
    ("get", "/api/admin/maintenance/runs/1", None),
    ("post", "/api/admin/maintenance/run", {"job": "rescore_all", "args": {}}),
    ("post", "/api/admin/maintenance/runs/1/abandon", None),
]


async def _request(ac, method, path, body, headers=None):
    kwargs = {"headers": headers} if headers else {}
    if body is not None:
        kwargs["json"] = body
    return await getattr(ac, method)(path, **kwargs)


@pytest.mark.parametrize("method,path,body", ROUTES)
async def test_no_secret_is_rejected(monkeypatch, method, path, body):
    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    app.dependency_overrides.pop(require_secret, None)  # undo conftest bypass
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        r = await _request(ac, method, path, body)
    assert r.status_code == 401, (
        f"{method.upper()} {path} returned {r.status_code} with no secret"
    )


@pytest.mark.parametrize("method,path,body", ROUTES)
async def test_wrong_secret_is_rejected(monkeypatch, method, path, body):
    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    app.dependency_overrides.pop(require_secret, None)
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        r = await _request(ac, method, path, body,
                           headers={"X-Admin-Secret": "wrong"})
    assert r.status_code == 401


@pytest.mark.parametrize("method,path,body", ROUTES)
async def test_unset_secret_fails_closed(monkeypatch, method, path, body):
    """No ADMIN_API_SECRET configured must 503, never fall open."""
    monkeypatch.setattr(settings, "admin_api_secret", None)
    app.dependency_overrides.pop(require_secret, None)
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        r = await _request(ac, method, path, body,
                           headers={"X-Admin-Secret": "anything"})
    assert r.status_code == 503


async def test_correct_secret_clears_auth(monkeypatch):
    """Sanity that the gate is auth and not a blanket block: with the right
    header the request gets PAST auth (it may then fail on the test DB, but the
    status must not be an auth status)."""
    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    app.dependency_overrides.pop(require_secret, None)
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        r = await ac.get("/api/admin/maintenance/jobs",
                         headers={"X-Admin-Secret": "s3cret"})
    assert r.status_code not in (401, 503)


async def test_unauthenticated_post_never_reaches_the_handler(monkeypatch):
    """Auth must short-circuit before a run row is created or a job enqueued.
    Patch both so a leak would be loudly visible rather than inferred."""
    called = {"create": False, "send": False}

    async def _spy_create(*a, **k):
        called["create"] = True
        return 1

    def _spy_send(*a, **k):
        called["send"] = True

    from app.api import admin_maintenance
    from app.services import job_queue

    monkeypatch.setattr(admin_maintenance, "create_run", _spy_create)
    monkeypatch.setattr(job_queue.run_maintenance_job, "send", _spy_send)
    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    app.dependency_overrides.pop(require_secret, None)

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        r = await ac.post("/api/admin/maintenance/run",
                          json={"job": "rescore_all", "args": {}})
    assert r.status_code == 401
    assert not called["create"], "created a run row without auth"
    assert not called["send"], "enqueued a job without auth"


def test_every_maintenance_route_is_covered_here():
    """If a route is added to the router, this fails until it is added above —
    so the perimeter check cannot silently fall behind the surface. Compares
    against FastAPI's templated paths (…/runs/{run_id}), mapping the concrete
    paths used in ROUTES onto them."""
    live = {
        (m.lower(), r.path)
        for r in app.routes
        if "admin/maintenance" in getattr(r, "path", "")
        for m in (getattr(r, "methods", set()) or set())
        if m.lower() in {"get", "post", "put", "patch", "delete"}
    }
    covered = {
        (m, p.replace("/runs/1/abandon", "/runs/{run_id}/abandon")
             .replace("/runs/1", "/runs/{run_id}"))
        for m, p, _ in ROUTES
    }
    assert live == covered, (
        f"uncovered: {live - covered}; stale entries: {covered - live}"
    )
