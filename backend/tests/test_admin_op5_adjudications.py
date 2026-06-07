"""Tests for GET /api/admin/op5/adjudications status param.

Covers the status filter introduced by the Allentown unclear-row scoping
work (/tmp/lane_e_recovery_scope.md): the original endpoint only exposed
`pending` or `approved` rows, but the audit script's `matrix_stats` CTE
counts every row in `zone_use_matrix` regardless of `deleted_at`.

`zone_use_matrix` has no separate `status` column — rejection is encoded
as a soft-delete (`deleted_at IS NOT NULL`, with notes prefixed
"REJECTED: ..." by the reject endpoint). So the API's `status` filter
maps to:

    pending  → deleted_at IS NULL AND human_reviewed IS FALSE
    approved → deleted_at IS NULL AND human_reviewed IS TRUE
    rejected → deleted_at IS NOT NULL
    all      → no human_reviewed / deleted_at filter at all
               (matches the audit's CTE — every row in the table)

Strategy mirrors test_admin_op5_matrix.py: drive the FastAPI app via
httpx.ASGITransport and override `get_db` to yield the conftest's
transaction-scoped session. Each test owns its own jurisdiction so
filtering by `state=ZZ` (a sentinel jurisdiction's state) isolates the
seed set from any leftover rows the conftest may carry across tests.
"""
from __future__ import annotations

import datetime as _dt
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.models.zone_use_matrix import ZoneUseMatrix


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session):
    """ASGI client with `get_db` overridden to the test session."""
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


@pytest_asyncio.fixture(loop_scope="session")
async def jurisdiction_id(db_session) -> uuid.UUID:
    """Throwaway jurisdiction owned by this test.

    Uses state="ZZ" so every test can filter by `state=ZZ` and isolate
    its seeded rows from any sibling jurisdiction created elsewhere in
    the same session.
    """
    jid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO jurisdictions (id, name, state) "
            "VALUES (:id, :name, 'ZZ')"
        ),
        {"id": jid, "name": f"test-adjudications-{jid.hex[:8]}"},
    )
    await db_session.flush()
    return jid


async def _seed_status_mix(db_session, jurisdiction_id: uuid.UUID) -> dict[str, list[int]]:
    """Seed 2 pending + 2 approved + 2 rejected rows.

    Returns a dict mapping status label to the seeded row ids so tests
    can assert on identity, not just counts.

    Conventions:
        * pending  → human_reviewed=False, deleted_at=None
        * approved → human_reviewed=True,  deleted_at=None
        * rejected → human_reviewed=any,   deleted_at=now()
          (we set human_reviewed=True for one rejected row to prove the
           `rejected` filter doesn't depend on human_reviewed value)
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    seeds = [
        # 2 pending
        ZoneUseMatrix(
            jurisdiction_id=jurisdiction_id,
            zone_code="P-A",
            municipality=None,
            self_storage="unclear",
            mini_warehouse="unclear",
            light_industrial="unclear",
            luxury_garage_condo="unclear",
            confidence=0.35,
            human_reviewed=False,
            classification_source="llm_low_confidence",
        ),
        ZoneUseMatrix(
            jurisdiction_id=jurisdiction_id,
            zone_code="P-B",
            municipality=None,
            self_storage="unclear",
            mini_warehouse="unclear",
            light_industrial="unclear",
            luxury_garage_condo="unclear",
            confidence=0.40,
            human_reviewed=False,
            classification_source="llm_low_confidence",
        ),
        # 2 approved
        ZoneUseMatrix(
            jurisdiction_id=jurisdiction_id,
            zone_code="A-A",
            municipality=None,
            self_storage="permitted",
            mini_warehouse="permitted",
            light_industrial="permitted",
            luxury_garage_condo="permitted",
            confidence=0.95,
            human_reviewed=True,
            classification_source="human",
        ),
        ZoneUseMatrix(
            jurisdiction_id=jurisdiction_id,
            zone_code="A-B",
            municipality=None,
            self_storage="prohibited",
            mini_warehouse="prohibited",
            light_industrial="prohibited",
            luxury_garage_condo="prohibited",
            confidence=0.92,
            human_reviewed=True,
            classification_source="human",
        ),
        # 2 rejected (soft-deleted). One has human_reviewed=True to
        # prove the rejected filter uses deleted_at only, not the
        # human_reviewed flag.
        ZoneUseMatrix(
            jurisdiction_id=jurisdiction_id,
            zone_code="R-A",
            municipality=None,
            self_storage="prohibited",
            mini_warehouse="prohibited",
            light_industrial="prohibited",
            luxury_garage_condo="prohibited",
            confidence=0.50,
            human_reviewed=False,
            classification_source="llm",
            notes="REJECTED: bogus zone code",
            deleted_at=now,
        ),
        ZoneUseMatrix(
            jurisdiction_id=jurisdiction_id,
            zone_code="R-B",
            municipality=None,
            self_storage="prohibited",
            mini_warehouse="prohibited",
            light_industrial="prohibited",
            luxury_garage_condo="prohibited",
            confidence=0.55,
            human_reviewed=True,
            classification_source="human",
            notes="REJECTED: superseded by per-muni row",
            deleted_at=now,
        ),
    ]
    db_session.add_all(seeds)
    await db_session.flush()

    return {
        "pending": [seeds[0].id, seeds[1].id],
        "approved": [seeds[2].id, seeds[3].id],
        "rejected": [seeds[4].id, seeds[5].id],
    }


# ────────────────────────────────────────────────────────────────────────────
# 1. status=rejected returns only rejected rows
# ────────────────────────────────────────────────────────────────────────────


async def test_status_rejected_returns_rejected_rows(
    client, db_session, jurisdiction_id
):
    """status=rejected returns exactly the 2 soft-deleted rows."""
    by_status = await _seed_status_mix(db_session, jurisdiction_id)

    r = await client.get(
        "/api/admin/op5/adjudications",
        params={"status": "rejected", "state": "ZZ", "limit": 100},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    returned_ids = {row["id"] for row in rows}

    assert returned_ids == set(by_status["rejected"]), (
        f"expected only rejected ids {by_status['rejected']}, "
        f"got {sorted(returned_ids)}"
    )
    # Every returned row reports status="rejected" on the response.
    assert all(row["status"] == "rejected" for row in rows)
    # And none of them are pending or approved ids.
    assert not (returned_ids & set(by_status["pending"]))
    assert not (returned_ids & set(by_status["approved"]))


# ────────────────────────────────────────────────────────────────────────────
# 2. status=all returns all non-deleted-filtered rows
# ────────────────────────────────────────────────────────────────────────────


async def test_status_all_returns_all_rows(
    client, db_session, jurisdiction_id
):
    """status=all returns all 6 seeded rows (2 pending + 2 approved + 2 rejected).

    This is the mode that mirrors `audit_zoning_coverage.py`'s
    `matrix_stats` CTE — no `deleted_at` or `human_reviewed` filter.
    """
    by_status = await _seed_status_mix(db_session, jurisdiction_id)

    r = await client.get(
        "/api/admin/op5/adjudications",
        params={"status": "all", "state": "ZZ", "limit": 100},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    returned_ids = {row["id"] for row in rows}

    expected = set(by_status["pending"]) | set(by_status["approved"]) | set(
        by_status["rejected"]
    )
    assert returned_ids == expected, (
        f"expected all 6 seed ids {sorted(expected)}, got {sorted(returned_ids)}"
    )
    assert len(rows) == 6

    # Confirm each row reports a status that matches its actual bucket.
    status_by_id = {row["id"]: row["status"] for row in rows}
    for rid in by_status["pending"]:
        assert status_by_id[rid] == "pending"
    for rid in by_status["approved"]:
        assert status_by_id[rid] == "approved"
    for rid in by_status["rejected"]:
        assert status_by_id[rid] == "rejected"


# ────────────────────────────────────────────────────────────────────────────
# 3. default status (no param) still returns pending — no regression
# ────────────────────────────────────────────────────────────────────────────


async def test_status_default_unchanged(
    client, db_session, jurisdiction_id
):
    """Omitting the status param keeps the historical behavior.

    The endpoint used to default to status=pending and exclude
    tombstoned rows; this test guards that contract so existing
    callers don't break.
    """
    by_status = await _seed_status_mix(db_session, jurisdiction_id)

    r = await client.get(
        "/api/admin/op5/adjudications",
        params={"state": "ZZ", "limit": 100},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    returned_ids = {row["id"] for row in rows}

    assert returned_ids == set(by_status["pending"]), (
        f"default must equal status=pending; "
        f"expected {by_status['pending']}, got {sorted(returned_ids)}"
    )
    # Nothing rejected or approved leaked in.
    assert not (returned_ids & set(by_status["rejected"]))
    assert not (returned_ids & set(by_status["approved"]))
    assert all(row["status"] == "pending" for row in rows)
