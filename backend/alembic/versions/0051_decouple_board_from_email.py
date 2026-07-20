"""decouple board-sync from email — dashboardEnabled flag + silence the inbox

Board-sync was accidentally coupled to the email flag: dashboard_push selected
filters via ``_eligible_filters`` (gated on ``daily_email_enabled``), so turning
off a digest would silently darken the Deal Pipeline board. This migration makes
them independent toggles:

  1. Seed ``filter_json.dashboardEnabled = true`` on every filter that currently
     feeds the board (i.e. currently email-enabled) — PRESERVES the exact board
     set (Hot deals storage + LGC Hot deals) so nothing on the board changes.
  2. Turn OFF ``daily_email_enabled`` on those filters so the inbox goes quiet.

After this, ``dashboard_push._dashboard_filters`` selects on ``dashboardEnabled``
(independent of email), so the board keeps populating with email disabled.

Data-only (no schema change). Idempotent given the current prod state; the
seed reads the pre-silence email flags, so the two statements are ordered.

Revision ID: 0051
Revises: 0050
Create Date: 2026-07-20 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Capture the CURRENT board set (email-enabled filters) into the new
    #    board toggle BEFORE silencing email — preserves the board exactly.
    op.execute(
        """
        UPDATE buybox_filters
           SET filter_json = filter_json || '{"dashboardEnabled": true}'::jsonb
         WHERE daily_email_enabled = true
        """
    )
    # 2. Silence the inbox. The board is now driven by dashboardEnabled, so this
    #    no longer darkens it.
    op.execute("UPDATE buybox_filters SET daily_email_enabled = false")


def downgrade() -> None:
    # Restore the pre-migration coupling: the filters that were feeding the board
    # (now dashboardEnabled) were the email-enabled ones — re-enable their email.
    op.execute(
        """
        UPDATE buybox_filters
           SET daily_email_enabled = true
         WHERE (filter_json ->> 'dashboardEnabled')::boolean IS TRUE
        """
    )
    op.execute(
        "UPDATE buybox_filters SET filter_json = filter_json - 'dashboardEnabled'"
    )
