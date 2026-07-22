"""parcel_radial_metrics — fixed-radius (circular) ring metrics per parcel

Separate from parcel_ring_metrics (which is drive-time isochrone based and
whose aggregation is frozen in lock-step with the frontend twin). This table
holds area-weighted radial census values — the trustworthy 3-mile population
the saturation panel already computes live — so we can (a) apply Nache's
"too rural" floor (3-mi pop < 30k) as a score factor + board gate, and (b)
lane-split saturation later (competitor sqft/capita at the same radius).

Idempotent CREATE (IF NOT EXISTS) so a crash-looped Railway boot re-apply is
harmless. Light DDL, no backfill here — that runs as a script.

Revision ID: 0054
Revises: 0053
Create Date: 2026-07-22 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS parcel_radial_metrics (
            parcel_id        BIGINT NOT NULL
                             REFERENCES parcels(id) ON DELETE CASCADE,
            radius_miles     NUMERIC(4,1) NOT NULL,
            population       INTEGER,
            competitor_sqft  BIGINT,
            sqft_per_capita  NUMERIC(10,2),
            computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (parcel_id, radius_miles)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS parcel_radial_metrics")
