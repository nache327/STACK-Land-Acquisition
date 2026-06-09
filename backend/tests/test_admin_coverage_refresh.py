"""Tests for POST /api/admin/coverage/refresh response semantics.

Before 2026-06-08 the endpoint always returned HTTP 200, even when the
audit SQL silently failed inside `coverage_audit._refresh_all_snapshots_inner`'s
try/except and the response body was `{"snapshots_written": 0,
"snapshots_failed": 1, "summary": {"error": "..."}}`. Operators reading
HTTP status (or running tooling that only checks 2xx) interpreted the
silent-failure case as success — Hunterdon fired 4 refreshes over 24h
with `captured_at` stuck because every call returned 200.

These tests pin the new contract:

  written > 0                              → 200 (full / partial success)
  written == 0 AND failed > 0              → 502 (all-fail)
  written == 0 AND failed == 0             → 200 (no jurisdictions matched
                                                  — e.g. empty DB; not a
                                                  failure to report up)

The audit itself is monkeypatched so the test runs in milliseconds and
doesn't depend on having ingested data; the production silent-failure
mode is reproduced by patching `refresh_all_snapshots` directly.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.main import app


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session):
    """ASGI client with get_db overridden to the test session."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)


def _patch_refresh(monkeypatch, payload: dict) -> None:
    """Replace coverage_audit.refresh_all_snapshots with a stub returning
    the supplied payload. Reaches into the module the endpoint imports
    from at request time, not the symbol in jurisdictions.py — the
    endpoint does `from app.services.coverage_audit import …` inside the
    handler, so the patch target is the source module."""
    async def _fake_refresh(db, jurisdiction_id=None, source="manual"):
        return payload

    import app.services.coverage_audit as coverage_audit_mod
    monkeypatch.setattr(
        coverage_audit_mod, "refresh_all_snapshots", _fake_refresh
    )


# ─── all-fail case — the bug we shipped to fix ───────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_returns_502_when_every_snapshot_failed(client, monkeypatch):
    """The silent-failure case: 0 written, ≥1 failed. Must surface as
    502 so operator tooling stops mistaking it for success."""
    _patch_refresh(monkeypatch, {
        "snapshots_written": 0,
        "snapshots_failed": 1,
        "summary": {"error": "audit failed: QueryCanceledError: …"},
    })

    resp = await client.post("/api/admin/coverage/refresh")

    assert resp.status_code == 502
    body = resp.json()
    # FastAPI nests HTTPException(detail=…) under "detail"
    assert body["detail"]["error"] == "coverage refresh failed; no snapshots written"
    # The original audit result is preserved inside detail so operators
    # can still read the underlying error without re-running the call.
    assert body["detail"]["result"]["snapshots_written"] == 0
    assert body["detail"]["result"]["snapshots_failed"] == 1


# ─── partial-success — must stay 200 so multi-jurisdiction sweeps don't bail ─


@pytest.mark.asyncio(loop_scope="session")
async def test_returns_200_on_partial_success(client, monkeypatch):
    """A full-sweep refresh might write some jurisdictions and fail
    others (e.g. one big county times out while smaller ones succeed).
    Keep partial-success as 200 — the body's `snapshots_failed > 0`
    field is the degradation signal."""
    _patch_refresh(monkeypatch, {
        "snapshots_written": 12,
        "snapshots_failed": 1,
        "summary": {"jurisdiction_count": 13, "operational_count": 7},
    })

    resp = await client.post("/api/admin/coverage/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["snapshots_written"] == 12
    assert body["snapshots_failed"] == 1


# ─── full success — unchanged ────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_returns_200_on_full_success(client, monkeypatch):
    _patch_refresh(monkeypatch, {
        "snapshots_written": 75,
        "snapshots_failed": 0,
        "summary": {"jurisdiction_count": 75, "operational_count": 16},
    })

    resp = await client.post("/api/admin/coverage/refresh")

    assert resp.status_code == 200
    assert resp.json()["snapshots_written"] == 75


# ─── zero/zero — empty DB or no-op refresh; not a failure to report up ───────


@pytest.mark.asyncio(loop_scope="session")
async def test_returns_200_when_no_jurisdictions_matched(client, monkeypatch):
    """Edge case: refresh runs but the audit returns an empty audit
    list (no jurisdictions in the DB, or a `jurisdiction_id` filter
    that matched zero rows). 0/0 is not a failure — keep 200 and
    let the caller decide from the body."""
    _patch_refresh(monkeypatch, {
        "snapshots_written": 0,
        "snapshots_failed": 0,
        "summary": {"jurisdiction_count": 0},
    })

    resp = await client.post("/api/admin/coverage/refresh")

    assert resp.status_code == 200
    assert resp.json()["snapshots_written"] == 0
    assert resp.json()["snapshots_failed"] == 0


# ─── jurisdiction_id scope — same contract ───────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_scoped_refresh_502s_on_silent_failure(client, monkeypatch):
    """Hunterdon-shaped case: scoped refresh for one jurisdiction whose
    audit SQL times out. Same 502 contract as the all-fail case."""
    _patch_refresh(monkeypatch, {
        "snapshots_written": 0,
        "snapshots_failed": 1,
        "summary": {"error": "audit failed: QueryCanceledError: …"},
    })

    import uuid as _uuid
    fake_jid = _uuid.uuid4()
    resp = await client.post(
        f"/api/admin/coverage/refresh?jurisdiction_id={fake_jid}&source=diag"
    )

    assert resp.status_code == 502
    assert (
        resp.json()["detail"]["error"]
        == "coverage refresh failed; no snapshots written"
    )
