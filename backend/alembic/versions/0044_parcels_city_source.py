"""Add parcels.city_source provenance (Task #86; column ONLY — the stamp is a JOB).

city_source distinguishes boundary-derived cities from source-attribute ones
(same discipline as zoning_code_source, 0042):
    'boundary_spatial' — centroid-in-municipal-boundary stamp
    'district_spatial' — zoning-district municipality stamp
    NULL               — source-attribute / crosswalk / pre-provenance

0042 LESSON APPLIED: no data backfill in this file — the multi-million-row
stamp runs as scripts/backfill_city_from_boundaries.py (batched, resumable,
never in the deploy path). This ADD COLUMN is nullable/no-default = instant.

Revision ID: 0044
Revises: 0043
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET statement_timeout = 0")
    op.execute("ALTER TABLE parcels ADD COLUMN IF NOT EXISTS city_source VARCHAR(32) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE parcels DROP COLUMN IF EXISTS city_source")
