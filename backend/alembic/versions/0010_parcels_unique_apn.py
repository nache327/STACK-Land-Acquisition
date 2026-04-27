"""Add unique constraint on (jurisdiction_id, apn) to prevent duplicate parcel ingestion

Revision ID: 0010
Revises: 0009m
Create Date: 2026-04-24 00:00:00.000000

Without this constraint, every pipeline re-run stacks a fresh copy of every
parcel on top of the existing ones (same APN, different UUID primary key).
The DISTINCT ON dedup must run before this migration if duplicates exist.
"""
from alembic import op


revision = "0010"
down_revision = "0009m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Duplicates were removed manually before this migration ran.
    op.create_unique_constraint(
        "uq_parcels_jurisdiction_apn",
        "parcels",
        ["jurisdiction_id", "apn"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_parcels_jurisdiction_apn", "parcels")
