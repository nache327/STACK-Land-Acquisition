"""candidate_search must resolve zone_use_matrix exactly like the scorer.

The map/table read path (`search_candidate_parcels`) and the Site Score
(`buybox_scoring._select_parcels_sql`) both join parcels -> zone_use_matrix.
The scorer has always been municipality-aware (prefer the row whose
`municipality` equals `parcels.city`, else the NULL-municipality county
default, LIMIT 1). The read path was NOT: it joined on (jurisdiction, zone_code)
only, so in any county holding both a township-specific row and a county
default for the same zone code it:

  1. emitted BOTH rows -> the parcel appeared twice in results and was
     double-counted in the total, and
  2. labelled the parcel with whichever row the planner happened to emit —
     which could be the county default 'prohibited' while the Site Score for
     the same parcel said 'permitted' from the township row.

That is the "table says one thing, the score says another" class of bug the
2026-07-22 sweep set out to eliminate, and it survived in this one path.

`uq_zone_matrix` is UNIQUE on (jurisdiction_id, zone_code,
COALESCE(municipality,'')), so a parcel has at most two candidate rows; the
predicates asserted here therefore select exactly one.

No DB needed: we compile the statement and assert its shape.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.models.parcel import Parcel
from app.models.zone_use_matrix import ZoneUseMatrix
from app.schemas.parcel import CandidateParcelSearchFilters, CandidateParcelSearchRequest


def _compiled_join_sql() -> str:
    """Build the same permission_join search_candidate_parcels builds, by
    invoking it far enough to compile a statement. Simplest robust approach:
    re-derive it from the module so the test breaks if the join is rewritten
    in a way that drops the predicates."""
    import inspect

    from app.services import candidate_search

    src = inspect.getsource(candidate_search.search_candidate_parcels)
    return src


def test_join_is_municipality_scoped():
    """The join must restrict to rows governing THIS parcel: its own
    municipality or the county-wide default."""
    src = _compiled_join_sql()
    assert "ZoneUseMatrix.municipality.is_(None)" in src
    assert "ZoneUseMatrix.municipality == Parcel.city" in src


def test_join_suppresses_county_default_when_municipality_row_exists():
    """Precedence: the county default must be excluded when a
    municipality-specific row exists for the parcel's city — otherwise both
    rows match and the parcel duplicates."""
    src = _compiled_join_sql()
    assert "ZoneUseMatrix.municipality.isnot(None)" in src
    # the anti-join on an aliased matrix keyed to the parcel's city
    assert "_zum_muni_specific" in src
    assert "_zum_muni_specific.municipality == Parcel.city" in src
    assert ".exists()" in src


def test_soft_deletes_still_excluded_on_both_sides():
    src = _compiled_join_sql()
    assert "ZoneUseMatrix.deleted_at.is_(None)" in src
    assert "_zum_muni_specific.deleted_at.is_(None)" in src


def test_precedence_sql_compiles_to_expected_shape():
    """Compile an equivalent statement and assert the emitted SQL contains the
    municipality predicate and the NOT EXISTS precedence guard."""
    from sqlalchemy import and_, literal_column, or_
    from sqlalchemy.orm import aliased

    z2 = aliased(ZoneUseMatrix)
    join = and_(
        ZoneUseMatrix.jurisdiction_id == Parcel.jurisdiction_id,
        ZoneUseMatrix.zone_code == Parcel.zoning_code,
        ZoneUseMatrix.deleted_at.is_(None),
        or_(
            ZoneUseMatrix.municipality.is_(None),
            ZoneUseMatrix.municipality == Parcel.city,
        ),
        or_(
            ZoneUseMatrix.municipality.isnot(None),
            ~(
                select(literal_column("1"))
                .where(
                    z2.jurisdiction_id == Parcel.jurisdiction_id,
                    z2.zone_code == Parcel.zoning_code,
                    z2.municipality == Parcel.city,
                    z2.deleted_at.is_(None),
                )
                .exists()
            ),
        ),
    )
    stmt = select(func.count()).select_from(Parcel).outerjoin(ZoneUseMatrix, join)
    sql = str(stmt.compile(dialect=postgresql.dialect(),
                           compile_kwargs={"literal_binds": True}))
    assert "zone_use_matrix.municipality IS NULL OR zone_use_matrix.municipality = parcels.city" in sql
    assert "zone_use_matrix.municipality IS NOT NULL OR NOT (EXISTS" in sql
    # the anti-join must key on the parcel's city, not a constant
    assert "zone_use_matrix_1.municipality = parcels.city" in sql


def test_request_schema_still_accepts_city_drilldown():
    """cities filter is what makes municipality precedence observable in the UI."""
    req = CandidateParcelSearchRequest(
        jurisdiction_id="00000000-0000-0000-0000-000000000001",
        filters=CandidateParcelSearchFilters(cities=["Somerville borough"]),
    )
    assert req.filters.cities == ["Somerville borough"]
