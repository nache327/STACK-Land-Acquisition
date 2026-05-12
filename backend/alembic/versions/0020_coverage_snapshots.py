"""coverage_snapshots: cached per-jurisdiction coverage rollup

Today `/api/debug/geom-info` times out on every non-empty jurisdiction
because COUNT(*) JOINs across `parcels` and `zoning_overlays` don't scale
past ~1M rows. There's no way to see a dashboard view of operational
coverage without running the audit CLI by hand against prod.

This migration creates a `coverage_snapshots` table seeded by the existing
`backend/scripts/audit_zoning_coverage.py` machinery. A scheduled refresh
(POST /api/admin/coverage/refresh) writes one row per jurisdiction per
snapshot; the dashboard reads the latest via DISTINCT ON. Snapshots are
small (~75 jurisdictions × snapshot rate), so history is cheap to keep.

Mirrors the `JurisdictionAudit` dataclass field-for-field except that
array fields (blocking_gaps, unmatched_zone_samples) are flattened into
jsonb.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coverage_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("jurisdiction_id", UUID(as_uuid=True),
                  sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jurisdiction_name", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("county", sa.Text, nullable=True),
        sa.Column("coverage_level", sa.Text, nullable=True),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_bbox", sa.Boolean, nullable=True),

        # Parcel counts
        sa.Column("parcel_count", sa.Integer, nullable=True),
        sa.Column("parcel_with_geom_count", sa.Integer, nullable=True),
        sa.Column("parcel_with_zoning_code_count", sa.Integer, nullable=True),
        sa.Column("parcel_with_zone_class_count", sa.Integer, nullable=True),
        sa.Column("parcel_distinct_zone_count", sa.Integer, nullable=True),
        sa.Column("vacant_parcel_count", sa.Integer, nullable=True),
        sa.Column("flood_parcel_count", sa.Integer, nullable=True),
        sa.Column("wetland_parcel_count", sa.Integer, nullable=True),

        # Districts + matrix
        sa.Column("zoning_district_count", sa.Integer, nullable=True),
        sa.Column("zoning_district_with_geom_count", sa.Integer, nullable=True),
        sa.Column("matrix_zone_count", sa.Integer, nullable=True),
        sa.Column("matrix_self_storage_permitted_count", sa.Integer, nullable=True),
        sa.Column("matrix_self_storage_conditional_count", sa.Integer, nullable=True),
        sa.Column("matrix_self_storage_prohibited_count", sa.Integer, nullable=True),
        sa.Column("matrix_self_storage_unclear_count", sa.Integer, nullable=True),
        sa.Column("matrix_human_reviewed_count", sa.Integer, nullable=True),

        # Self-storage cross-joins
        sa.Column("parcels_with_zoning_code", sa.Integer, nullable=True),
        sa.Column("parcels_with_matrix_match", sa.Integer, nullable=True),
        sa.Column("parcels_self_storage_permitted", sa.Integer, nullable=True),
        sa.Column("parcels_self_storage_conditional", sa.Integer, nullable=True),
        sa.Column("parcels_self_storage_prohibited", sa.Integer, nullable=True),
        sa.Column("parcels_self_storage_unclear", sa.Integer, nullable=True),
        sa.Column("parcel_distinct_zone_with_matrix_match_count", sa.Integer, nullable=True),

        # Derived ratios
        sa.Column("parcel_geom_coverage_pct", sa.Float, nullable=True),
        sa.Column("parcel_zoning_code_coverage_pct", sa.Float, nullable=True),
        sa.Column("parcel_zone_class_coverage_pct", sa.Float, nullable=True),
        sa.Column("zoning_polygon_coverage_flag", sa.Boolean, nullable=True),
        sa.Column("matrix_zone_match_pct", sa.Float, nullable=True),
        sa.Column("matrix_distinct_zone_match_pct", sa.Float, nullable=True),
        sa.Column("self_storage_classified_parcel_pct", sa.Float, nullable=True),
        sa.Column("self_storage_positive_parcel_pct", sa.Float, nullable=True),

        # Verdict + diagnostics
        sa.Column("operational_readiness", sa.Text, nullable=True),
        sa.Column("blocking_gaps", JSONB, nullable=True),
        sa.Column("unmatched_zone_samples", JSONB, nullable=True),

        # Snapshot metadata
        sa.Column("source", sa.Text, nullable=True),  # 'scheduled' | 'manual'
    )
    op.create_index(
        "ix_coverage_snapshots_jurisdiction_captured",
        "coverage_snapshots",
        ["jurisdiction_id", sa.text("captured_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_coverage_snapshots_jurisdiction_captured", table_name="coverage_snapshots")
    op.drop_table("coverage_snapshots")
