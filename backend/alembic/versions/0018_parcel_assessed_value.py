"""Add parcels.assessed_value + is_residential and homes_over_{1,2,5}m on
parcel_ring_metrics.

Backs the new "Wealth density" buy-box dimension: count of residential
parcels with total assessed value >= $1M / $2M / $5M inside a drive-time
ring. The two parcel columns are populated by ingest + backfill via
``app.services.parcel_value_mapper``; the three ring-metric columns are
populated lazily by ``POST /api/parcels/value-density`` and cached.

Additive only — every column is nullable. Safe to run with the worker live.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-11 14:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── parcels ───────────────────────────────────────────────────────────
    op.add_column(
        "parcels",
        sa.Column("assessed_value", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "parcels",
        sa.Column("is_residential", sa.Boolean(), nullable=True),
    )
    # Partial index — supports the density endpoint's hot path. Only rows
    # with both flags set contribute, so a partial index is much smaller
    # than a full one and the planner uses it whenever the WHERE clause
    # matches the index predicate.
    op.create_index(
        "ix_parcels_residential_value",
        "parcels",
        ["jurisdiction_id", "assessed_value"],
        postgresql_where=sa.text(
            "is_residential IS TRUE AND assessed_value IS NOT NULL"
        ),
    )

    # ── parcel_ring_metrics ───────────────────────────────────────────────
    op.add_column(
        "parcel_ring_metrics",
        sa.Column("homes_over_1m", sa.Integer(), nullable=True),
    )
    op.add_column(
        "parcel_ring_metrics",
        sa.Column("homes_over_2m", sa.Integer(), nullable=True),
    )
    op.add_column(
        "parcel_ring_metrics",
        sa.Column("homes_over_5m", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("parcel_ring_metrics", "homes_over_5m")
    op.drop_column("parcel_ring_metrics", "homes_over_2m")
    op.drop_column("parcel_ring_metrics", "homes_over_1m")
    op.drop_index("ix_parcels_residential_value", table_name="parcels")
    op.drop_column("parcels", "is_residential")
    op.drop_column("parcels", "assessed_value")
