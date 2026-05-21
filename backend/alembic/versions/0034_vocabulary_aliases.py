"""Vocabulary aliases — map jurisdiction-specific use-name terms to
the canonical use class.

Why:
    Three jurisdictions, three vocabularies for the same use class:
      Howard MD:  "Self-Storage Facilities" (§131.0)
      Loudoun VA: "Mini-Warehouse" (§4.06.06)
      Allentown PA: "Self-Service Storage" (§660-37M)
    Future jurisdictions will surface more: "self storage", "personal
    storage", "mini storage", "self-service storage facility", etc.
    Hard-coding the mapping in extractors / parsers fails the
    next-jurisdiction test. A registry lets us add a new term in one
    row without code changes.

Schema:
    canonical_use_name           — e.g. 'self_storage_facility' (matches
                                   the buy-box's internal use-class enum)
    jurisdiction_specific_term   — exact ordinance verbatim
    jurisdiction_id              — NULL = globally applicable; non-NULL
                                   = jurisdiction-scoped (when one
                                   jurisdiction uses a term in a
                                   different sense than another)
    source                       — cited section (e.g. '§660-37M')
    notes                        — provenance / disambiguation

Unique on (canonical_use_name, lower(jurisdiction_specific_term),
COALESCE(jurisdiction_id, '00000000-0000-0000-0000-000000000000'))
so the same term can coexist global + jurisdiction-scoped if needed.

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-21 15:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS vocabulary_aliases (
            id                          SERIAL PRIMARY KEY,
            canonical_use_name          TEXT NOT NULL,
            jurisdiction_specific_term  TEXT NOT NULL,
            jurisdiction_id             UUID NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
            source                      TEXT,
            notes                       TEXT,
            created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Postgres UNIQUE constraints don't allow expressions; use a UNIQUE INDEX.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_vocab_aliases_canonical_term_jur
          ON vocabulary_aliases (
            canonical_use_name,
            lower(jurisdiction_specific_term),
            COALESCE(jurisdiction_id, '00000000-0000-0000-0000-000000000000'::uuid)
          )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vocab_aliases_canonical "
        "ON vocabulary_aliases (canonical_use_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_vocab_aliases_term_lower "
        "ON vocabulary_aliases (lower(jurisdiction_specific_term))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_vocab_aliases_term_lower")
    op.execute("DROP INDEX IF EXISTS idx_vocab_aliases_canonical")
    op.execute("DROP TABLE IF EXISTS vocabulary_aliases")
