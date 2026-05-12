"""zoning_overlays: dedupe + UNIQUE (parcel_id)

Philadelphia ended up with ~2x ZoningOverlay rows per parcel (1,093,778 for
547k parcels) because bulk_ingest_zoning_for_jurisdiction's SELECT … LEFT
JOIN zoning_overlays o … WHERE o.id IS NULL pattern is racy: two back-to-back
pipeline runs both observed no overlays for the same parcel and both
inserted. Result: every parcel has duplicate overlays, the buybox scorer
joins to the rule twice, and the storage-permission color flickers on the
frontend.

This migration:
  1. Deletes duplicate overlays per parcel_id (keep the earliest by
     created_at, fall back to lowest UUID).
  2. Adds a UNIQUE constraint on zoning_overlays.parcel_id so future inserts
     can use ON CONFLICT (parcel_id) DO NOTHING and be naturally idempotent.

Safe to run with prod traffic — the DELETE uses a CTE that postgres holds
in a single transaction; the ADD CONSTRAINT takes an ACCESS EXCLUSIVE lock
on zoning_overlays for the duration of the index build, which on 1.1M rows
should be a second or two.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: dedupe — keep the oldest overlay per parcel_id; delete the rest.
    op.execute(
        """
        DELETE FROM zoning_overlays
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY parcel_id
                           ORDER BY created_at NULLS LAST, id
                       ) AS rn
                FROM zoning_overlays
            ) ranked
            WHERE ranked.rn > 1
        )
        """
    )

    # Step 2: enforce one overlay per parcel from now on.
    op.create_unique_constraint(
        "uq_zoning_overlays_parcel_id",
        "zoning_overlays",
        ["parcel_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_zoning_overlays_parcel_id",
        "zoning_overlays",
        type_="unique",
    )
