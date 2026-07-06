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

Operational shape (prod has millions of parcel rows):
    - ADD COLUMN is nullable with no default → metadata-only, instant.
    - The backfill runs in BATCHES of 50k rows keyed on the PK, each batch
      committing independently (autocommit_block), so no long row-lock window
      and a cancelled run resumes where it left off. The batch predicate only
      selects rows the CASE would actually set (else the NULL-outcome rows
      would be re-selected forever).
    - The index is created CONCURRENTLY (also requires autocommit) so writes
      to parcels are never blocked.

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

_BATCH = 50_000

# Only rows this backfill would actually change. Keeps each batch's candidate
# scan honest AND terminates the loop (rows whose CASE outcome is NULL are
# never selected).
_NEEDS_BACKFILL = (
    "zoning_code_source IS NULL AND ("
    "  zone_binding_method = 'contained'"
    "  OR zone_binding_method LIKE 'nearest\\_%'"
    "  OR (zoning_code IS NOT NULL AND zoning_code <> '')"
    ")"
)

_BATCH_UPDATE = sa.text(
    f"""
    UPDATE parcels SET zoning_code_source = CASE
        WHEN zone_binding_method = 'contained'             THEN 'district_spatial'
        WHEN zone_binding_method LIKE 'nearest\\_%'         THEN 'nearest'
        WHEN zoning_code IS NOT NULL AND zoning_code <> '' THEN 'parcel_attr'
        ELSE NULL
    END
    WHERE id IN (
        SELECT id FROM parcels
        WHERE {_NEEDS_BACKFILL}
        ORDER BY id
        LIMIT {_BATCH}
    )
    """
)


def upgrade() -> None:
    # Instant: nullable, no default.
    op.add_column(
        "parcels",
        sa.Column("zoning_code_source", sa.String(length=32), nullable=True),
    )

    # Batched backfill + CONCURRENTLY index — both need to run outside the
    # migration transaction (each batch commits; CONCURRENTLY refuses to run
    # inside any transaction block).
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        total = 0
        while True:
            result = conn.execute(_BATCH_UPDATE)
            n = result.rowcount or 0
            total += n
            print(f"  0042 backfill: +{n} (total {total})")
            if n < _BATCH:
                break
        print(f"  0042 backfill complete: {total} rows stamped")

        conn.execute(
            sa.text(
                "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                "ix_parcels_jurisdiction_zoning_source "
                "ON parcels (jurisdiction_id, zoning_code_source)"
            )
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcels_jurisdiction_zoning_source")
    op.drop_column("parcels", "zoning_code_source")
