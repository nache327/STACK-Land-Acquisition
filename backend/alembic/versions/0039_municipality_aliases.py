"""Municipality alias map — reliable parcels.city <-> zone_use_matrix.municipality pairing.

Why:
    For county-as-jurisdiction setups, the buybox LATERAL join keys on
    `zone_use_matrix.municipality = parcels.city` (verbatim string equality),
    and the city->county crosswalk discovers sibling jurisdictions by
    normalizing names against the distinct `parcels.city` set. Both are
    free-text comparisons, so any format/spelling difference between a
    parcel's city string and a sibling jurisdiction's name (or a matrix
    municipality) creates a SILENT pairing gap — the city scores nothing
    and never appears as covered.

    This table records, per county jurisdiction, an (alias_city ->
    canonical_city) mapping so the normalize layer can resolve a parcel
    city string to the canonical municipality used by the matrix/sibling.
    Modeled on the existing alias_mappings table (migration 0033) which
    does the same thing for zone CODES.

Schema:
    municipality_aliases is additive. When empty, the normalize layer
    falls back to pure string canonicalization, so behavior is unchanged
    until aliases are seeded (auto-proposed by the crosswalk, or added by
    a human in the verifier).

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-02 00:00:00.000000

Note: renumbered 0038 -> 0039 to resolve a duplicate-revision collision.
Adam's 0038_parcels_zone_binding_method.py also claimed revision "0038" off
0037 (merged to main independently of PR #174), so this migration now chains
AFTER it: 0037 -> 0038 (parcels_zone_binding_method) -> 0039.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS municipality_aliases (
          id              SERIAL PRIMARY KEY,
          jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
          alias_city      TEXT NOT NULL,
          canonical_city  TEXT NOT NULL,
          source          TEXT,
          confidence      REAL DEFAULT 0.0,
          notes           TEXT,
          human_reviewed  BOOLEAN NOT NULL DEFAULT FALSE,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          promoted_at     TIMESTAMPTZ,
          UNIQUE (jurisdiction_id, alias_city)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_municipality_aliases_canonical "
        "ON municipality_aliases(jurisdiction_id, canonical_city)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_municipality_aliases_canonical")
    op.execute("DROP TABLE IF EXISTS municipality_aliases")
