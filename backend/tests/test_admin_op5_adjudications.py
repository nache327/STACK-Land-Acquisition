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


# ────────────────────────────────────────────────────────────────────────────
# 4. jurisdiction_id filter scopes results to a single jurisdiction
# ────────────────────────────────────────────────────────────────────────────
#
# Regression guard for the cross-jurisdiction leak in
# GET /api/admin/op5/adjudications. Before the fix the endpoint accepted
# `jurisdiction_id` in the query string but silently dropped it (no
# WHERE clause), so callers asking for one jurisdiction got rows from
# every jurisdiction in the table. The orchestrator confirmed the leak
# applied to both `status=approved` and `status=pending` (and `rejected`),
# so this test exercises the two most-trafficked status branches against
# a fixture with rows seeded in two distinct jurisdictions.
#
# Seeds:
#   juris A (state=YA)  → 2 pending + 1 approved rows
#   juris B (state=YB)  → 2 pending + 1 approved rows
#
# When the caller passes `jurisdiction_id=<A>`, every returned row's
# `jurisdiction_id` must equal `<A>`. Same assertion for `<B>`. Status
# filter is tested for both `pending` and `approved` to prove the fix
# is in the shared query path, not a status-specific code branch.


@pytest_asyncio.fixture(loop_scope="session")
async def two_jurisdictions(db_session) -> tuple[uuid.UUID, uuid.UUID]:
    """Two throwaway jurisdictions in different sentinel states.

    Uses non-"ZZ" states so this fixture is fully independent of the
    `jurisdiction_id` fixture used by the earlier status tests — no
    risk of cross-contamination if both fixtures end up in the same
    test session.
    """
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO jurisdictions (id, name, state) "
            "VALUES (:id, :name, 'YA')"
        ),
        {"id": a_id, "name": f"test-jur-a-{a_id.hex[:8]}"},
    )
    await db_session.execute(
        text(
            "INSERT INTO jurisdictions (id, name, state) "
            "VALUES (:id, :name, 'YB')"
        ),
        {"id": b_id, "name": f"test-jur-b-{b_id.hex[:8]}"},
    )
    await db_session.flush()
    return a_id, b_id


async def _seed_two_jurisdictions(
    db_session, juris_a: uuid.UUID, juris_b: uuid.UUID
) -> dict[uuid.UUID, dict[str, list[int]]]:
    """Seed each jurisdiction with 2 pending + 1 approved row.

    Returns {juris_id: {"pending": [...], "approved": [...]}} so the
    test can assert on identity per jurisdiction.
    """
    seeds_a_pending = [
        ZoneUseMatrix(
            jurisdiction_id=juris_a,
            zone_code="A-P1",
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
            jurisdiction_id=juris_a,
            zone_code="A-P2",
            municipality=None,
            self_storage="unclear",
            mini_warehouse="unclear",
            light_industrial="unclear",
            luxury_garage_condo="unclear",
            confidence=0.40,
            human_reviewed=False,
            classification_source="llm_low_confidence",
        ),
    ]
    seeds_a_approved = [
        ZoneUseMatrix(
            jurisdiction_id=juris_a,
            zone_code="A-AP1",
            municipality=None,
            self_storage="permitted",
            mini_warehouse="permitted",
            light_industrial="permitted",
            luxury_garage_condo="permitted",
            confidence=0.95,
            human_reviewed=True,
            classification_source="human",
        ),
    ]
    seeds_b_pending = [
        ZoneUseMatrix(
            jurisdiction_id=juris_b,
            zone_code="B-P1",
            municipality=None,
            self_storage="unclear",
            mini_warehouse="unclear",
            light_industrial="unclear",
            luxury_garage_condo="unclear",
            confidence=0.30,
            human_reviewed=False,
            classification_source="llm_low_confidence",
        ),
        ZoneUseMatrix(
            jurisdiction_id=juris_b,
            zone_code="B-P2",
            municipality=None,
            self_storage="unclear",
            mini_warehouse="unclear",
            light_industrial="unclear",
            luxury_garage_condo="unclear",
            confidence=0.45,
            human_reviewed=False,
            classification_source="llm_low_confidence",
        ),
    ]
    seeds_b_approved = [
        ZoneUseMatrix(
            jurisdiction_id=juris_b,
            zone_code="B-AP1",
            municipality=None,
            self_storage="prohibited",
            mini_warehouse="prohibited",
            light_industrial="prohibited",
            luxury_garage_condo="prohibited",
            confidence=0.92,
            human_reviewed=True,
            classification_source="human",
        ),
    ]
    db_session.add_all(
        seeds_a_pending + seeds_a_approved + seeds_b_pending + seeds_b_approved
    )
    await db_session.flush()
    return {
        juris_a: {
            "pending": [s.id for s in seeds_a_pending],
            "approved": [s.id for s in seeds_a_approved],
        },
        juris_b: {
            "pending": [s.id for s in seeds_b_pending],
            "approved": [s.id for s in seeds_b_approved],
        },
    }


async def test_jurisdiction_id_filter_scopes_pending_and_approved(
    client, db_session, two_jurisdictions
):
    """`jurisdiction_id` query param must restrict rows to that jurisdiction.

    Regression for the cross-jurisdiction leak documented in the Lane A
    bug: a request like `?jurisdiction_id=<A>&status=pending` was
    returning rows from every jurisdiction in the table. After the fix,
    every returned row must report `jurisdiction_id == <A>`.

    Exercises both `status=pending` and `status=approved` because the
    orchestrator confirmed both branches leaked — proving the fix lives
    in the shared query path, not a status-specific branch.
    """
    juris_a, juris_b = two_jurisdictions
    by_juris = await _seed_two_jurisdictions(db_session, juris_a, juris_b)

    # ── status=pending, scoped to juris_a ────────────────────────────────
    r = await client.get(
        "/api/admin/op5/adjudications",
        params={
            "status": "pending",
            "jurisdiction_id": str(juris_a),
            "limit": 500,
        },
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    # Every row must belong to juris_a — this is THE bug fix assertion.
    assert all(row["jurisdiction_id"] == str(juris_a) for row in rows), (
        f"expected every row.jurisdiction_id == {juris_a}, got "
        f"{sorted({row['jurisdiction_id'] for row in rows})}"
    )
    # And specifically the pending seeds for juris_a must be present.
    returned_ids = {row["id"] for row in rows}
    for rid in by_juris[juris_a]["pending"]:
        assert rid in returned_ids, f"pending seed {rid} missing from response"
    # None of juris_b's seeds may leak in.
    for rid in (
        by_juris[juris_b]["pending"] + by_juris[juris_b]["approved"]
    ):
        assert rid not in returned_ids, (
            f"juris_b seed {rid} leaked into juris_a query"
        )

    # ── status=approved, scoped to juris_b ───────────────────────────────
    r = await client.get(
        "/api/admin/op5/adjudications",
        params={
            "status": "approved",
            "jurisdiction_id": str(juris_b),
            "limit": 500,
        },
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert all(row["jurisdiction_id"] == str(juris_b) for row in rows), (
        f"expected every row.jurisdiction_id == {juris_b}, got "
        f"{sorted({row['jurisdiction_id'] for row in rows})}"
    )
    returned_ids = {row["id"] for row in rows}
    for rid in by_juris[juris_b]["approved"]:
        assert rid in returned_ids, f"approved seed {rid} missing from response"
    # None of juris_a's seeds may leak in.
    for rid in (
        by_juris[juris_a]["pending"] + by_juris[juris_a]["approved"]
    ):
        assert rid not in returned_ids, (
            f"juris_a seed {rid} leaked into juris_b query"
        )


async def test_jurisdiction_id_omitted_preserves_legacy_behavior(
    client, db_session, two_jurisdictions
):
    """Omitting `jurisdiction_id` keeps the cross-jurisdiction behavior.

    The fix must not silently break callers that intentionally don't
    pass `jurisdiction_id` (e.g. global audit dashboards). With no
    jurisdiction_id but `status=pending`, both juris_a and juris_b's
    pending seeds must still appear.
    """
    juris_a, juris_b = two_jurisdictions
    by_juris = await _seed_two_jurisdictions(db_session, juris_a, juris_b)

    r = await client.get(
        "/api/admin/op5/adjudications",
        params={"status": "pending", "limit": 500},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    returned_ids = {row["id"] for row in rows}

    # Both jurisdictions' pending seeds must show up — proves the fix
    # didn't accidentally add an unconditional WHERE clause.
    for rid in by_juris[juris_a]["pending"]:
        assert rid in returned_ids, (
            f"juris_a pending seed {rid} missing when jurisdiction_id omitted"
        )
    for rid in by_juris[juris_b]["pending"]:
        assert rid in returned_ids, (
            f"juris_b pending seed {rid} missing when jurisdiction_id omitted"
        )
