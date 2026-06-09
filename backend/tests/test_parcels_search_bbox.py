"""Tests for POST /api/parcels/search Phase 2 bbox filtering.

Backend bbox wiring at `candidate_search.py:189-192` was already present
on `main` when Phase 2 landed — Phase 2 wires it through the frontend
and adds these regression tests so the contract can't silently break.

Pins:

1. **No bbox → unchanged behavior.** Existing full-jurisdiction fetch
   path is the baseline; ensure adding bbox support didn't change the
   shape or count when bbox is absent.
2. **bbox containing the parcel → it's returned**, `.total` reflects
   the bbox-filtered count.
3. **bbox excluding the parcel → empty result**, `.total == 0`.
4. **bbox + filters compose** — bbox AND a storage_permission filter
   both apply (not just one).
5. **Cache keys split by bbox** — two different bboxes both MISS the
   in-process memo (so paged viewports don't collide).
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


@pytest_asyncio.fixture(loop_scope="session")
async def jurisdiction_with_parcel_at_origin(db_session):
    """One parcel at lng/lat (-74.0, 40.0) — same shape as the other
    perf tests' fixture so existing parcel-search assertions still
    hold. Bbox tests pick windows around that point."""
    jid = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO jurisdictions (id, name, state) VALUES (:id, :name, 'NJ')"),
        {"id": jid, "name": f"bbox-test-{jid.hex[:8]}"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO parcels (
                jurisdiction_id, apn, geom, zoning_code, zone_class,
                acres, has_structure, in_flood_zone, in_wetland, address
            )
            VALUES (
                :jid, 'BX-1',
                ST_GeomFromText('POLYGON((-74 40, -74 40.001, -73.999 40.001, -73.999 40, -74 40))', 4326),
                'R-1', 'residential',
                1.5, FALSE, FALSE, FALSE, '1 Test Ave'
            )
            """
        ),
        {"jid": jid},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO zone_use_matrix (
                jurisdiction_id, zone_code, self_storage, mini_warehouse,
                light_industrial, luxury_garage_condo, human_reviewed
            )
            VALUES (:jid, 'R-1', 'permitted', 'unclear', 'unclear', 'unclear', TRUE)
            """
        ),
        {"jid": jid},
    )
    await db_session.commit()

    from app.api.parcels import _parcels_search_cache_clear
    _parcels_search_cache_clear()

    try:
        yield jid
    finally:
        await db_session.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"),
            {"jid": jid},
        )
        await db_session.execute(
            text("DELETE FROM parcels WHERE jurisdiction_id = :jid"),
            {"jid": jid},
        )
        await db_session.execute(
            text("DELETE FROM jurisdictions WHERE id = :jid"),
            {"jid": jid},
        )
        await db_session.commit()
        _parcels_search_cache_clear()


def _payload(jid: uuid.UUID, **overrides: object) -> dict:
    base = {
        "jurisdiction_id": str(jid),
        "target_use": "self_storage",
        "filters": {},
        "page": 1,
        "page_size": 100,
        "sort": "acres_desc",
        "slim": True,
    }
    base.update(overrides)
    return base


# ─── unchanged behavior when bbox is absent ──────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_no_bbox_returns_full_jurisdiction(
    client, jurisdiction_with_parcel_at_origin
):
    jid = jurisdiction_with_parcel_at_origin
    resp = await client.post("/api/parcels/search", json=_payload(jid))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


# ─── bbox containing the parcel ─────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_bbox_containing_parcel_returns_it(
    client, jurisdiction_with_parcel_at_origin
):
    jid = jurisdiction_with_parcel_at_origin
    # Window from -74.01,39.99 to -73.99,40.01 — encloses the parcel
    # at (-74.0..-73.999, 40.0..40.001).
    resp = await client.post(
        "/api/parcels/search",
        json=_payload(jid, bbox=[-74.01, 39.99, -73.99, 40.01]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1, "bbox-scoped count should equal one"
    assert len(body["items"]) == 1
    assert body["items"][0]["apn"] == "BX-1"


# ─── bbox excluding the parcel ──────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_bbox_excluding_parcel_returns_empty(
    client, jurisdiction_with_parcel_at_origin
):
    jid = jurisdiction_with_parcel_at_origin
    # Window 1 degree to the east — far outside the parcel.
    resp = await client.post(
        "/api/parcels/search",
        json=_payload(jid, bbox=[-73.0, 40.0, -72.9, 40.1]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0, "bbox excludes parcel → count zero"
    assert body["items"] == []


# ─── bbox + filters compose ─────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_bbox_and_storage_permission_filter_both_apply(
    client, jurisdiction_with_parcel_at_origin
):
    """bbox containing the parcel + a storage_permission filter that
    matches → parcel returned. Same bbox + non-matching filter →
    parcel filtered out. Confirms both predicates AND together."""
    jid = jurisdiction_with_parcel_at_origin
    in_bbox = [-74.01, 39.99, -73.99, 40.01]

    match = await client.post(
        "/api/parcels/search",
        json=_payload(
            jid,
            bbox=in_bbox,
            filters={"storage_permissions": ["permitted"]},
        ),
    )
    assert match.status_code == 200
    assert match.json()["total"] == 1

    no_match = await client.post(
        "/api/parcels/search",
        json=_payload(
            jid,
            bbox=in_bbox,
            filters={"storage_permissions": ["prohibited"]},
        ),
    )
    assert no_match.status_code == 200
    assert no_match.json()["total"] == 0


# ─── distinct bbox values use distinct cache keys ───────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_different_bboxes_get_distinct_cache_keys(
    client, jurisdiction_with_parcel_at_origin
):
    """Two map pans land on different bboxes — both should MISS, not
    collide. Cache memo is keyed on the canonical payload (including
    bbox)."""
    jid = jurisdiction_with_parcel_at_origin
    a = await client.post(
        "/api/parcels/search",
        json=_payload(jid, bbox=[-74.01, 39.99, -73.99, 40.01]),
    )
    b = await client.post(
        "/api/parcels/search",
        json=_payload(jid, bbox=[-74.02, 39.98, -73.98, 40.02]),
    )
    assert a.headers.get("x-cache") == "MISS"
    assert b.headers.get("x-cache") == "MISS"

    # Re-hit the first one — should HIT.
    a2 = await client.post(
        "/api/parcels/search",
        json=_payload(jid, bbox=[-74.01, 39.99, -73.99, 40.01]),
    )
    assert a2.headers.get("x-cache") == "HIT"
    assert a2.content == a.content
