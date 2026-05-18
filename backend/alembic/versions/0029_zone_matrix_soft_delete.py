"""Soft-delete (tombstone) for zone_use_matrix.

Why:
    matrix_bootstrap.bootstrap_zone_use_matrix() is called from the
    ingest pipeline (and was observed running on its own schedule)
    and re-inserts NULL-municipality rows with src='unclear' for any
    zone_code missing from the matrix. Result: hard DELETEs of fuzzy
    auto-classified rows get resurrected within ~30min. Observed
    twice on 2026-05-18 (16:18:28 burst of 5 rows, 18:58:26 burst of
    11 rows — the surgical-delete set).

After this migration:
    - zone_use_matrix gains deleted_at TIMESTAMPTZ NULL.
    - All read sites filter `deleted_at IS NULL`.
    - matrix_bootstrap's existence check looks at ALL rows, including
      tombstones — so a tombstoned slot blocks re-insert.
    - DELETE endpoint converts to soft-delete (UPDATE deleted_at).
    - The uniqueness index on
      (jurisdiction_id, zone_code, COALESCE(municipality, '')) becomes
      partial — WHERE deleted_at IS NULL — so an active row can coexist
      with one or more tombstoned rows for the same triplet (history).

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-18 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tombstone column.
    op.execute(
        "ALTER TABLE zone_use_matrix "
        "ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL"
    )

    # Replace the existing (jurisdiction_id, zone_code, COALESCE(municipality, ''))
    # unique index with a partial variant that scopes to active rows
    # only. Tombstones can pile up for the same triplet over time
    # without colliding; only one active row per triplet is enforced.
    op.execute("DROP INDEX IF EXISTS uq_zone_matrix")
    op.execute(
        "CREATE UNIQUE INDEX uq_zone_matrix "
        "ON zone_use_matrix "
        "(jurisdiction_id, zone_code, COALESCE(municipality, '')) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    # Restore the non-partial index, then drop the column. If there
    # are tombstoned rows that would collide with active ones in the
    # non-partial index, the recreate will fail — that's intentional;
    # operator must manually purge tombstones before downgrading.
    op.execute("DROP INDEX IF EXISTS uq_zone_matrix")
    op.execute(
        "CREATE UNIQUE INDEX uq_zone_matrix "
        "ON zone_use_matrix "
        "(jurisdiction_id, zone_code, COALESCE(municipality, ''))"
    )
    op.execute("ALTER TABLE zone_use_matrix DROP COLUMN IF EXISTS deleted_at")
