"""Tests for GET /api/jurisdictions/{id}/parcels/map — Phase 1 perf pass.

Pins three contracts:

1. **Slim property set.** Each Feature's `properties` contains *only* the
   fields the MapLibre paint pipeline reads (plus the click-targeting
   `id`). Heavy detail (`apn`, `address`, `acres`, structure/flood/wetland
   flags) was removed in Phase 1 — clicks fetch via /api/parcels/{id}.

2. **Cache-Control.** Response carries
   `public, s-maxage=300, stale-while-revalidate=600` — replaces the
   prior `no-store`, lets upstream HTTP caches do their job.

3. **Server-side memo invalidation.** Repeat calls with no audit refresh
   hit the in-process LRU and return `X-Cache: HIT`. When the audit
   refresh advances `coverage_snapshots.captured_at`, the next call
   misses and rebuilds.
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
    """One jurisdiction + one parcel + one zone_use_matrix row that maps
    the parcel's zoning_code to 'permitted'. Enough to assert shape + the
    storage_permission derivation."""
    jid = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO jurisdictions (id, name, state) VALUES (:id, :name, 'NJ')"),
        {"id": jid, "name": f"pm-test-{jid.hex[:8]}"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO parcels (
                jurisdiction_id, apn, geom, zoning_code, zone_class,
                acres, has_structure, in_flood_zone, in_wetland, address
            )
            VALUES (
                :jid, 'P-1',
                ST_GeomFromText('POLYGON((-74 40, -74 40.001, -73.999 40.001, -73.999 40, -74 40))', 4326),
                'R-1', 'residential',
                1.5, FALSE, FALSE, FALSE, '123 Main St'
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
                luxury_garage_condo, human_reviewed
            )
            VALUES (:jid, 'R-1', 'permitted', 'unclear', 'unclear', TRUE)
            """
        ),
        {"jid": jid},
    )
    # Commit so the endpoint's request-scoped session sees the data.
    await db_session.commit()

    # Clear the in-process cache so test ordering doesn't leak state.
    from app.api.jurisdictions import _parcels_map_cache_clear
    _parcels_map_cache_clear()

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
        _parcels_map_cache_clear()


# ─── slim property set — Phase 1 contract ────────────────────────────────────


_EXPECTED_PROPERTY_KEYS = {"id", "zoning_code", "zone_class", "storage_permission"}
_REMOVED_PROPERTY_KEYS = {
    "apn",
    "acres",
    "has_structure",
    "in_flood_zone",
    "in_wetland",
    "address",
}


@pytest.mark.asyncio(loop_scope="session")
async def test_response_carries_only_slim_property_set(
    client, jurisdiction_with_one_parcel
):
    jid = jurisdiction_with_one_parcel

    resp = await client.get(f"/api/jurisdictions/{jid}/parcels/map")
    assert resp.status_code == 200
    fc = resp.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert set(props.keys()) == _EXPECTED_PROPERTY_KEYS, (
        f"expected exactly {_EXPECTED_PROPERTY_KEYS}, got {set(props.keys())}"
    )
    # Negative pin so a future re-add lands in a test failure, not a quiet
    # tile bloat regression.
    assert _REMOVED_PROPERTY_KEYS.isdisjoint(props.keys())
    # Sanity-check the load-bearing paint field.
    assert props["storage_permission"] == "permitted"
    assert props["zoning_code"] == "R-1"
    assert props["zone_class"] == "residential"


# ─── Cache-Control header ────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_response_carries_cacheable_cache_control(
    client, jurisdiction_with_one_parcel
):
    jid = jurisdiction_with_one_parcel
    resp = await client.get(f"/api/jurisdictions/{jid}/parcels/map")
    assert resp.headers["cache-control"] == (
        "public, s-maxage=300, stale-while-revalidate=600"
    )


# ─── server-side memo: hit on repeat, miss after captured_at advances ────────


@pytest.mark.asyncio(loop_scope="session")
async def test_repeat_call_hits_in_process_cache(
    client, jurisdiction_with_one_parcel
):
    jid = jurisdiction_with_one_parcel

    first = await client.get(f"/api/jurisdictions/{jid}/parcels/map")
    second = await client.get(f"/api/jurisdictions/{jid}/parcels/map")

    assert first.headers.get("x-cache") == "MISS"
    assert second.headers.get("x-cache") == "HIT"
    # Bytes must match — cache hit serves the exact pre-serialized payload.
    assert first.content == second.content


@pytest.mark.asyncio(loop_scope="session")
async def test_advancing_captured_at_invalidates_cache(
    client, db_session, jurisdiction_with_one_parcel
):
    """When the audit refresh writes a newer `coverage_snapshots` row,
    the (jid, captured_at) key changes and the next request rebuilds."""
    jid = jurisdiction_with_one_parcel

    # Warm the cache.
    first = await client.get(f"/api/jurisdictions/{jid}/parcels/map")
    assert first.headers.get("x-cache") == "MISS"

    second = await client.get(f"/api/jurisdictions/{jid}/parcels/map")
    assert second.headers.get("x-cache") == "HIT"

    # Insert a snapshot — captured_at advances → key changes → next call
    # is a fresh miss.
    await db_session.execute(
        text(
            """
            INSERT INTO coverage_snapshots (
                id, jurisdiction_id, jurisdiction_name, captured_at, source
            )
            VALUES (
                gen_random_uuid(), :jid, 'pm-test', :ts, 'test'
            )
            """
        ),
        {"jid": jid, "ts": _dt.datetime.now(_dt.timezone.utc)},
    )
    await db_session.commit()

    third = await client.get(f"/api/jurisdictions/{jid}/parcels/map")
    assert third.headers.get("x-cache") == "MISS", (
        "audit refresh should have invalidated the cache key"
    )
    # Content still equals (no parcel data changed) — the invalidation
    # is about freshness, not about changing the response.
    assert third.json() == first.json()
