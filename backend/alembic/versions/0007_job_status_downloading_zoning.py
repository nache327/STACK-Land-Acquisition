"""Add 'downloading_zoning' to job_status_enum

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-20 00:00:04.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE … ADD VALUE must run outside a transaction block in older
    # Postgres versions; Alembic wraps the migration in one by default, but
    # Postgres 12+ accepts this inside a transaction provided the value
    # isn't used in the same transaction.
    op.execute(
        "ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'downloading_zoning' "
        "AFTER 'downloading_parcels'"
    )


def downgrade() -> None:
    # Postgres does not support removing a single enum value. A true downgrade
    # would require recreating the type and re-casting all columns; we
    # intentionally no-op here.
    pass
