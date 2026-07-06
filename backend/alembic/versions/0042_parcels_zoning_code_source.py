"""Add parcels.zoning_code_source provenance column (schema only — no backfill).

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
        NULL               — unknown / pre-migration row

NULL semantics (load-bearing — tested in test_zoning_provenance.py and
test_zoning_precedence_db.py):
    NULL is the LOWEST precedence, freely overridable. The backfill predicate
    uses ``zoning_code_source IS DISTINCT FROM 'district_spatial'`` (NULL-safe),
    so a pre-migration row with a code but NULL source is re-bound by the next
    county district backfill. NULL must NEVER be treated as trusted
    'parcel_attr' — that would freeze stale county codes and defeat D2.

Why there is NO data backfill here (removed 2026-07-06):
    The original best-effort backfill (stamp provenance on existing rows from
    zone_binding_method/zoning_code) proved operationally infeasible: parcels
    has ~17.6M rows and every UPDATE rewrites six indexes (two GiST), measured
    at ~16 min per 50k batch on the prod instance — days of runtime. It was
    also never functionally required: ingest stamps provenance on new writes,
    and each jurisdiction's spatial backfill stamps 'district_spatial' as it
    (re-)binds — old rows converge organically, and until then their NULL
    source correctly marks them lowest-precedence (see NULL semantics above).
    Prod was stamped at exactly this schema state (column + index, no
    backfill) on 2026-07-06; this file must keep producing that same state so
    fresh envs/CI match prod (no 0008b/0009b-style drift).

Operational notes:
    - ADD COLUMN is nullable with no default → metadata-only, instant.
    - The index is created CONCURRENTLY inside an autocommit block (it cannot
      run in a transaction) so writes to parcels are never blocked. If a
      CONCURRENTLY build is interrupted it leaves an INVALID index that
      IF NOT EXISTS will silently skip — check pg_index.indisvalid and
      DROP + re-create if invalid.
    - SET statement_timeout=0 comes FIRST: lock-wait time counts toward
      statement_timeout, and Railway runs `alembic upgrade head` at container
      boot, where a queued ALTER behind a long query was observed to cancel.

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
    # FIRST statement — see "Operational notes" in the module docstring.
    op.execute("SET statement_timeout = 0")

    # Idempotent + instant (nullable, no default).
    op.execute(
        "ALTER TABLE parcels ADD COLUMN IF NOT EXISTS "
        "zoning_code_source VARCHAR(32)"
    )

    # CONCURRENTLY requires autocommit (refuses to run inside a transaction).
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_parcels_jurisdiction_zoning_source "
            "ON parcels (jurisdiction_id, zoning_code_source)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcels_jurisdiction_zoning_source")
    op.drop_column("parcels", "zoning_code_source")
