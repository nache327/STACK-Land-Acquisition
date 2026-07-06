"""Add parcels.zoning_code_source provenance column.

Why:
    ``zone_binding_method`` records the spatial *sub-method* (contained /
    nearest_<N>m) but not which *authority* a parcel's ``zoning_code`` came
    from. Without that, a stale county parcel-attribute code and an
    authoritative municipal district code are indistinguishable — so the
    fill-only-where-NULL backfill silently lets the county attribute win
    forever, and a re-ingest can never clear a bad code (audit "D2").

    ``zoning_code_source`` classifies the authority:
        'parcel_attr'      — the source parcel layer's own zoning field (ingest)
        'district_spatial' — ST_Within(centroid, municipal district) containment
        'nearest'          — ST_DWithin nearest-district fallback
        'sibling_apn'      — inherited from a sibling parcel via APN crosswalk
        NULL               — no zoning_code / pre-migration unknown

    Best-effort backfilled from the existing ``zone_binding_method`` +
    ``zoning_code`` so live rows get a provenance without a re-ingest.

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-06 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parcels",
        sa.Column("zoning_code_source", sa.String(length=32), nullable=True),
    )
    # Best-effort backfill from existing signals (no re-ingest needed).
    op.execute(
        """
        UPDATE parcels SET zoning_code_source = CASE
            WHEN zone_binding_method = 'contained'            THEN 'district_spatial'
            WHEN zone_binding_method LIKE 'nearest\\_%'        THEN 'nearest'
            WHEN zoning_code IS NOT NULL AND zoning_code <> '' THEN 'parcel_attr'
            ELSE NULL
        END
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcels_jurisdiction_zoning_source "
        "ON parcels (jurisdiction_id, zoning_code_source)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcels_jurisdiction_zoning_source")
    op.drop_column("parcels", "zoning_code_source")
