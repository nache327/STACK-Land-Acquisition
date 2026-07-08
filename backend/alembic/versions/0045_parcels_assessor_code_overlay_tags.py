"""Rollback provenance + overlay tags for the MA district rebind (columns ONLY).

assessor_zoning_code — the pre-rebind parcels.zoning_code value, preserved the
    first time the district rebind overwrites it (write-once: the ORIGINAL
    assessor label survives repeated rebinds for rollback).
overlay_tags — JSONB list of overlay-district codes containing the parcel
    (e.g. ["SS"] for Billerica's Self-Service Storage Facility overlay).
    Overlays are NEVER written to zoning_code (base districts only); the
    buybox filters on this tag instead.

0042 LESSON APPLIED: no data backfill here — the rebind runs as
scripts/backfill_zoning_from_districts.py (batched job, dry-run + diff
artifact first, per-muni blocking gates). Nullable/no-default = instant DDL.

Revision ID: 0045
Revises: 0044
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET statement_timeout = 0")
    op.execute("ALTER TABLE parcels ADD COLUMN IF NOT EXISTS assessor_zoning_code VARCHAR(50) NULL")
    op.execute("ALTER TABLE parcels ADD COLUMN IF NOT EXISTS overlay_tags JSONB NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE parcels DROP COLUMN IF EXISTS assessor_zoning_code")
    op.execute("ALTER TABLE parcels DROP COLUMN IF EXISTS overlay_tags")
