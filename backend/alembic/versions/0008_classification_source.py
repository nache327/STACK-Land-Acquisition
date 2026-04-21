"""Add classification_source column to zone_use_matrix

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-21 00:00:00.000000

Tracks whether each row was produced by the LLM ordinance parser,
a rule-based fallback classifier, or a human analyst override.
This enables bulk re-classification queries (WHERE classification_source = 'rule')
and prevents rule-based data from silently overwriting verified classifications.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type first
    op.execute(
        "CREATE TYPE classification_source_enum AS ENUM "
        "('llm', 'rule', 'human', 'unclear')"
    )
    # Add column — existing rows get 'unclear' (origin unknown / legacy)
    op.add_column(
        "zone_use_matrix",
        sa.Column(
            "classification_source",
            sa.Enum("llm", "rule", "human", "unclear", name="classification_source_enum"),
            nullable=False,
            server_default="unclear",
        ),
    )
    # Rows inserted by rule-based scripts have confidence <= 0.75 and notes matching the pattern
    op.execute(
        """
        UPDATE zone_use_matrix
        SET classification_source = 'rule'
        WHERE confidence <= 0.75
          AND (
            notes ILIKE '%rule-based%'
            OR notes ILIKE '%Rule-based%'
            OR notes ILIKE '%conservative default%'
            OR notes ILIKE '%initial classification%'
          )
        """
    )
    # Rows where human_reviewed = true are human-sourced
    op.execute(
        """
        UPDATE zone_use_matrix
        SET classification_source = 'human'
        WHERE human_reviewed = true
        """
    )
    # Higher-confidence rows without rule-based notes are LLM-parsed
    op.execute(
        """
        UPDATE zone_use_matrix
        SET classification_source = 'llm'
        WHERE classification_source = 'unclear'
          AND confidence >= 0.85
        """
    )


def downgrade() -> None:
    op.drop_column("zone_use_matrix", "classification_source")
    op.execute("DROP TYPE IF EXISTS classification_source_enum")
