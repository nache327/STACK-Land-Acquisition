"""Tests for GET /api/jurisdictions/{id}/dashboard-context.

This endpoint exists because digest / deal-board deep links use the
JURISDICTION id as the /dashboard/[jobId] segment whenever the jurisdiction
has no ``status='ready'`` job — the majority case, since script-ingested
counties never drive a job to 'ready'. Those links hit GET /api/jobs/:id,
404'd, and the dashboard hung on "Loading…" forever.

Pins four contracts:

1. **Job-shaped response.** The payload validates as a job so the dashboard's
   poller/JobSchema can consume it without a second code path.
2. **status is always 'ready'.** Never the real latest job's status — a live
   'queued'/'running' would route the deep link into the JobProgress screen
   and strand the operator even though parcels are in the DB.
3. **jurisdiction_id round-trips** and jurisdiction_input carries the name
   (feeds the "Re-analyze" button + the map's cityName).
4. **404 on unknown jurisdiction and on a jurisdiction with no parcels** — an
   honest error beats an empty map.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import get_db
from app.main import app


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session):
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


async def _insert_jurisdiction(db_session, *, name: str) -> uuid.UUID:
    jid = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO jurisdictions (id, name, state) VALUES (:id, :name, 'UT')"),
        {"id": jid, "name": name},
    )
    return jid


async def _insert_parcel(db_session, jid: uuid.UUID) -> None:
    # in_flood_zone / in_wetland are NOT NULL with PYTHON-side defaults, which a
    # raw INSERT bypasses — supply them explicitly or CI fails on the constraint.
    await db_session.execute(
        text(
            """
            INSERT INTO parcels (
                jurisdiction_id, apn, geom, acres, in_flood_zone, in_wetland
            )
            VALUES (
                :jid, 'DC-1',
                ST_GeomFromText(
                    'POLYGON((-111.9 40.5, -111.9 40.501, -111.899 40.501, '
                    '-111.899 40.5, -111.9 40.5))', 4326),
                1.6, FALSE, FALSE
            )
            """
        ),
        {"jid": jid},
    )


@pytest_asyncio.fixture(loop_scope="session")
async def jurisdiction_with_parcels(db_session):
    """A jurisdiction holding parcels but NO ready job — the Draper City shape."""
    jid = await _insert_jurisdiction(db_session, name=f"dc-test-{uuid.uuid4().hex[:8]}")
    await _insert_parcel(db_session, jid)
    # A failed job, mirroring production: every Draper job is failed/cancelled.
    # The endpoint must ignore it and still report 'ready'.
    # force / attempts are NOT NULL with PYTHON-side defaults — raw INSERT
    # bypasses them, so set them here.
    await db_session.execute(
        text(
            "INSERT INTO jobs "
            "(id, jurisdiction_id, status, jurisdiction_input, force, attempts) "
            "VALUES (:id, :jid, 'failed', 'ignored', FALSE, 0)"
        ),
        {"id": uuid.uuid4(), "jid": jid},
    )
    await db_session.commit()
    try:
        yield jid
    finally:
        await db_session.execute(
            text("DELETE FROM jobs WHERE jurisdiction_id = :jid"), {"jid": jid}
        )
        await db_session.execute(
            text("DELETE FROM parcels WHERE jurisdiction_id = :jid"), {"jid": jid}
        )
        await db_session.execute(
            text("DELETE FROM jurisdictions WHERE id = :jid"), {"jid": jid}
        )
        await db_session.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def jurisdiction_without_parcels(db_session):
    jid = await _insert_jurisdiction(db_session, name=f"np-test-{uuid.uuid4().hex[:8]}")
    await db_session.commit()
    try:
        yield jid
    finally:
        await db_session.execute(
            text("DELETE FROM jurisdictions WHERE id = :jid"), {"jid": jid}
        )
        await db_session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_returns_ready_job_context(client, jurisdiction_with_parcels):
    jid = jurisdiction_with_parcels
    r = await client.get(f"/api/jurisdictions/{jid}/dashboard-context")
    assert r.status_code == 200, r.text
    body = r.json()

    # Contract 2: 'ready' despite the jurisdiction's only job being 'failed'.
    assert body["status"] == "ready"
    # Contract 3: the dashboard reads jurisdiction_id off this object.
    assert body["jurisdiction_id"] == str(jid)
    assert body["jurisdiction_input"]  # non-empty; feeds Re-analyze + cityName
    # Synthetic id mirrors the URL segment.
    assert body["id"] == str(jid)
    assert body["progress"]["synthetic"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_response_satisfies_job_read_schema(client, jurisdiction_with_parcels):
    """Contract 1: the payload must carry every field the frontend JobSchema
    requires, or the dashboard's zod parse throws and the page errors out —
    trading one broken state for another."""
    jid = jurisdiction_with_parcels
    r = await client.get(f"/api/jurisdictions/{jid}/dashboard-context")
    assert r.status_code == 200
    body = r.json()

    # Mirrors the non-optional keys of frontend/lib/schemas.ts JobSchema.
    for key in (
        "id",
        "jurisdiction_id",
        "status",
        "jurisdiction_input",
        "ordinance_url",
        "target_uses",
        "error_message",
        "progress",
        "created_at",
        "updated_at",
    ):
        assert key in body, f"JobSchema requires {key}"
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_404_on_unknown_jurisdiction(client):
    r = await client.get(f"/api/jurisdictions/{uuid.uuid4()}/dashboard-context")
    assert r.status_code == 404
    assert r.json()["detail"] == "Jurisdiction not found"


@pytest.mark.asyncio(loop_scope="session")
async def test_404_when_jurisdiction_has_no_parcels(
    client, jurisdiction_without_parcels
):
    """Contract 4: synthesizing 'ready' for a jurisdiction with nothing
    ingested would open an empty map and read as data loss."""
    r = await client.get(
        f"/api/jurisdictions/{jurisdiction_without_parcels}/dashboard-context"
    )
    assert r.status_code == 404
    assert "no ingested parcels" in r.json()["detail"]
