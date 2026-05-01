"""Add 'ingesting_parcels' to job_status_enum

Revision ID: 0011b
Revises: 0011
Create Date: 2026-04-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0011b"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'ingesting_parcels' "
        "AFTER 'downloading_parcels'"
    )


def downgrade() -> None:
    pass
