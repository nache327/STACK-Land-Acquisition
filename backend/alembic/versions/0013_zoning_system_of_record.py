"""Add zoning system-of-record tables

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-28 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'pending_zoning'")

    op.add_column("parcels", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("parcels", sa.Column("state", sa.Text(), nullable=True))
    op.add_column("parcels", sa.Column("lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("parcels", sa.Column("lng", sa.Numeric(10, 7), nullable=True))
    op.create_index("ix_parcels_city", "parcels", ["city"])

    op.create_table(
        "zoning_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("zone_code", sa.Text(), nullable=False),
        sa.Column("density", sa.Float(), nullable=True),
        sa.Column("max_units", sa.Integer(), nullable=True),
        sa.Column("min_lot_size", sa.Float(), nullable=True),
        sa.Column("setbacks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("height_limit", sa.Float(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zoning_rules_city", "zoning_rules", ["city"])
    op.create_index("ix_zoning_rules_zone_code", "zoning_rules", ["zone_code"])
    op.create_index(
        "uq_zoning_rules_city_zone_code",
        "zoning_rules",
        ["city", "zone_code"],
        unique=True,
    )

    op.create_table(
        "zoning_overlays",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_id", sa.BigInteger(), nullable=False),
        sa.Column("zoning_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zoning_rule_id"], ["zoning_rules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zoning_overlays_parcel_id", "zoning_overlays", ["parcel_id"])

    op.create_table(
        "enrichment_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_id", sa.BigInteger(), nullable=False),
        sa.Column("zoning_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("slope", sa.Float(), nullable=True),
        sa.Column("flood_zone", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_enrichment_cache_parcel_id", "enrichment_cache", ["parcel_id"])
    op.create_index(
        "uq_enrichment_cache_parcel_id",
        "enrichment_cache",
        ["parcel_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_enrichment_cache_parcel_id", table_name="enrichment_cache")
    op.drop_index("ix_enrichment_cache_parcel_id", table_name="enrichment_cache")
    op.drop_table("enrichment_cache")
    op.drop_index("ix_zoning_overlays_parcel_id", table_name="zoning_overlays")
    op.drop_table("zoning_overlays")
    op.drop_index("uq_zoning_rules_city_zone_code", table_name="zoning_rules")
    op.drop_index("ix_zoning_rules_zone_code", table_name="zoning_rules")
    op.drop_index("ix_zoning_rules_city", table_name="zoning_rules")
    op.drop_table("zoning_rules")
    op.drop_index("ix_parcels_city", table_name="parcels")
    op.drop_column("parcels", "lng")
    op.drop_column("parcels", "lat")
    op.drop_column("parcels", "state")
    op.drop_column("parcels", "city")
