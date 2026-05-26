"""Add parcels.normalized_address for symmetric listing matching.

Why:
    listing_matcher Tier 1/2 compares normalize(listing.address) against
    the parcel address run through ONLY lower() + strip-punctuation in
    SQL. normalize() additionally expands street-type abbreviations
    (Dr->drive, St->street), directionals (N->north), and canonicalizes
    routes. So:
      listing  "1 Cascade Dr"  -> normalize -> "1 cascade drive"
      parcel   "1 CASCADE DR"  -> SQL       -> "1 cascade dr"
    never match. Any jurisdiction where Census/Nominatim geocoding also
    fails (Allentown PA city grid, Middlesex composite addresses) gets
    0 address-tier matches -- the geocode tiers were silently carrying
    the load for jurisdictions that DO geocode (Howard MD: 25/94).

Fix:
    Materialize a normalized_address column populated by the same
    normalize() Python function. Matcher Tier 1/2 then compares
    p.normalized_address = :norm -- symmetric, indexed.

    Backfilled per-jurisdiction by scripts/backfill_normalized_address.py.
    Column is NULL until backfilled; the matcher keeps an inline-SQL
    fallback so un-backfilled jurisdictions don't regress.

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-26 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE parcels ADD COLUMN IF NOT EXISTS normalized_address TEXT NULL")
    # Index for the Tier 1/2 equality lookup, scoped per jurisdiction.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcels_jur_normaddr "
        "ON parcels (jurisdiction_id, normalized_address)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcels_jur_normaddr")
    op.execute("ALTER TABLE parcels DROP COLUMN IF EXISTS normalized_address")
