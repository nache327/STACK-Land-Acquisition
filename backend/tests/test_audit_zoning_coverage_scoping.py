from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.append(str(SCRIPTS_DIR))

import audit_zoning_coverage as az  # noqa: E402


def _schema() -> az.SchemaProfile:
    return az.SchemaProfile(
        has_parcels_table=True,
        has_zone_use_matrix_table=True,
        has_zoning_districts_table=True,
        has_overlays_table=False,
        has_parcel_zone_class_column=True,
        has_parcel_zone_binding_method_column=True,
        has_jurisdiction_coverage_level_column=True,
        has_jurisdiction_bbox_column=True,
    )


def test_scoped_audit_sql_limits_heavy_ctes_to_target_jurisdictions():
    sql = str(az._build_audit_sql(_schema()))

    assert "WITH target_jurisdictions AS" in sql
    assert "CAST(:jurisdiction_id AS uuid)" in sql
    assert "FROM parcels p\n            JOIN target_jurisdictions tj" in sql
    assert "FROM zoning_districts zd\n            JOIN target_jurisdictions tj" in sql
    assert "FROM zone_use_matrix zum\n            JOIN target_jurisdictions tj" in sql
    assert "FROM jurisdictions j\n        JOIN target_jurisdictions tj" in sql
