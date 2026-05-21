"""Alias mappings framework — generalizable "same zone, different
string" handling across jurisdictions.

Why:
    Recurring pattern: parcels carry zone_code strings that don't
    match canonical zone_use_matrix.zone_code. Examples:
      - Hyphen-stripped (AR1 vs AR-1, MRHI vs MR-HI)
      - Typos (RA51 vs R-A-15)
      - Truncation (CACCL vs CAC-CLI -- 5-char fixed-width sources)
      - Case variants
      - Ordinance-era variants (1993 vs 2023 LCZO)
    Howard MD shipped 72 aliases; Loudoun has ~40K parcels worth.
    Building this once means every future jurisdiction ingest gets
    automatic alias detection.

Schema:
    alias_mappings stores per-jurisdiction (alias -> canonical)
    pairs with the alias type and reviewer status. Drives:
      Strategy A: rewrite parcels.zoning_code -> canonical (mechanical
        aliases; preserves original in zoning_code_pre_normalization)
      Strategy B: insert matrix row at the alias code that inherits
        from canonical (ordinance-era variants; parcel code is legally
        meaningful)

    parcels.zoning_code_pre_normalization preserves the original
    string for rollback / audit when Strategy A overwrites.

    classification_source_enum += 'alias_inherited' for Strategy B
    matrix rows.

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-21 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS alias_mappings (
          id              SERIAL PRIMARY KEY,
          jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
          alias_code      TEXT NOT NULL,
          canonical_code  TEXT NOT NULL,
          alias_type      TEXT NOT NULL,
          parcel_count    INTEGER,
          source          TEXT,
          confidence      REAL DEFAULT 0.0,
          notes           TEXT,
          human_reviewed  BOOLEAN NOT NULL DEFAULT FALSE,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          promoted_at     TIMESTAMPTZ,
          UNIQUE (jurisdiction_id, alias_code)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_alias_mappings_canonical "
        "ON alias_mappings(jurisdiction_id, canonical_code)"
    )
    op.execute(
        "ALTER TABLE parcels "
        "ADD COLUMN IF NOT EXISTS zoning_code_pre_normalization TEXT NULL"
    )
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE classification_source_enum "
        "ADD VALUE IF NOT EXISTS 'alias_inherited'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alias_mappings_canonical")
    op.execute("DROP TABLE IF EXISTS alias_mappings")
    op.execute("ALTER TABLE parcels DROP COLUMN IF EXISTS zoning_code_pre_normalization")
    # alias_inherited enum value retained (Postgres doesn't support clean removal).
