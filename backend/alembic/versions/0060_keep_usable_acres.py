"""parcel_keep_metrics usable acres + existing building

Owner decision 2026-10-19: a garage-condo card's land $/SF is spread over the USABLE
acres (gross minus the area under NWI wetlands UNION FEMA SFHA zones, so an overlap is
not subtracted twice), and the card says when the parcel already carries a building
(assessor improvement value >= 25% of total assessed value).

  gross_acres        parcels.acres at compute time (the acreage the card shows)
  usable_acres       gross × (1 − constrained fraction of the parcel geometry)
  wetland_acres      gross × wetland fraction            (NWI, all wetland types)
  sfha_acres         gross × SFHA fraction               (A / AE / AH / AO / V / VE)
  improvement_share  improvement value ÷ total assessed value (NULL = not on the roll)
  existing_building  improvement_share >= keep_market.EXISTING_BUILDING_SHARE

Idempotent (ADD COLUMN IF NOT EXISTS) so a crash-looped Railway boot re-apply is
harmless. Light: NO backfill here — scripts/backfill_keep_usable.py fills it.

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0060"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("gross_acres", "DOUBLE PRECISION"),
    ("usable_acres", "DOUBLE PRECISION"),
    ("wetland_acres", "DOUBLE PRECISION"),
    ("sfha_acres", "DOUBLE PRECISION"),
    ("improvement_share", "DOUBLE PRECISION"),
    ("existing_building", "BOOLEAN"),
    # When the usable-acres overlay was last measured for this row (NULL = never);
    # lets the backfill resume and re-measure only what it hasn't done.
    ("usable_computed_at", "TIMESTAMPTZ"),
)


def upgrade() -> None:
    for name, typ in _COLUMNS:
        op.execute(f"ALTER TABLE parcel_keep_metrics ADD COLUMN IF NOT EXISTS {name} {typ}")


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE parcel_keep_metrics DROP COLUMN IF EXISTS {name}")
