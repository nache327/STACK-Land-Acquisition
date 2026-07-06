"""
Pure (no-DB) tests for the zoning_code provenance + precedence logic (audit "D2"):
  - the force-aware COPY→parcels merge builder
  - the binding-needed precedence predicate (city_gis vs county_gis vs force)

These lock the decision policy; the actual "resolves to muni" behavior against
PostGIS lives in test_zoning_precedence_db.py (CI-only).
"""
from __future__ import annotations

from app.services.ingestion import _STAGE_COLUMNS, _build_merge_sql
from app.services.spatial_backfill import _binding_needed_predicate


# ── merge builder ────────────────────────────────────────────────────────────

def test_merge_default_coalesces_zoning_code():
    sql = _build_merge_sql(force=False)
    # non-force keeps the existing code when the ingest brings none
    assert "COALESCE(EXCLUDED.zoning_code, parcels.zoning_code)" in sql
    # code + class + source move together (never split authorities)
    assert "zoning_code_source = CASE WHEN EXCLUDED.zoning_code IS NOT NULL" in sql
    assert "zone_class = CASE WHEN EXCLUDED.zoning_code IS NOT NULL" in sql


def test_merge_force_overwrites_unconditionally():
    sql = _build_merge_sql(force=True)
    # force clears a stale code even when the new value is NULL
    assert "zoning_code = EXCLUDED.zoning_code," in sql
    assert "COALESCE(EXCLUDED.zoning_code" not in sql
    assert "zoning_code_source = EXCLUDED.zoning_code_source," in sql


def test_merge_inserts_provenance_column():
    sql = _build_merge_sql(force=False)
    assert "zoning_code_source" in sql
    assert "s.zoning_code_source" in sql
    assert "zoning_code_source" in _STAGE_COLUMNS


# ── precedence predicate ─────────────────────────────────────────────────────

def test_city_gis_only_rebinds_unzoned():
    """Default (city_gis): the parcel-layer code is authoritative — only truly
    unzoned parcels get bound (this is what keeps the NYC fast-skip)."""
    assert _binding_needed_predicate(False, False) == "(zoning_code IS NULL OR zoning_code = '')"


def test_county_gis_rebinds_non_district_sources():
    """county_gis: a municipal district overrides a stale parcel_attr code, so
    anything not yet 'district_spatial' still needs binding."""
    pred = _binding_needed_predicate(False, True)
    assert "district_spatial" in pred
    assert "IS DISTINCT FROM" in pred
    assert "zoning_code IS NULL" in pred


def test_force_rebinds_everything():
    assert _binding_needed_predicate(True, False) == "TRUE"
    assert _binding_needed_predicate(True, True) == "TRUE"


def test_alias_prefixes_columns_for_subquery():
    pred = _binding_needed_predicate(False, True, alias="p")
    assert pred.startswith("(p.zoning_code")
    assert "p.zoning_code_source" in pred
    # no unqualified column leaks through
    assert " zoning_code" not in pred.replace("p.zoning_code", "")


# ── NULL zoning_code_source semantics (migration 0042 has NO backfill) ────────
# Pre-migration rows keep a NULL source. NULL MUST be lowest-precedence /
# freely overridable by a district_spatial re-bind. If any code path treats
# NULL as trusted 'parcel_attr', old county codes freeze and D2 is silently
# defeated. The behavioral counterpart runs against PostGIS in
# test_zoning_precedence_db.py::test_null_source_is_freely_overridable.

def test_null_source_predicate_is_null_safe():
    """The county-mode predicate must use IS DISTINCT FROM (NULL-safe): a plain
    `<> 'district_spatial'` evaluates to NULL for NULL-source rows, silently
    excluding them from rebinding — the exact freeze condition 1 forbids."""
    pred = _binding_needed_predicate(False, True)
    assert "zoning_code_source IS DISTINCT FROM 'district_spatial'" in pred
    # never the NULL-poisoned comparison forms
    assert "zoning_code_source <>" not in pred
    assert "zoning_code_source !=" not in pred
    assert "zoning_code_source = " not in pred


def test_merge_never_invents_parcel_attr_for_null_codes():
    """Non-force merge: when the incoming ingest row has NO zoning code, the
    existing zoning_code_source is preserved AS IS (including NULL) — never
    promoted to 'parcel_attr'."""
    sql = _build_merge_sql(force=False)
    assert "ELSE parcels.zoning_code_source END" in sql
    # source is only ever set from the staged row, gated on a real incoming code
    assert "THEN EXCLUDED.zoning_code_source" in sql
