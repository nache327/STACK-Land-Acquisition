"""deal_dispositions — ParcelLogic's local mirror of dashboard board dispositions

Phase 2 of the LGC/deal-flow roadmap (docs/AUDIT_2026_07_17.md): closes the
one-way-sync gap. dashboard_push refreshes this table from the dashboard's
deal_prospect board each sync; the digest + listing alerts then suppress deals
the owner already closed out (passed / dead / under_contract) so they stop
re-surfacing.

One row per parcel. Light CREATE TABLE — safe at Railway boot.

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-18 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deal_dispositions",
        sa.Column(
            "parcel_id",
            sa.BigInteger(),
            sa.ForeignKey("parcels.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Partial index on the closed-out statuses the digest/alerts filter against,
    # so the NOT EXISTS suppression stays cheap as the board grows.
    op.create_index(
        "ix_deal_dispositions_closed",
        "deal_dispositions",
        ["parcel_id"],
        postgresql_where=sa.text(
            "status IN ('passed', 'dead', 'under_contract')"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_deal_dispositions_closed", table_name="deal_dispositions")
    op.drop_table("deal_dispositions")
