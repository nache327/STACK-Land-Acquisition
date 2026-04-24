"""Bridge missing 0008 revision present in production.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-21 00:00:00.000000
"""
from typing import Sequence, Union


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Production was already stamped to 0008, but the repo never carried the
    # matching file. This bridge restores a coherent Alembic graph so later
    # repair migrations can run safely against both local and production DBs.
    pass


def downgrade() -> None:
    pass
