"""
Coverage-inflation fix (audit "D2" 2.4): refresh_jurisdiction_coverage_level
must count only REAL verdicts, not placeholder stubs (inherited_pending /
unclear-bootstrap / op5_factory_catchall) or soft-deleted rows.

SAFETY: commits + deletes; self-skips unless DATABASE_URL is a local/CI test DB.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from app.models.jurisdiction import CoverageLevel, Jurisdiction
from app.services.spatial_backfill import refresh_jurisdiction_coverage_level

_DBURL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    (not _DBURL) or ("supabase" in _DBURL) or ("pooler" in _DBURL),
    reason="coverage DB test runs only against a local/CI test DB, never prod",
)

_POLY = "POLYGON((0 0,0 1,1 1,1 0,0 0))"


async def _mk(db, jid, *, source):
    await db.execute(
        text(
            "INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, self_storage, "
            "classification_source) VALUES (:jid, :zc, 'permitted', "
            "CAST(:src AS classification_source_enum))"
        ),
        {"jid": jid, "zc": f"Z-{source}", "src": source},
    )


async def test_stub_only_matrix_is_not_full_coverage(db_session):
    jid = uuid.uuid4()
    j = Jurisdiction(id=jid, name=f"Cov {jid}", state="PA", bbox=[0, 0, 1, 1])
    db_session.add(j)
    await db_session.flush()
    # parcels (structure known) + a zoning district → parcel/zoning counts > 0
    await db_session.execute(
        text(
            "INSERT INTO parcels (jurisdiction_id, apn, has_structure, geom) "
            "VALUES (:jid, 'A1', true, ST_GeomFromText(:g,4326))"
        ),
        {"jid": jid, "g": _POLY},
    )
    await db_session.execute(
        text(
            "INSERT INTO zoning_districts (jurisdiction_id, zone_code, geom) "
            "VALUES (:jid, 'Z1', ST_GeomFromText(:g,4326))"
        ),
        {"jid": jid, "g": _POLY},
    )
    # ONLY stub matrix rows — must NOT count as coverage
    for src in ("inherited_pending", "unclear", "op5_factory_catchall"):
        await _mk(db_session, jid, source=src)
    await db_session.commit()
    try:
        level = await refresh_jurisdiction_coverage_level(j, db_session)
        # matrix_count(real)=0 → cannot be `full`; parcels+zoning present → partial
        assert level != CoverageLevel.full
        assert level == CoverageLevel.partial

        # Add ONE grounded verdict → real matrix coverage → full
        await _mk(db_session, jid, source="llm")
        await db_session.commit()
        level2 = await refresh_jurisdiction_coverage_level(j, db_session)
        assert level2 == CoverageLevel.full
    finally:
        await db_session.execute(text("DELETE FROM parcels WHERE jurisdiction_id=:j"), {"j": jid})
        await db_session.execute(text("DELETE FROM zoning_districts WHERE jurisdiction_id=:j"), {"j": jid})
        await db_session.execute(text("DELETE FROM zone_use_matrix WHERE jurisdiction_id=:j"), {"j": jid})
        await db_session.execute(text("DELETE FROM jurisdictions WHERE id=:j"), {"j": jid})
        await db_session.commit()
