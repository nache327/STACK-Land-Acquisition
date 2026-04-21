"""Add parcels.zone_class denormalized column

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-20 00:00:01.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parcels",
        sa.Column(
            "zone_class",
            postgresql.ENUM(
                "residential",
                "commercial",
                "industrial",
                "mixed_use",
                "agricultural",
                "open_space",
                "special",
                "overlay",
                "unknown",
                name="zone_class_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_parcels_jurisdiction_zone_class",
        "parcels",
        ["jurisdiction_id", "zone_class"],
    )


def downgrade() -> None:
    op.drop_index("ix_parcels_jurisdiction_zone_class", table_name="parcels")
    op.drop_column("parcels", "zone_class")
