"""
End-to-end precedence tests (audit "D2") against PostGIS: a municipal district
binding must override a stale/junk county parcel-attribute code, while a
city_gis jurisdiction keeps its authoritative parcel code.

SAFETY: these commit + delete rows, so they run ONLY against a local/CI test
database. The module skips itself if DATABASE_URL is unset or looks like the
Supabase/pooled production DSN — never touches prod (catch #42).
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from app.services.spatial_backfill import backfill_parcel_zoning_from_districts

_DBURL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    (not _DBURL) or ("supabase" in _DBURL) or ("pooler" in _DBURL),
    reason="precedence DB tests run only against a local/CI test DB, never prod",
)

_DISTRICT_POLY = "POLYGON((0 0,0 1,1 1,1 0,0 0))"
_PARCEL_POLY = "POLYGON((0.4 0.4,0.4 0.6,0.6 0.6,0.6 0.4,0.4 0.4))"  # centroid inside district


async def _setup(db, *, parcel_code, dist_code, dist_class):
    jid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO jurisdictions (id, name, state) VALUES (:id, :n, :s)"),
        {"id": jid, "n": f"Test {jid}", "s": "PA"},
    )
    # Raw SQL bypasses ORM Python-side defaults: supply every NOT NULL column
    # without a server_default, and let parcels.id (BigInteger identity)
    # autoincrement (CI catch 2026-07-07).
    await db.execute(
        text(
            "INSERT INTO zoning_districts (jurisdiction_id, zone_code, zone_class, "
            "source, human_reviewed, geom) "
            "VALUES (:jid, :c, CAST(:cl AS zone_class_enum), "
            "CAST('arcgis' AS zone_source_enum), false, ST_GeomFromText(:g, 4326))"
        ),
        {"jid": jid, "c": dist_code, "cl": dist_class, "g": _DISTRICT_POLY},
    )
    await db.execute(
        text(
            "INSERT INTO parcels (jurisdiction_id, apn, zoning_code, zoning_code_source, "
            "in_flood_zone, in_wetland, geom) "
            "VALUES (:jid, :apn, :zc, :src, false, false, ST_GeomFromText(:g, 4326))"
        ),
        {"jid": jid, "apn": "A1", "zc": parcel_code,
         "src": "parcel_attr", "g": _PARCEL_POLY},
    )
    await db.commit()  # backfill uses a separate raw connection — must be committed
    return jid


async def _parcel(db, jid):
    r = await db.execute(
        text(
            "SELECT zoning_code, zoning_code_source, zone_class::text AS zone_class "
            "FROM parcels WHERE jurisdiction_id = :jid"
        ),
        {"jid": jid},
    )
    return r.one()


async def _cleanup(db, jid):
    await db.execute(text("DELETE FROM parcels WHERE jurisdiction_id = :jid"), {"jid": jid})
    await db.execute(text("DELETE FROM zoning_districts WHERE jurisdiction_id = :jid"), {"jid": jid})
    await db.execute(text("DELETE FROM jurisdictions WHERE id = :jid"), {"jid": jid})
    await db.commit()


async def test_county_stale_attr_yields_to_muni_district(db_session):
    """Synthetic 'county attribute stale, municipal layer correct' → muni wins."""
    jid = await _setup(db_session, parcel_code="OLDCTY", dist_code="LI", dist_class="industrial")
    try:
        await backfill_parcel_zoning_from_districts(jid, db_session, district_beats_attr=True)
        p = await _parcel(db_session, jid)
        assert p.zoning_code == "LI"
        assert p.zoning_code_source == "district_spatial"
        assert p.zone_class == "industrial"  # class + code from one authority
    finally:
        await _cleanup(db_session, jid)


async def test_allentown_integer_code_yields_to_muni_district(db_session):
    """Allentown-style integer parcel code overridden by the real district code."""
    jid = await _setup(db_session, parcel_code="4", dist_code="C-1", dist_class="commercial")
    try:
        await backfill_parcel_zoning_from_districts(jid, db_session, district_beats_attr=True)
        p = await _parcel(db_session, jid)
        assert p.zoning_code == "C-1"
        assert p.zoning_code_source == "district_spatial"
    finally:
        await _cleanup(db_session, jid)


async def test_null_source_is_freely_overridable(db_session):
    """NULL zoning_code_source (pre-migration row — 0042 ships NO backfill) is
    LOWEST precedence: a district re-bind must override it. If NULL were
    treated as trusted 'parcel_attr', old county codes would freeze and the
    muni-beats-county precedence would be silently defeated (condition 1 of
    the 2026-07-06 stop+stamp approval)."""
    jid = await _setup(db_session, parcel_code="OLDCTY", dist_code="LI", dist_class="industrial")
    try:
        # simulate the pre-migration state: code present, provenance unknown
        await db_session.execute(
            text("UPDATE parcels SET zoning_code_source = NULL WHERE jurisdiction_id = :jid"),
            {"jid": jid},
        )
        await db_session.commit()
        await backfill_parcel_zoning_from_districts(jid, db_session, district_beats_attr=True)
        p = await _parcel(db_session, jid)
        assert p.zoning_code == "LI"
        assert p.zoning_code_source == "district_spatial"
    finally:
        await _cleanup(db_session, jid)


async def test_city_gis_keeps_authoritative_parcel_code(db_session):
    """city_gis (district_beats_attr=False): the parcel-layer code is kept —
    a district must NOT clobber it, and the NYC-style fast-skip holds."""
    jid = await _setup(db_session, parcel_code="R-1", dist_code="C-9", dist_class="commercial")
    try:
        await backfill_parcel_zoning_from_districts(jid, db_session, district_beats_attr=False)
        p = await _parcel(db_session, jid)
        assert p.zoning_code == "R-1"
        assert p.zoning_code_source == "parcel_attr"
    finally:
        await _cleanup(db_session, jid)
