"""Tests for GET /api/admin/op5/uncovered-zone-codes.

Covers the 5 contract points from the endpoint spec:

  1. Returns zone codes present in parcels but NOT covered by matrix.
  2. Orders rows by parcel_count DESC, zone_code ASC.
  3. sample_towns is the top 3 munis (by parcel count) for the code.
  4. Respects `min_parcel_count` filter on the rows.
  5. Returns 404 for unknown jurisdiction.

Strategy mirrors test_admin_op5_matrix.py — drive the FastAPI app via
httpx.ASGITransport, override `get_db` to yield the conftest's
transaction-scoped session so each test rolls back at the end.

The endpoint uses raw SQL against `parcels` + `zone_use_matrix`, so the
fixtures seed parcels directly via the ORM (no source assessor fetch).
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import get_db
from app.main import app
from app.models.parcel import Parcel
from app.models.zone_use_matrix import ZoneUseMatrix


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


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
async def jurisdiction_id(db_session) -> uuid.UUID:
    jid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO jurisdictions (id, name, state) "
            "VALUES (:id, :name, 'NJ')"
        ),
        {"id": jid, "name": f"test-uncovered-{jid.hex[:8]}"},
    )
    await db_session.flush()
    return jid


async def _seed_parcels(
    db_session,
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    count: int,
    city: str | None = "Test Town",
    apn_prefix: str | None = None,
) -> None:
    """Seed `count` parcels with the given zone_code and city.

    apn_prefix scopes the synthetic apns so multiple seed calls in one
    test don't collide on the natural-ish APN string.
    """
    prefix = apn_prefix or f"{zone_code}-{(city or 'none').replace(' ', '_')}"
    for i in range(count):
        db_session.add(
            Parcel(
                jurisdiction_id=jurisdiction_id,
                apn=f"{prefix}-{i}",
                zoning_code=zone_code,
                city=city,
            )
        )
    await db_session.flush()


async def _seed_matrix(
    db_session,
    jurisdiction_id: uuid.UUID,
    zone_code: str,
    municipality: str | None = None,
) -> None:
    """Seed a jurisdiction-default matrix row for `zone_code`."""
    db_session.add(
        ZoneUseMatrix(
            jurisdiction_id=jurisdiction_id,
            zone_code=zone_code,
            municipality=municipality,
            self_storage="prohibited",
            mini_warehouse="prohibited",
            light_industrial="prohibited",
            luxury_garage_condo="prohibited",
            classification_source="human",
        )
    )
    await db_session.flush()


# ────────────────────────────────────────────────────────────────────────────
# 1. uncovered = codes in parcels but not in matrix
# ────────────────────────────────────────────────────────────────────────────


async def test_uncovered_returns_codes_not_in_matrix(
    client, db_session, jurisdiction_id
):
    """Codes X, Y, Z exist in parcels. Matrix only covers X.

    Expect rows to include Y and Z (uncovered) and exclude X (covered).
    """
    await _seed_parcels(db_session, jurisdiction_id, "X", 5)
    await _seed_parcels(db_session, jurisdiction_id, "Y", 3)
    await _seed_parcels(db_session, jurisdiction_id, "Z", 7)
    await _seed_matrix(db_session, jurisdiction_id, "X")

    r = await client.get(
        "/api/admin/op5/uncovered-zone-codes",
        params={"jurisdiction_id": str(jurisdiction_id)},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    returned_codes = {row["zone_code"] for row in body["rows"]}
    assert "Y" in returned_codes
    assert "Z" in returned_codes
    assert "X" not in returned_codes

    # Summary: 2 uncovered codes (Y, Z), 10 stranded parcels (3 + 7).
    assert body["uncovered_count"] == 2
    assert body["total_parcels_uncovered"] == 10
    assert body["jurisdiction_id"] == str(jurisdiction_id)


# ────────────────────────────────────────────────────────────────────────────
# 2. ordering by parcel_count DESC
# ────────────────────────────────────────────────────────────────────────────


async def test_uncovered_orders_by_parcel_count_desc(
    client, db_session, jurisdiction_id
):
    """Highest-count code must come first, then ASC by code on tie-break."""
    await _seed_parcels(db_session, jurisdiction_id, "LOW", 2)
    await _seed_parcels(db_session, jurisdiction_id, "HIGH", 50)
    await _seed_parcels(db_session, jurisdiction_id, "MID", 10)

    r = await client.get(
        "/api/admin/op5/uncovered-zone-codes",
        params={"jurisdiction_id": str(jurisdiction_id)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    codes_in_order = [row["zone_code"] for row in body["rows"]]
    assert codes_in_order == ["HIGH", "MID", "LOW"]
    assert body["rows"][0]["parcel_count"] == 50


# ────────────────────────────────────────────────────────────────────────────
# 3. sample_towns = top 3 by per-(code, city) count
# ────────────────────────────────────────────────────────────────────────────


async def test_uncovered_sample_towns_uses_top3(
    client, db_session, jurisdiction_id
):
    """Code Y spans 5 towns with distinct parcel counts.

    Expect sample_towns to be the top 3 by count, in count-desc order.
    Town counts: A=10, B=8, C=6, D=4, E=2 → expect [A, B, C].
    """
    counts = {"TownA": 10, "TownB": 8, "TownC": 6, "TownD": 4, "TownE": 2}
    for city, n in counts.items():
        await _seed_parcels(
            db_session,
            jurisdiction_id,
            "Y",
            n,
            city=city,
            apn_prefix=f"Y-{city}",
        )

    r = await client.get(
        "/api/admin/op5/uncovered-zone-codes",
        params={"jurisdiction_id": str(jurisdiction_id)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    y_rows = [row for row in body["rows"] if row["zone_code"] == "Y"]
    assert len(y_rows) == 1
    sample = y_rows[0]["sample_towns"]
    assert sample == ["TownA", "TownB", "TownC"]


# ────────────────────────────────────────────────────────────────────────────
# 4. min_parcel_count filter
# ────────────────────────────────────────────────────────────────────────────


async def test_uncovered_respects_min_parcel_count(
    client, db_session, jurisdiction_id
):
    """Y has 1 parcel, Z has 100. min_parcel_count=5 -> Y dropped from rows.

    Summary counts still include Y because the spec carves out
    min_parcel_count to the row worklist only — sprint sizing must see
    the full long tail.
    """
    await _seed_parcels(db_session, jurisdiction_id, "Y", 1)
    await _seed_parcels(db_session, jurisdiction_id, "Z", 100)

    r = await client.get(
        "/api/admin/op5/uncovered-zone-codes",
        params={
            "jurisdiction_id": str(jurisdiction_id),
            "min_parcel_count": 5,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    codes = {row["zone_code"] for row in body["rows"]}
    assert "Z" in codes
    assert "Y" not in codes

    # Summary unaffected by min_parcel_count.
    assert body["uncovered_count"] == 2
    assert body["total_parcels_uncovered"] == 101


# ────────────────────────────────────────────────────────────────────────────
# 5. 404 for unknown jurisdiction
# ────────────────────────────────────────────────────────────────────────────


async def test_uncovered_404_for_unknown_jurisdiction(client):
    fake = uuid.uuid4()
    r = await client.get(
        "/api/admin/op5/uncovered-zone-codes",
        params={"jurisdiction_id": str(fake)},
    )
    assert r.status_code == 404, r.text
    assert "not found" in r.json()["detail"].lower()
