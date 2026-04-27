"""Merge duplicate 0009 heads into a single revision.

Revision ID: 0009m
Revises: 0009, 0009a
Create Date: 2026-04-27

Both 0009 branches (repair_production_schema_drift and classification_source_extend)
ran independently. This merge node makes 0010 have a single unambiguous parent.
"""
from typing import Sequence, Union

revision: str = "0009m"
down_revision: Union[str, Sequence[str], None] = ("0009", "0009a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
