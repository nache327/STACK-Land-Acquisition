"""Integration tests for spatial_backfill.backfill_parcel_zoning_from_districts.

Requires a Postgres+PostGIS test DB (the conftest db_session fixture). The
function-under-test opens its own raw asyncpg connection from
`settings.database_url`, so the fixture's DATABASE_URL must point to the same
database the test session uses (the conftest enforces this).

Each test commits its fixture rows explicitly because the backfill's separate
connection cannot see uncommitted state, then deletes them in a `finally`
block so the suite stays re-runnable on a persistent test DB.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.services.spatial_backfill import backfill_parcel_zoning_from_districts


# ── shared fixture: a synthetic jurisdiction with one district + 3 parcels ──
#
# Geometry layout (all WGS84, near Hackensack NJ for realism):
#   district     R-1  square ~110m on a side centered at (-74.000, 40.850)
#   P-INSIDE     point at (-74.0000, 40.8500) — centroid is inside R-1
#   P-NEAR       point at (-73.9989, 40.8500) — ~50m east of the R-1 edge
#   P-FAR        point at (-73.9940, 40.8500) — ~460m east of the R-1 edge
#
# At ~40.85°N: 0.0001° longitude ≈ 8.4 m. The district half-width is 0.0005°
# (~42 m), the NEAR parcel sits 0.0006° east of the centroid (~5 m past the
# east edge ≈ ~46 m away geodesic). We use generous radius gaps in the
# assertions so the test isn't pinned to spheroid-vs-sphere distance details.

@pytest_asyncio.fixture(loop_scope="session")
async def _three_parcels_one_district(db_session):
    jid = uuid.uuid4()
    parcel_ids: dict[str, int] = {}

    await db_session.execute(
        text(
            "INSERT INTO jurisdictions (id, name, state) "
            "VALUES (:id, :name, 'NJ')"
        ),
        {"id": jid, "name": f"test-zb-{jid.hex[:8]}"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO zoning_districts (
                jurisdiction_id, zone_code, zone_class, geom, source, human_reviewed
            ) VALUES (
                :jid, 'R-1', 'residential',
                ST_GeomFromText(
                    'POLYGON((-74.0005 40.8495, -74.0005 40.8505, '
                    '-73.9995 40.8505, -73.9995 40.8495, -74.0005 40.8495))',
                    4326
                ),
                'manual', FALSE
            )
            """
        ),
        {"jid": jid},
    )
    for apn, wkt in (
        ("P-INSIDE", "POINT(-74.0000 40.8500)"),
        ("P-NEAR", "POINT(-73.9989 40.8500)"),
        ("P-FAR", "POINT(-73.9940 40.8500)"),
    ):
        # in_flood_zone / in_wetland are NOT NULL with Python-side
        # (column-level) defaults, so a raw INSERT must supply them
        # explicitly — the server-side DEFAULT is absent.
        result = await db_session.execute(
            text(
                """
                INSERT INTO parcels (
                    jurisdiction_id, apn, geom,
                    in_flood_zone, in_wetland
                )
                VALUES (
                    :jid, :apn, ST_GeomFromText(:wkt, 4326),
                    FALSE, FALSE
                )
                RETURNING id
                """
            ),
            {"jid": jid, "apn": apn, "wkt": wkt},
        )
        parcel_ids[apn] = int(result.scalar_one())
    # Commit so the function-under-test's separate asyncpg connection can
    # see the rows. The fixture's own rollback at session-end is a no-op
    # once we've committed; we clean up explicitly below.
    await db_session.commit()

    try:
        yield jid, parcel_ids
    finally:
        await db_session.execute(
            text("DELETE FROM parcels WHERE jurisdiction_id = :jid"),
            {"jid": jid},
        )
        await db_session.execute(
            text("DELETE FROM zoning_districts WHERE jurisdiction_id = :jid"),
            {"jid": jid},
        )
        await db_session.execute(
            text("DELETE FROM jurisdictions WHERE id = :jid"),
            {"jid": jid},
        )
        await db_session.commit()


# ── Pass 1 (existing behavior) — no nearest fallback ────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_contained_pass_only_binds_centroid_inside_parcels(
    db_session, _three_parcels_one_district
):
    jid, parcel_ids = _three_parcels_one_district

    updated = await backfill_parcel_zoning_from_districts(jid, db_session)

    # Only P-INSIDE matches ST_Within; the other two stay NULL.
    assert updated == 1

    rows = await db_session.execute(
        text(
            "SELECT apn, zoning_code, zone_binding_method "
            "FROM parcels WHERE jurisdiction_id = :jid"
        ),
        {"jid": jid},
    )
    by_apn = {r.apn: r for r in rows}
    assert by_apn["P-INSIDE"].zoning_code == "R-1"
    assert by_apn["P-INSIDE"].zone_binding_method == "contained"
    assert by_apn["P-NEAR"].zoning_code is None
    assert by_apn["P-NEAR"].zone_binding_method is None
    assert by_apn["P-FAR"].zoning_code is None
    assert by_apn["P-FAR"].zone_binding_method is None


# ── Pass 2 (new) — nearest-district fallback ────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_nearest_within_100m_binds_only_near_parcel(
    db_session, _three_parcels_one_district
):
    jid, parcel_ids = _three_parcels_one_district

    updated = await backfill_parcel_zoning_from_districts(
        jid, db_session, nearest_within_meters=100.0
    )

    # P-INSIDE (contained) + P-NEAR (nearest_100m). P-FAR is 460m away → out.
    assert updated == 2

    rows = await db_session.execute(
        text(
            "SELECT apn, zoning_code, zone_binding_method "
            "FROM parcels WHERE jurisdiction_id = :jid"
        ),
        {"jid": jid},
    )
    by_apn = {r.apn: r for r in rows}
    assert by_apn["P-INSIDE"].zone_binding_method == "contained"
    assert by_apn["P-INSIDE"].zoning_code == "R-1"
    assert by_apn["P-NEAR"].zone_binding_method == "nearest_100m"
    assert by_apn["P-NEAR"].zoning_code == "R-1"
    assert by_apn["P-FAR"].zone_binding_method is None
    assert by_apn["P-FAR"].zoning_code is None


@pytest.mark.asyncio(loop_scope="session")
async def test_nearest_within_1000m_also_binds_far_parcel(
    db_session, _three_parcels_one_district
):
    jid, parcel_ids = _three_parcels_one_district

    updated = await backfill_parcel_zoning_from_districts(
        jid, db_session, nearest_within_meters=1000.0
    )

    # 1000m radius pulls in P-FAR (~460m away) as well.
    assert updated == 3

    rows = await db_session.execute(
        text(
            "SELECT apn, zone_binding_method "
            "FROM parcels WHERE jurisdiction_id = :jid"
        ),
        {"jid": jid},
    )
    by_apn = {r.apn: r.zone_binding_method for r in rows}
    assert by_apn["P-INSIDE"] == "contained"
    assert by_apn["P-NEAR"] == "nearest_1000m"
    assert by_apn["P-FAR"] == "nearest_1000m"


# ── audit_zoning_coverage script: binding-method split appears in output ────

@pytest.mark.asyncio(loop_scope="session")
async def test_audit_output_splits_coverage_by_binding_method(
    db_session, _three_parcels_one_district
):
    """The audit script should report contained-vs-nearest coverage % so
    operators can read the inferred share without altering the ≥70% gate.
    Verifies the SchemaProfile picks up the new column and the SQL emits
    both `parcel_zoning_code_coverage_pct_contained` and `_nearest`."""
    from dataclasses import asdict

    from scripts.audit_zoning_coverage import (
        _build_audit,
        _build_audit_sql,
        _load_schema_profile,
    )

    jid, _ = _three_parcels_one_district

    # Bind two of the three parcels: one contained, one nearest_100m.
    await backfill_parcel_zoning_from_districts(
        jid, db_session, nearest_within_meters=100.0
    )

    # Use a separate raw connection from the session — _load_schema_profile
    # and _build_audit_sql take the same connection object the script uses
    # at the top level (sqlalchemy async connection).
    conn = await db_session.connection()
    schema = await _load_schema_profile(conn)
    assert schema.has_parcel_zone_binding_method_column is True

    result = await conn.execute(
        _build_audit_sql(schema),
        {"jurisdiction_name": None},
    )
    audits = [_build_audit(r, schema) for r in result]
    audit = next(a for a in audits if uuid.UUID(a.id) == jid)
    snapshot = asdict(audit)

    # Both new fields are present in the dataclass payload.
    assert "parcel_zoning_code_coverage_pct_contained" in snapshot
    assert "parcel_zoning_code_coverage_pct_nearest" in snapshot

    # 3 parcels total, 1 contained, 1 nearest → contained=33.3%, nearest=33.3%,
    # combined zoning_code coverage=66.7%. The combined number is the
    # operational gate; the split is for transparency.
    assert audit.parcel_count == 3
    assert audit.parcel_zoning_code_coverage_pct == 66.7
    assert audit.parcel_zoning_code_coverage_pct_contained == 33.3
    assert audit.parcel_zoning_code_coverage_pct_nearest == 33.3
