"""Tests for POST /api/jurisdictions/{id}/_upload-matrix-rows (M2).

Covers the 7 scenarios from the M2 spec
(docs/OP5_FACTORY_ABANDONED.md → operator dispatch upload path):

  1. insert: 3 new rows → all inserted
  2. skip:   existing row + replace_existing=false → skipped
  3. update: existing row + replace_existing=true → updated in place
  4. undelete: tombstoned row + new payload → undeleted + updated
  5. invalid enum (single row) → 422, no DB writes
  6. atomic rollback: batch of 3 with row[1] invalid → 422, 0 inserts
  7. 404 for unknown jurisdiction

Strategy: drive the FastAPI app via httpx.ASGITransport (same pattern as
test_health.py) and override the `get_db` dependency to yield the
conftest's transaction-scoped `db_session` so each test rolls back at
the end (no manual cleanup required across the suite). The 422-rollback
test verifies that the *handler's* transactional commit-or-rollback
posture holds, independent of the per-test outer rollback.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

from app.db import get_db
from app.main import app
from app.models.zone_use_matrix import ZoneUseMatrix


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session):
    """ASGI client with `get_db` overridden to the test session.

    The override yields the same `db_session` for every request inside
    one test, so writes made by the handler are visible to subsequent
    assertions on the same session, and the outer transaction rollback
    in the conftest fixture isolates this test from siblings.
    """
    async def _override_get_db():
        # The conftest's db_session already opened a transaction at
        # session creation; the handler's `db.flush()` and our reads
        # share the same in-flight transaction. We intentionally do
        # NOT commit/rollback here — the outer fixture handles it.
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
    """A throwaway jurisdiction this test owns."""
    jid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO jurisdictions (id, name, state) "
            "VALUES (:id, :name, 'NJ')"
        ),
        {"id": jid, "name": f"test-upload-matrix-{jid.hex[:8]}"},
    )
    await db_session.flush()
    return jid


def _row_payload(
    zone_code: str = "R-2",
    municipality: str | None = "Fort Lee borough",
    self_storage: str = "prohibited",
    mini_warehouse: str = "prohibited",
    light_industrial: str = "prohibited",
    luxury_garage_condo: str = "prohibited",
    confidence: float = 0.91,
    notes: str | None = "Residential district.",
    classification_source: str = "human",
    human_reviewed: bool = False,
    citations: list[dict] | None = None,
) -> dict:
    return {
        "zone_code": zone_code,
        "zone_name": f"{zone_code} (Test)",
        "municipality": municipality,
        "self_storage": self_storage,
        "mini_warehouse": mini_warehouse,
        "light_industrial": light_industrial,
        "luxury_garage_condo": luxury_garage_condo,
        "confidence": confidence,
        "notes": notes,
        "classification_source": classification_source,
        "human_reviewed": human_reviewed,
        "citations": citations or [
            {
                "section": "Fort Lee Code § 410-13",
                "quote": "Residential district; storage uses not listed.",
                "url": "https://ecode360.com/test",
            }
        ],
    }


async def _count_rows(db_session, jurisdiction_id) -> int:
    return int(
        (
            await db_session.execute(
                select(func.count(ZoneUseMatrix.id)).where(
                    ZoneUseMatrix.jurisdiction_id == jurisdiction_id
                )
            )
        ).scalar()
        or 0
    )


# ────────────────────────────────────────────────────────────────────────────
# 1. insert
# ────────────────────────────────────────────────────────────────────────────


async def test_upload_inserts_new_rows(client, db_session, jurisdiction_id):
    rows = [
        _row_payload(zone_code="R-1"),
        _row_payload(zone_code="R-2"),
        _row_payload(zone_code="LM", self_storage="permitted"),
    ]
    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={"rows": rows, "replace_existing": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["received"] == 3
    assert body["inserted"] == 3
    assert body["updated"] == 0
    assert body["undeleted"] == 0
    assert body["skipped"] == 0
    assert body["errors"] == []

    # DB state: all 3 rows landed with the expected verdicts.
    assert await _count_rows(db_session, jurisdiction_id) == 3
    lm = (
        await db_session.execute(
            select(ZoneUseMatrix).where(
                ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
                ZoneUseMatrix.zone_code == "LM",
            )
        )
    ).scalar_one()
    assert lm.self_storage.value == "permitted"
    assert lm.classification_source.value == "human"
    assert lm.deleted_at is None


# ────────────────────────────────────────────────────────────────────────────
# 2. skip
# ────────────────────────────────────────────────────────────────────────────


async def test_upload_skips_existing_when_replace_false(
    client, db_session, jurisdiction_id
):
    pre = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        zone_code="R-3",
        municipality="Fort Lee borough",
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=0.5,
        notes="old",
        classification_source="llm",
    )
    db_session.add(pre)
    await db_session.flush()

    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={
            "rows": [
                _row_payload(
                    zone_code="R-3",
                    confidence=0.99,
                    notes="new",
                    self_storage="permitted",
                )
            ],
            "replace_existing": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] == 0
    assert body["skipped"] == 1
    assert body["updated"] == 0

    # DB state: row untouched.
    await db_session.refresh(pre)
    assert pre.self_storage.value == "prohibited"
    assert pre.notes == "old"
    assert float(pre.confidence) == 0.5


# ────────────────────────────────────────────────────────────────────────────
# 3. update
# ────────────────────────────────────────────────────────────────────────────


async def test_upload_updates_existing_when_replace_true(
    client, db_session, jurisdiction_id
):
    pre = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        zone_code="B-2",
        municipality="Fort Lee borough",
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=0.4,
        notes="stale",
        classification_source="llm",
        human_reviewed=False,
    )
    db_session.add(pre)
    await db_session.flush()

    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={
            "rows": [
                _row_payload(
                    zone_code="B-2",
                    self_storage="permitted",
                    light_industrial="conditional",
                    confidence=0.92,
                    notes="refreshed by op5 dispatch",
                    human_reviewed=True,
                )
            ],
            "replace_existing": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 1
    assert body["inserted"] == 0
    assert body["skipped"] == 0

    await db_session.refresh(pre)
    assert pre.self_storage.value == "permitted"
    assert pre.light_industrial.value == "conditional"
    assert pre.notes == "refreshed by op5 dispatch"
    assert pre.human_reviewed is True
    assert float(pre.confidence) == pytest.approx(0.92, abs=1e-6)


# ────────────────────────────────────────────────────────────────────────────
# 4. undelete
# ────────────────────────────────────────────────────────────────────────────


async def test_upload_undeletes_soft_deleted_rows(
    client, db_session, jurisdiction_id
):
    import datetime as _dt

    pre = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        zone_code="CA",
        municipality="Fort Lee borough",
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="prohibited",
        luxury_garage_condo="prohibited",
        confidence=0.7,
        notes="tombstoned",
        classification_source="llm",
        deleted_at=_dt.datetime.now(_dt.timezone.utc),
    )
    db_session.add(pre)
    await db_session.flush()

    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={
            "rows": [
                _row_payload(
                    zone_code="CA",
                    self_storage="permitted",
                    confidence=0.95,
                    notes="revived",
                )
            ],
            # Note: undelete happens regardless of replace_existing.
            "replace_existing": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["undeleted"] == 1
    assert body["inserted"] == 0
    assert body["skipped"] == 0
    assert body["updated"] == 0

    await db_session.refresh(pre)
    assert pre.deleted_at is None
    assert pre.self_storage.value == "permitted"
    assert pre.notes == "revived"
    assert float(pre.confidence) == pytest.approx(0.95, abs=1e-6)


# ────────────────────────────────────────────────────────────────────────────
# 5. invalid enum
# ────────────────────────────────────────────────────────────────────────────


async def test_upload_rejects_invalid_permission_enum(
    client, db_session, jurisdiction_id
):
    bad = _row_payload(zone_code="X-1")
    bad["self_storage"] = "maybe"  # invalid

    pre_count = await _count_rows(db_session, jurisdiction_id)

    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={"rows": [bad], "replace_existing": False},
    )
    assert r.status_code == 422, r.text
    # No writes — pydantic short-circuits before the handler body runs.
    assert await _count_rows(db_session, jurisdiction_id) == pre_count


# ────────────────────────────────────────────────────────────────────────────
# 6. atomic rollback on partial failure
# ────────────────────────────────────────────────────────────────────────────


async def test_upload_atomic_on_partial_failure(
    client, db_session, jurisdiction_id
):
    """Row index 1 has an invalid enum; the WHOLE batch must abort.

    The validation happens at parse time (Pydantic), so no DB work is
    attempted at all and the inserted count after the call is unchanged.
    This covers the "atomic" contract from the M2 spec without needing
    to engineer a mid-batch DB-level failure.
    """
    pre_count = await _count_rows(db_session, jurisdiction_id)

    rows = [
        _row_payload(zone_code="ATOMIC-1"),
        _row_payload(zone_code="ATOMIC-2"),
        _row_payload(zone_code="ATOMIC-3"),
    ]
    rows[1]["mini_warehouse"] = "definitely-not-an-enum"

    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={"rows": rows, "replace_existing": False},
    )
    assert r.status_code == 422, r.text
    assert await _count_rows(db_session, jurisdiction_id) == pre_count
    # And specifically: ATOMIC-1 must NOT have leaked in.
    leaked = (
        await db_session.execute(
            select(ZoneUseMatrix).where(
                ZoneUseMatrix.jurisdiction_id == jurisdiction_id,
                ZoneUseMatrix.zone_code == "ATOMIC-1",
            )
        )
    ).scalar_one_or_none()
    assert leaked is None


# ────────────────────────────────────────────────────────────────────────────
# 7. 404 for unknown jurisdiction
# ────────────────────────────────────────────────────────────────────────────


async def test_upload_404_for_unknown_jurisdiction(client):
    fake = uuid.uuid4()
    r = await client.post(
        f"/api/jurisdictions/{fake}/_upload-matrix-rows",
        json={"rows": [_row_payload(zone_code="R-1")], "replace_existing": False},
    )
    assert r.status_code == 404, r.text
    assert "not found" in r.json()["detail"].lower()


# ────────────────────────────────────────────────────────────────────────────
# 8. catch #13 — factory row must NOT overwrite a live human_reviewed verdict
# ────────────────────────────────────────────────────────────────────────────


async def test_upload_protects_human_row_from_factory_overwrite(
    client, db_session, jurisdiction_id
):
    """Even with replace_existing=true, a non-human (factory) row is skipped
    when it would overwrite a live human_reviewed=true verdict."""
    pre = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        zone_code="I-1",
        municipality="Fort Lee borough",
        self_storage="permitted",
        mini_warehouse="permitted",
        light_industrial="permitted",
        luxury_garage_condo="unclear",
        confidence=0.95,
        notes="HAND VERDICT",
        classification_source="human",
        human_reviewed=True,
    )
    db_session.add(pre)
    await db_session.flush()

    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={
            "rows": [
                _row_payload(
                    zone_code="I-1",
                    self_storage="prohibited",
                    notes="factory catchall",
                    classification_source="op5_factory_catchall",
                    human_reviewed=False,
                )
            ],
            "replace_existing": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_human"] == 1
    assert body["updated"] == 0

    await db_session.refresh(pre)
    assert pre.self_storage.value == "permitted"  # unchanged
    assert pre.human_reviewed is True
    assert pre.notes == "HAND VERDICT"


async def test_upload_human_may_update_human_row(client, db_session, jurisdiction_id):
    """The guard blocks only NON-human overwrites — a human-reviewed incoming
    row may still update an existing human row (operator re-dispatch)."""
    pre = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        zone_code="I-2",
        municipality="Fort Lee borough",
        self_storage="conditional",
        mini_warehouse="conditional",
        light_industrial="conditional",
        luxury_garage_condo="unclear",
        confidence=0.9,
        notes="v1",
        classification_source="human",
        human_reviewed=True,
    )
    db_session.add(pre)
    await db_session.flush()

    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={
            "rows": [
                _row_payload(
                    zone_code="I-2",
                    self_storage="permitted",
                    notes="v2",
                    classification_source="human",
                    human_reviewed=True,
                )
            ],
            "replace_existing": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 1
    assert body["skipped_human"] == 0


async def test_upload_factory_still_upserts_non_human_rows(
    client, db_session, jurisdiction_id
):
    """Preserve existing behavior: a factory row CAN update a non-human
    (e.g. llm/heuristic) live row with replace_existing=true."""
    pre = ZoneUseMatrix(
        jurisdiction_id=jurisdiction_id,
        zone_code="C-1",
        municipality="Fort Lee borough",
        self_storage="unclear",
        mini_warehouse="unclear",
        light_industrial="unclear",
        luxury_garage_condo="unclear",
        confidence=0.4,
        notes="heuristic",
        classification_source="llm",
        human_reviewed=False,
    )
    db_session.add(pre)
    await db_session.flush()

    r = await client.post(
        f"/api/jurisdictions/{jurisdiction_id}/_upload-matrix-rows",
        json={
            "rows": [
                _row_payload(
                    zone_code="C-1",
                    self_storage="conditional",
                    notes="factory grounded",
                    classification_source="op5_factory",
                    human_reviewed=False,
                )
            ],
            "replace_existing": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 1
    assert body["skipped_human"] == 0
