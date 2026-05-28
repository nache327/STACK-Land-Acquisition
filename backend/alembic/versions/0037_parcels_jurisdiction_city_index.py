"""Add (jurisdiction_id, city) composite index on parcels.

Why:
    The dashboard's /cities and /zone-class-summary endpoints do
    GROUP BY queries scoped to a single jurisdiction_id. With only
    standalone indexes on jurisdiction_id and city, county-sized
    jurisdictions (SLCo: 397k parcels) hit a sequential scan + hash
    aggregate that exceeded the 30s request timeout. Composite index
    on (jurisdiction_id, city) lets the planner use an index-only scan
    for the GROUP BY.

Note for prod:
    On a hot DB run /api/_admin/optimize-parcels first — it creates the
    same index CONCURRENTLY and ANALYZEs. This migration uses a regular
    CREATE INDEX (briefer lock, fine for fresh setups). Both are
    idempotent so re-running either after the other is a no-op.

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-28 12:30:00.000000
"""
from typing import Sequence, Union
from alembic import op


revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcels_jurisdiction_city "
        "ON parcels (jurisdiction_id, city)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcels_jurisdiction_city")
