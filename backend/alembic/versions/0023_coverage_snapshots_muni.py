"""coverage_snapshots per-municipality breakdown

Adds a JSONB column to coverage_snapshots for per-town progression
visibility. Shape:

    {
      "Paramus":   {"parcels": 8619, "parcels_with_zoning": 8619,
                    "zoning_overlays": 8619, "districts": 115},
      "Mahwah":    {"parcels": 11023, "parcels_with_zoning": 0, ...},
      ...
    }

Populated by coverage_audit.refresh_snapshot() via a GROUP BY city
roll-up. If parcels.city is null/empty for a jurisdiction, the rollup
degrades to a single 'unknown' bucket and the column stays useful for
metadata even if per-town granularity is missing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "coverage_snapshots",
        sa.Column("municipality_breakdown", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("coverage_snapshots", "municipality_breakdown")
