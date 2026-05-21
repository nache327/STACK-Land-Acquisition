"""Add structured-conditions + overlay columns to zone_use_matrix.

Why:
    Howard MD sprint surfaced data-loss-in-flight: B-2 self-storage is
    "conditional iff acres >= 5 AND public_water_sewer = true". Storing
    only "conditional" loses the conditions, so the buy-box can't auto-
    soft-flag a 3-acre B-2 parcel that would actually fail the
    conditional-use test. Same shape applies to overlays (Westampton
    PUD/MCD, Howard -I / -DEO / -CLI): a parcel's effective verdict
    is base_zone + overlay_adjustments, which the matrix can't model
    today.

After this migration:
    - cited_subsection TEXT: the single canonical ordinance section
      that supports the verdict (e.g. "§122.0 A.1"). citations JSONB
      can still carry multi-section evidence; this is the headline.
    - conditions_json JSONB: structured conditions like
      {"min_acres": 5, "requires_public_water_sewer": true}. NULL when
      verdict has no conditions. Buy-box query layer reads this and
      either hard-filters or soft-flags accordingly.
    - overlay_codes TEXT[]: tags for overlay districts that modify the
      base verdict (e.g. ['I'] for institutional, ['DEO'] for density
      exchange). NULL/empty when no overlay.

All three columns are NULL by default. Existing rows are unaffected.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE zone_use_matrix "
        "ADD COLUMN IF NOT EXISTS cited_subsection TEXT NULL"
    )
    op.execute(
        "ALTER TABLE zone_use_matrix "
        "ADD COLUMN IF NOT EXISTS conditions_json JSONB NULL"
    )
    op.execute(
        "ALTER TABLE zone_use_matrix "
        "ADD COLUMN IF NOT EXISTS overlay_codes TEXT[] NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE zone_use_matrix DROP COLUMN IF EXISTS overlay_codes")
    op.execute("ALTER TABLE zone_use_matrix DROP COLUMN IF EXISTS conditions_json")
    op.execute("ALTER TABLE zone_use_matrix DROP COLUMN IF EXISTS cited_subsection")
