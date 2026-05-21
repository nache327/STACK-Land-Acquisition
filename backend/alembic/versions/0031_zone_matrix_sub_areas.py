"""Add sub_areas_eligible TEXT[] to zone_use_matrix.

Why:
    Loudoun VA sprint surfaced sub-area-restricted conditional verdicts:
      - TRC: conditional only in {Outer Core, Transit-Designed
        Supportive Area}; prohibited in other TRC sub-areas
      - TC:  conditional only in {Fringe}; prohibited in Core
      - PD-RV: conditional only in {Commercial and Workplace Areas};
        prohibited in residential portions
    Current schema can't model "conditional in some parts of the zone."
    The matrix says "TRC conditional" which over-includes parcels in
    the prohibited sub-areas.

    sub_areas_eligible captures the named sub-areas where the verdict
    holds. NULL = verdict applies to the entire zone (no restriction).
    Buy-box stays over-inclusive for now (treats any TRC parcel as
    conditional); a future spatial-join sprint will tag parcels with
    their sub-area name via overlay shapefiles, then matrix lookup can
    refine to per-sub-area verdicts.

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-21 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute(
        "ALTER TABLE zone_use_matrix "
        "ADD COLUMN IF NOT EXISTS sub_areas_eligible TEXT[] NULL"
    )

def downgrade() -> None:
    op.execute(
        "ALTER TABLE zone_use_matrix "
        "DROP COLUMN IF EXISTS sub_areas_eligible"
    )
