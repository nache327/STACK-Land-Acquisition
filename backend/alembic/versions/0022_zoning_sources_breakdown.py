"""zoning_sources confidence breakdown + rejection feedback

Adds two columns to zoning_sources:
  - confidence_breakdown: structured per-component score deltas
    (e.g. {"name_match": +25, "wrong_state": -40}). Operators inspect
    this when triaging a candidate; complements the existing free-text
    `reasons` JSONB list.
  - rejected_reason: short text the operator records when rejecting
    a candidate ("wrong state", "false positive — different town", etc.).

Also adds an index on (validation_status, zoning_endpoint) so the
cross-jurisdiction deny-list lookup
  SELECT 1 FROM zoning_sources
   WHERE validation_status='rejected' AND zoning_endpoint=$1 LIMIT 1
runs fast even at 10k+ rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "zoning_sources",
        sa.Column("confidence_breakdown", JSONB, nullable=True),
    )
    op.add_column(
        "zoning_sources",
        sa.Column("rejected_reason", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_zoning_sources_status_endpoint",
        "zoning_sources",
        ["validation_status", "zoning_endpoint"],
    )


def downgrade() -> None:
    op.drop_index("ix_zoning_sources_status_endpoint", table_name="zoning_sources")
    op.drop_column("zoning_sources", "rejected_reason")
    op.drop_column("zoning_sources", "confidence_breakdown")
