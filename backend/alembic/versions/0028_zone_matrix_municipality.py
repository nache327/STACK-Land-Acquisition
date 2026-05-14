"""Add municipality dimension to zone_use_matrix.

Why:
    The matrix was keyed (jurisdiction_id, zone_code). For township-as-
    jurisdiction states (e.g., UT) that's fine — each Lehi zone code
    appears once. For county-as-jurisdiction states (e.g., NJ) it's
    wrong: a single county has many municipalities and shared zone
    codes ("B-1") mean different things across townships. Today's
    Somerville-only zoning corrections applied county-wide because
    there was nowhere else to put them.

After this migration:
    - Each row may carry an optional municipality (TEXT). NULL means
      "default for this county" — falls through when a township-
      specific row exists.
    - The scorer's matrix lookup picks the township-specific row when
      one exists, else the NULL-municipality fallback.
    - Uniqueness via UNIQUE INDEX on
      (jurisdiction_id, zone_code, COALESCE(municipality, '')) so
      multiple NULL-municipality rows can't collide and township rows
      coexist with the default.

Backfill:
    Mark the 9 Somerville-flavored Somerset rows (applied 2026-05-14)
    with municipality = 'Somerville borough' to match the TIGER MCD
    name now populated in parcels.city.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-14 18:31:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOMERSET_ID = "394ef40c-ca0d-4d57-9b11-dc5417430240"
SOMERVILLE_NAME = "Somerville borough"
SOMERVILLE_ZONES = ("B-1", "B-2", "B-3", "B-4", "B-5", "B-6", "CG", "H", "I-1")


def upgrade() -> None:
    op.execute("ALTER TABLE zone_use_matrix ADD COLUMN municipality TEXT")

    # Drop the old (jurisdiction_id, zone_code) unique constraint so we
    # can replace it with the municipality-aware one. The constraint
    # name was 'uq_zone_matrix' per the model definition.
    op.execute(
        "ALTER TABLE zone_use_matrix DROP CONSTRAINT IF EXISTS uq_zone_matrix"
    )

    # New uniqueness: COALESCE the optional municipality to empty string
    # so the unique index treats NULL as a real value and we can have
    # exactly one (jurisdiction, zone_code, municipality=NULL) row per
    # county AND one row per (jurisdiction, zone_code, "Somerville
    # borough") etc. without collision.
    op.execute(
        "CREATE UNIQUE INDEX uq_zone_matrix "
        "ON zone_use_matrix "
        "(jurisdiction_id, zone_code, COALESCE(municipality, ''))"
    )

    # Backfill: the 9 Somerville-flavored Somerset rows applied earlier
    # today should be marked as Somerville-specific, not county-wide.
    # Match on classification_source='human' + zone_code IN (...) to
    # avoid touching any other human-edited rows.
    zone_list = ",".join(f"'{z}'" for z in SOMERVILLE_ZONES)
    op.execute(
        f"""
        UPDATE zone_use_matrix
           SET municipality = '{SOMERVILLE_NAME}'
         WHERE jurisdiction_id = '{SOMERSET_ID}'::uuid
           AND classification_source = 'human'
           AND zone_code IN ({zone_list})
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_zone_matrix")
    op.execute(
        "ALTER TABLE zone_use_matrix "
        "ADD CONSTRAINT uq_zone_matrix "
        "UNIQUE (jurisdiction_id, zone_code)"
    )
    op.execute("ALTER TABLE zone_use_matrix DROP COLUMN IF EXISTS municipality")
