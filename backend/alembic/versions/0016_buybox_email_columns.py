"""Add daily-email columns to buybox_filters + notified_at to parcel_buybox_scores.

Powers the daily-digest worker. Additive only.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-08 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "buybox_filters",
        sa.Column(
            "daily_email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "buybox_filters",
        sa.Column(
            "daily_email_top_n",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("10"),
        ),
    )
    op.add_column(
        "buybox_filters",
        sa.Column(
            "last_email_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "parcel_buybox_scores",
        sa.Column(
            "notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Hot path for the worker: find unnotified rows for a given filter,
    # ordered by score desc.
    op.create_index(
        "ix_pbs_filter_unnotified",
        "parcel_buybox_scores",
        ["buybox_filter_id", sa.text("score DESC")],
        postgresql_where=sa.text("notified_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_pbs_filter_unnotified", table_name="parcel_buybox_scores")
    op.drop_column("parcel_buybox_scores", "notified_at")
    op.drop_column("buybox_filters", "last_email_sent_at")
    op.drop_column("buybox_filters", "daily_email_top_n")
    op.drop_column("buybox_filters", "daily_email_enabled")
