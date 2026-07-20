"""ops_cron_heartbeat — one row per watchdog cron tick, for liveness

The ops cron (backend/railway-cron.toml) runs the watchdog + digest every
10 min as restartPolicyType=NEVER one-shots. There is no external health
signal, so "is the cron actually firing?" was only answerable by reading
Railway logs (which we can't do programmatically) or by inferring from
side effects that are themselves gated (digest sends need hour==12 + email
enabled; the board push needs PORTFOLIO_DASHBOARD_DATABASE_URL set on the
cron service). That ambiguity is exactly what left a 19-day digest silence
unexplained.

This table gets one unconditional INSERT at the end of every watchdog tick
(see queued_job_watchdog._write_heartbeat), independent of the hour gate,
email flags, and dashboard DSN. So:
  * cron alive?          -> rows in the last ~15 min
  * fired at 12:00 UTC?  -> a row with ran_at in the 12:00 hour
  * what happened?       -> the per-tick watchdog/refresh/digest exit codes

Light CREATE TABLE — safe at Railway boot.

Revision ID: 0052
Revises: 0051
Create Date: 2026-07-20 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ops_cron_heartbeat",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("watchdog_code", sa.Integer, nullable=True),
        sa.Column("refresh_code", sa.Integer, nullable=True),
        sa.Column("digest_code", sa.Integer, nullable=True),
        sa.Column("host", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_ops_cron_heartbeat_ran_at",
        "ops_cron_heartbeat",
        [sa.text("ran_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_ops_cron_heartbeat_ran_at", table_name="ops_cron_heartbeat")
    op.drop_table("ops_cron_heartbeat")
