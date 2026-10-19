"""parcel_keep_metrics.competitor_units_30 — garage-condo supply within ~30 min

Keep tier/mix cards (owner decision 2026-10-19): every garage-condo (LGC) board card
shows the competitor units within a 30-minute drive, as INFORMATION ONLY (never a
gate). Proxy: units (built or planned) of the campuses in
backend/data/keep_supply_campuses.csv within 30 km straight-line of the parcel's
census-tract point — computed by app.services.keep_market.competitor_units.

Idempotent (ADD COLUMN IF NOT EXISTS) so a crash-looped Railway boot re-apply is
harmless. Light: NO backfill here — scripts/backfill_keep_competitors.py fills it.

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE parcel_keep_metrics ADD COLUMN IF NOT EXISTS competitor_units_30 INTEGER"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE parcel_keep_metrics DROP COLUMN IF EXISTS competitor_units_30")
