"""Tests for POST /api/parcels/search Phase 1.5 perf pass.

Pins four contracts:

1. **Slim shape** when `slim=true`: only the paint-relevant fields
   (parcel_id, apn, geom, storage_permission, zoning_code, zone_class,
   is_viable) are present; the popup-only fields the dispatch lists
   are absent.
2. **Backward compat**: default (`slim=false`) response shape is
   unchanged — every existing CandidateParcelRow field still present.
3. **Server-side memo**: a repeat call with the same payload + same
   captured_at returns `X-Cache: HIT` and the byte-identical body.
4. **Memo invalidation on captured_at advance**: writing a newer
   `coverage_snapshots` row rotates the cache key; the next call
   misses.

The Cache-Control header is set on both HIT and MISS.
"""
from __future__ import annotations

import datetime as _dt
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
async def jurisdiction_with_one_parcel(db_session):
    """One jurisdiction + one parcel + one matrix row mapping its
    zone to 'permitted'. Enough to assert shape + cache behavior."""
    jid = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO jurisdictions (id, name, state) VALUES (:id, :name, 'NJ')"),
        {"id": jid, "name": f"ps-test-{jid.hex[:8]}"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO parcels (
                jurisdiction_id, apn, geom, zoning_code, zone_class,
                acres, has_structure, in_flood_zone, in_wetland, address
            )
            VALUES (
                :jid, 'PS-1',
                ST_GeomFromText('POLYGON((-74 40, -74 40.001, -73.999 40.001, -73.999 40, -74 40))', 4326),
                'R-1', 'residential',
                1.5, FALSE, FALSE, FALSE, '123 Main St'
            )
            """
        ),
        {"jid": jid},
    )
    # zone_use_matrix has Python-side defaults on the four UsePermission
    # columns — raw INSERT must supply each explicitly (see
    # test_parcels_map_layer.py for the same gotcha).
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
            text("DELETE FROM coverage_snapshots WHERE jurisdiction_id = :jid"),
            {"jid": jid},
        )
        await db_session.execute(
            text("DELETE FROM jurisdictions WHERE id = :jid"),
            {"jid": jid},
        )
        await db_session.commit()
        _parcels_search_cache_clear()


def _basic_payload(jid: uuid.UUID, *, slim: bool = False) -> dict:
    return {
        "jurisdiction_id": str(jid),
        "target_use": "self_storage",
        "filters": {},
        "page": 1,
        "page_size": 100,
        "sort": "acres_desc",
        "slim": slim,
    }


# ─── slim shape contract ─────────────────────────────────────────────────────


_SLIM_KEPT_KEYS = {
    "parcel_id",
    "apn",
    "geom",
    "storage_permission",
    "zoning_code",
    "zone_class",
    "is_viable",
    # Restored after the initial slim landing — Map.tsx paint
    # expressions (lines 678, 892) read both. See the slim-restore PR.
    "has_listing",
    "garage_permission",
}

_SLIM_DROPPED_KEYS = {
    "address",
    "acres",
    "has_structure",
    "in_flood_zone",
    "in_wetland",
    "aadt",
    "storage_allowed",
    "storage_conditional",
    "violation_reasons",
    "listing_summary",
    "city",
}


@pytest.mark.asyncio(loop_scope="session")
async def test_slim_response_has_only_paint_fields(
    client, jurisdiction_with_one_parcel
):
    jid = jurisdiction_with_one_parcel
    resp = await client.post(
        "/api/parcels/search", json=_basic_payload(jid, slim=True)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    row = body["items"][0]
    assert set(row.keys()) == _SLIM_KEPT_KEYS, (
        f"expected exactly {_SLIM_KEPT_KEYS}, got {set(row.keys())}"
    )
    assert _SLIM_DROPPED_KEYS.isdisjoint(row.keys())
    assert row["storage_permission"] == "permitted"
    assert row["zoning_code"] == "R-1"
    assert row["zone_class"] == "residential"
    assert row["is_viable"] is True  # permitted + no structure/flood/wetland
    # Paint-pipeline fields restored after the initial slim landing:
    # the test fixture has no forsale_listings row + matrix.luxury_garage_condo
    # is 'unclear', so has_listing=false and garage_permission='unclear'.
    assert row["has_listing"] is False
    assert row["garage_permission"] == "unclear"


# ─── paint fields populate correctly when underlying data exists ─────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_slim_has_listing_true_when_matched_listing_exists(
    client, db_session, jurisdiction_with_one_parcel
):
    """Insert a current matched forsale_listing for the fixture parcel
    and assert slim's has_listing flips true. This is the load-bearing
    paint field for Map.tsx:678's magenta for-sale outline."""
    jid = jurisdiction_with_one_parcel
    # Discover the parcel_id from the test fixture row.
    row = (await db_session.execute(
        text("SELECT id FROM parcels WHERE jurisdiction_id = :jid"),
        {"jid": jid},
    )).scalar_one()
    # forsale_listings has several NOT NULL columns with no server_default
    # (address, sale_status, raw_row). is_current / first_seen_at /
    # last_seen_at have server_defaults so they can be omitted.
    await db_session.execute(
        text(
            """
            INSERT INTO forsale_listings (
                jurisdiction_id, source, address, sale_status, raw_row,
                matched_parcel_id
            )
            VALUES (
                :jid, 'test', '1 Test Way', 'Active', '{}'::jsonb,
                :pid
            )
            """
        ),
        {"jid": jid, "pid": row},
    )
    await db_session.commit()

    from app.api.parcels import _parcels_search_cache_clear
    _parcels_search_cache_clear()

    try:
        resp = await client.post(
            "/api/parcels/search", json=_basic_payload(jid, slim=True)
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["has_listing"] is True
    finally:
        await db_session.execute(
            text("DELETE FROM forsale_listings WHERE jurisdiction_id = :jid"),
            {"jid": jid},
        )
        await db_session.commit()
        _parcels_search_cache_clear()


# ─── slim payload is still meaningfully smaller than full ────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_slim_response_is_smaller_than_full(
    client, jurisdiction_with_one_parcel
):
    """Restoring has_listing + garage_permission adds ~13 bytes per row;
    slim should still be measurably smaller than full because the
    popup-only fields (address, acres, has_structure, in_flood_zone,
    in_wetland, aadt, storage_allowed, storage_conditional,
    violation_reasons, listing_summary, city) all drop out."""
    jid = jurisdiction_with_one_parcel

    full_resp = await client.post(
        "/api/parcels/search", json=_basic_payload(jid, slim=False)
    )
    slim_resp = await client.post(
        "/api/parcels/search", json=_basic_payload(jid, slim=True)
    )
    assert full_resp.status_code == 200
    assert slim_resp.status_code == 200
    # One-row fixture isn't representative of Bergen-scale savings but
    # any savings at all proves slim is still narrower than full —
    # production validation lives in the PR body's curl harness.
    assert len(slim_resp.content) < len(full_resp.content)


# ─── backward-compat: slim=false is the existing shape ───────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_full_response_unchanged_when_slim_false(
    client, jurisdiction_with_one_parcel
):
    jid = jurisdiction_with_one_parcel
    resp = await client.post(
        "/api/parcels/search", json=_basic_payload(jid, slim=False)
    )
    assert resp.status_code == 200
    row = resp.json()["items"][0]
    # Every CandidateParcelRow field present (positive pin guards
    # against accidental schema drift).
    for k in (
        "parcel_id", "apn", "address", "city", "acres", "zoning_code",
        "zone_class", "storage_permission", "garage_permission",
        "storage_allowed", "storage_conditional", "in_flood_zone",
        "in_wetland", "aadt", "has_structure", "is_viable",
        "violation_reasons", "geom", "listing_summary",
    ):
        assert k in row, f"full shape missing field {k!r}"


@pytest.mark.asyncio(loop_scope="session")
async def test_full_response_when_slim_field_omitted(
    client, jurisdiction_with_one_parcel
):
    """Existing callers that don't include `slim` at all must keep
    getting the full shape — the field defaults to False on the model."""
    jid = jurisdiction_with_one_parcel
    payload = _basic_payload(jid)
    payload.pop("slim")
    resp = await client.post("/api/parcels/search", json=payload)
    assert resp.status_code == 200
    row = resp.json()["items"][0]
    assert "address" in row  # popup-only field — present in full shape


# ─── Cache-Control header ────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_response_carries_cacheable_cache_control(
    client, jurisdiction_with_one_parcel
):
    jid = jurisdiction_with_one_parcel
    resp = await client.post(
        "/api/parcels/search", json=_basic_payload(jid, slim=True)
    )
    assert resp.headers["cache-control"] == (
        "public, s-maxage=60, stale-while-revalidate=300"
    )


# ─── server-side memo: HIT on repeat, MISS after captured_at advances ────────


@pytest.mark.asyncio(loop_scope="session")
async def test_repeat_call_hits_in_process_cache(
    client, jurisdiction_with_one_parcel
):
    jid = jurisdiction_with_one_parcel
    payload = _basic_payload(jid, slim=True)
    first = await client.post("/api/parcels/search", json=payload)
    second = await client.post("/api/parcels/search", json=payload)

    assert first.headers.get("x-cache") == "MISS"
    assert second.headers.get("x-cache") == "HIT"
    assert first.content == second.content


@pytest.mark.asyncio(loop_scope="session")
async def test_slim_and_full_use_distinct_cache_keys(
    client, jurisdiction_with_one_parcel
):
    """The cache key folds in the payload — slim=true and slim=false
    must not collide. Two calls with different slim flag both MISS."""
    jid = jurisdiction_with_one_parcel
    first = await client.post(
        "/api/parcels/search", json=_basic_payload(jid, slim=False)
    )
    second = await client.post(
        "/api/parcels/search", json=_basic_payload(jid, slim=True)
    )
    assert first.headers.get("x-cache") == "MISS"
    assert second.headers.get("x-cache") == "MISS"


@pytest.mark.asyncio(loop_scope="session")
async def test_advancing_captured_at_invalidates_cache(
    client, db_session, jurisdiction_with_one_parcel
):
    jid = jurisdiction_with_one_parcel
    payload = _basic_payload(jid, slim=True)

    first = await client.post("/api/parcels/search", json=payload)
    assert first.headers.get("x-cache") == "MISS"
    second = await client.post("/api/parcels/search", json=payload)
    assert second.headers.get("x-cache") == "HIT"

    await db_session.execute(
        text(
            """
            INSERT INTO coverage_snapshots (
                id, jurisdiction_id, jurisdiction_name, captured_at, source
            )
            VALUES (gen_random_uuid(), :jid, 'ps-test', :ts, 'test')
            """
        ),
        {"jid": jid, "ts": _dt.datetime.now(_dt.timezone.utc)},
    )
    await db_session.commit()

    third = await client.post("/api/parcels/search", json=payload)
    assert third.headers.get("x-cache") == "MISS"
    # Content shape unchanged — parcel data hasn't moved.
    assert third.json()["items"] == first.json()["items"]
