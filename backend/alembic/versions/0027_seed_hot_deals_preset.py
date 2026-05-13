"""Seed canonical "Hot deals" buy-box preset.

A second saved filter alongside Default Box, scoped to the same
(default org, self_storage use case). Differs from Default Box in two
key ways:

  * ``requireListed: true`` — dashboard collapses to parcels with an
    active for-sale listing match.
  * ``daily_email_enabled: true`` — the daily digest worker picks it
    up automatically. Top 10 by score.

The thresholds otherwise mirror the current Default Box snapshot
(pop 50K / hhi $100K / home $475K / hnw 4400, drive-time 10 min,
listingScoreBoost 15). The Hot deals daily digest leans on the
``_MIN_SCORE_LISTED`` floor (score >= 70) already shipped in
``daily_email.py`` — no worker changes needed.

Idempotent: INSERT ... ON CONFLICT DO NOTHING on the existing
``uq_buybox_filters_org_use_name`` constraint. ``is_default`` stays
false so Default Box remains the dashboard default.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-13 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
SELF_STORAGE_USE_CASE_ID = "00000000-0000-0000-0000-000000000002"
HOT_DEALS_NAME = "Hot deals"


def upgrade() -> None:
    op.execute(sa.text(
        f"""
        INSERT INTO buybox_filters (
            organization_id,
            use_case_id,
            name,
            filter_json,
            is_default,
            daily_email_enabled,
            daily_email_top_n
        )
        VALUES (
            '{DEFAULT_ORG_ID}'::uuid,
            '{SELF_STORAGE_USE_CASE_ID}'::uuid,
            '{HOT_DEALS_NAME}',
            jsonb_build_object(
                'minPopulation',       50000,
                'minMedianHHI',        100000,
                'minMedianHomeValue',  475000,
                'minHnwHouseholds',    4400,
                'minAADT',             null,
                'minHomesOver1M',      null,
                'minHomesOver2M',      null,
                'minHomesOver5M',      null,
                'requireListed',       true,
                'listingScoreBoost',   15,
                'sortListedFirst',     false,
                'driveTimeMinutes',    10,
                'matchLogic',          'AND'
            ),
            false,
            true,
            10
        )
        ON CONFLICT ON CONSTRAINT uq_buybox_filters_org_use_name DO NOTHING
        """
    ))


def downgrade() -> None:
    op.execute(sa.text(
        f"""
        DELETE FROM buybox_filters
         WHERE organization_id = '{DEFAULT_ORG_ID}'::uuid
           AND use_case_id     = '{SELF_STORAGE_USE_CASE_ID}'::uuid
           AND name            = '{HOT_DEALS_NAME}'
        """
    ))
