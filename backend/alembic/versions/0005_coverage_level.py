"""Add jurisdictions.coverage_level and jurisdictions.bbox

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-20 00:00:02.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COVERAGE_LEVEL_VALUES = ("full", "zoning_only", "parcels_only", "partial")


def upgrade() -> None:
    coverage_enum = postgresql.ENUM(
        *COVERAGE_LEVEL_VALUES, name="coverage_level_enum"
    )
    coverage_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "jurisdictions",
        sa.Column(
            "coverage_level",
            postgresql.ENUM(
                *COVERAGE_LEVEL_VALUES,
                name="coverage_level_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    # [minLng, minLat, maxLng, maxLat] in EPSG:4326 — used for frontend map-fit
    op.add_column(
        "jurisdictions",
        sa.Column("bbox", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jurisdictions", "bbox")
    op.drop_column("jurisdictions", "coverage_level")
    op.execute("DROP TYPE IF EXISTS coverage_level_enum")
