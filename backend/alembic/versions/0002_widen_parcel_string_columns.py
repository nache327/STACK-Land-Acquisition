"""Widen parcel zoning_code and land_use_code columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-16 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "parcels",
        "zoning_code",
        existing_type=sa.String(50),
        type_=sa.String(100),
        existing_nullable=True,
    )
    op.alter_column(
        "parcels",
        "land_use_code",
        existing_type=sa.String(100),
        type_=sa.String(512),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "parcels",
        "land_use_code",
        existing_type=sa.String(512),
        type_=sa.String(100),
        existing_nullable=True,
    )
    op.alter_column(
        "parcels",
        "zoning_code",
        existing_type=sa.String(100),
        type_=sa.String(50),
        existing_nullable=True,
    )
