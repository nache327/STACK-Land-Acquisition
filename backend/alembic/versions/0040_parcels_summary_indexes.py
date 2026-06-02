"""Add covering indexes for the dashboard zone/zone-class/feature-flag summaries.

Why:
    On jurisdiction-entry the dashboard fires GROUP BY queries scoped to one
    jurisdiction_id:
      - /parcels/zone-summary       -> GROUP BY zoning_code
      - /parcels/zone-class-summary -> GROUP BY zone_class
    and a feature-flags EXISTS check on assessed_value. With only the
    (jurisdiction_id, city) composite from 0037, the zone/zone-class
    summaries still sequential-scan + hash-aggregate on county-sized
    jurisdictions (SLCo: 397k parcels), ~100-500ms each. Composite indexes
    on (jurisdiction_id, zoning_code) and (jurisdiction_id, zone_class) let
    the planner do index-only aggregates (~10-40ms). The partial index makes
    the wealth-density availability check an index-only existence probe.

Note for prod:
    On a hot DB run /api/_admin/optimize-parcels first — it creates these same
    indexes CONCURRENTLY and ANALYZEs (no write lock). This migration uses a
    regular CREATE INDEX (briefer lock, fine for fresh setups). Both are
    idempotent (IF NOT EXISTS) so re-running either after the other is a no-op.

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-04 20:00:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcels_jur_zoning_code "
        "ON parcels (jurisdiction_id, zoning_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcels_jur_zone_class "
        "ON parcels (jurisdiction_id, zone_class)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcels_jur_assessed "
        "ON parcels (jurisdiction_id) WHERE assessed_value IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcels_jur_zoning_code")
    op.execute("DROP INDEX IF EXISTS ix_parcels_jur_zone_class")
    op.execute("DROP INDEX IF EXISTS ix_parcels_jur_assessed")
