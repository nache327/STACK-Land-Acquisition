"""parcel_keep_metrics — garage-condo (LGC) keep-market depth metrics per parcel

Phase B of the 2026-10 keep-market calibration: the LGC lane's price and sell-out
speed track WEALTH DEPTH near the site (share of $1M+ owner homes within a 20-min
drive, drive time to the nearest $1M+ cluster), not the dt=10 ring median home value
it borrowed from storage. This table holds those inputs plus the lane / price band /
velocity flag derived by app.services.keep_market. Storage never reads it.

Idempotent DDL (CREATE TABLE / INDEX IF NOT EXISTS + ADD COLUMN IF NOT EXISTS) so a
crash-looped Railway boot re-apply is harmless. Light: no backfill here — the data is
loaded by scripts/precompute_keep_metrics.py --load-csv.

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    ("tract_geoid", "TEXT"),
    ("hh_200k_20", "INTEGER"),
    ("owner_1m_count_20", "INTEGER"),
    ("owner_1m_share_20", "DOUBLE PRECISION"),
    ("seasonal_share_20", "DOUBLE PRECISION"),
    ("young_old_200k_ratio_20", "DOUBLE PRECISION"),
    ("wealth_center_drive_min", "DOUBLE PRECISION"),
    ("wealth_center_km", "DOUBLE PRECISION"),
    ("wealth_center_label", "TEXT"),
    ("county_home_ppsf", "DOUBLE PRECISION"),
    ("keep_lane", "TEXT"),
    ("price_band_low", "INTEGER"),
    ("price_band_high", "INTEGER"),
    ("velocity_flag", "TEXT"),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS parcel_keep_metrics (
            parcel_id    BIGINT PRIMARY KEY
                         REFERENCES parcels(id) ON DELETE CASCADE,
            computed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Columns via ADD COLUMN IF NOT EXISTS so a partially-created table (or a later
    # re-run after a column is added here) converges instead of erroring.
    for name, typ in _COLUMNS:
        op.execute(f"ALTER TABLE parcel_keep_metrics ADD COLUMN IF NOT EXISTS {name} {typ}")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcel_keep_metrics_tract "
        "ON parcel_keep_metrics (tract_geoid)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS parcel_keep_metrics")
