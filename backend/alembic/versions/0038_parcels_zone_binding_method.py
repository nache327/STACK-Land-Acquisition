"""Add zone_binding_method column to parcels.

Why:
    spatial_backfill.backfill_parcel_zoning_from_districts now supports an
    optional nearest-district fallback (ST_DWithin) for parcels that no
    zoning district fully contains. The audit and downstream consumers need
    to distinguish "centroid contained inside a district" from "snapped to
    the nearest district within N meters" so operators can read the
    inferred-vs-contained split before promoting a jurisdiction to
    operational status.

    Values:
        NULL          — never bound by this service (or pre-migration row)
        'contained'   — ST_Within(centroid, district) matched
        'nearest_<N>m' — ST_DWithin fallback matched within N meters
                        (e.g. 'nearest_50m')

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-04 18:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parcels",
        sa.Column("zone_binding_method", sa.String(length=32), nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcels_jurisdiction_binding_method "
        "ON parcels (jurisdiction_id, zone_binding_method)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcels_jurisdiction_binding_method")
    op.drop_column("parcels", "zone_binding_method")
