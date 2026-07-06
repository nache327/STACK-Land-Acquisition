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

# Keyset pagination: each batch resumes from the last stamped PK instead of
# rescanning the already-stamped prefix — total work stays O(N) across the
# whole run. RETURNING feeds the next batch's cursor.
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
        WHERE id > :last_id AND {_NEEDS_BACKFILL}
        ORDER BY id
        LIMIT {_BATCH}
    )
    RETURNING id
    """
)


def upgrade() -> None:
    # IF NOT EXISTS (not op.add_column): the batched section below commits per
    # batch, so an interrupted run leaves the column in place with the version
    # still at 0041 — the retry must not die on "column already exists".
    # Nullable, no default → metadata-only, instant.
    op.execute(
        "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS "
        "zoning_code_source VARCHAR(32)"
    )

    # Batched backfill + CONCURRENTLY index — both need to run outside the
    # migration transaction (each batch commits; CONCURRENTLY refuses to run
    # inside any transaction block).
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        # Supabase enforces a server-side statement_timeout that killed the
        # original monolithic UPDATE (observed in the Railway boot crashloop,
        # 2026-07-06). Batches are small, but late-run batches on a cold cache
        # can still be slow — disable the timeout for this session only.
        conn.execute(sa.text("SET statement_timeout = 0"))
        total = 0
        last_id = 0
        while True:
            result = conn.execute(_BATCH_UPDATE, {"last_id": last_id})
            ids = [r[0] for r in result]
            if not ids:
                break
            total += len(ids)
            last_id = max(ids)
            print(f"  0042 backfill: +{len(ids)} (total {total}, cursor id {last_id})")
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
