"""Bridge missing 0008 revision present in production.

Revision ID: 0008b
Revises: 0008
Create Date: 2026-04-21 00:00:00.000000

Originally tagged "0008" alongside 0008_classification_source.py, which
made `alembic upgrade head` fail with "Multiple head revisions". Renumbered
to 0008b so the chain is strictly linear:

    0007 → 0008 (classification_source) → 0008b (bridge)
         → 0009 (classification_source_extend) → 0009b (repair_production_drift)
         → 0010 → 0011 → 0012 → 0013

The bridge body stays a no-op; production has been at this stamp for months.
"""
from typing import Sequence, Union


revision: str = "0008b"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Production stamped this revision before the repo carried a file. This
    # bridge keeps the Alembic graph coherent without touching schema.
    pass


def downgrade() -> None:
    pass
