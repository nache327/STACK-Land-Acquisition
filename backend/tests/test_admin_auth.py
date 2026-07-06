"""
Pins the shared-secret admin-auth contract (app/api/_auth.require_secret):

  ADMIN_API_SECRET unset              → 503 (fail-closed, never silently open)
  set, header missing or wrong        → 401
  set, correct X-Admin-Secret header  → passes

Unit-level against the dependency itself (no DB), plus one end-to-end check
that a gated route actually enforces it — with the suite-wide bypass fixture
(conftest._bypass_admin_auth) popped for that test.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.api._auth import require_secret
from app.config import settings


async def test_unset_secret_fails_closed_503(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_secret", "")
    with pytest.raises(HTTPException) as exc:
        await require_secret(x_admin_secret="anything")
    assert exc.value.status_code == 503


async def test_missing_header_401(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    with pytest.raises(HTTPException) as exc:
        await require_secret(x_admin_secret=None)
    assert exc.value.status_code == 401


async def test_wrong_header_401(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    with pytest.raises(HTTPException) as exc:
        await require_secret(x_admin_secret="wrong")
    assert exc.value.status_code == 401


async def test_correct_header_passes(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    assert await require_secret(x_admin_secret="s3cret") is None


async def test_gated_route_enforces_end_to_end(monkeypatch):
    """With the suite bypass popped, a gated route 401s without the header and
    is let through with it (503 would mean the dependency isn't wired)."""
    from app.main import app

    monkeypatch.setattr(settings, "admin_api_secret", "s3cret")
    app.dependency_overrides.pop(require_secret, None)  # undo conftest bypass
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        denied = await ac.get("/api/debug/alembic-status")
        assert denied.status_code == 401
        # Correct header clears auth; the route may then fail on the missing
        # test DB, but it must NOT be an auth status.
        allowed = await ac.get(
            "/api/debug/alembic-status", headers={"X-Admin-Secret": "s3cret"}
        )
        assert allowed.status_code not in (401, 503)
