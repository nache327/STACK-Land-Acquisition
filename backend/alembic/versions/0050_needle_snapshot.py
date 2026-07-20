"""needle_snapshot — precomputed wealth-gated needle metrics per jurisdiction

Phase 5: turns the product's one metric (currently CLI-only in verify_batch)
into a fast in-app read. The needle count is a heavy per-parcel matrix LATERAL
over the wealth ring, so it's precomputed nightly (precompute_needles.py) into
one current row per jurisdiction, not scanned live per request.

Tracks BOTH assets now that LGC is live: self-storage needles, LGC-effective
needles, the LGC-only incremental slice, and current on-needle CoStar deals for
each. Light CREATE TABLE — safe at Railway boot.

Revision ID: 0050
Revises: 0049
Create Date: 2026-07-18 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "needle_snapshot",
        sa.Column(
            "jurisdiction_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("jurisdiction_name", sa.Text(), nullable=False),
        sa.Column("state", sa.String(), nullable=True),
        sa.Column("storage_needles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lgc_needles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lgc_incremental", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_deals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lgc_deals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("needle_snapshot")
