"""Add 'crosswalk' + 'inherited_pending' to classification_source_enum,
and possible_lczo_codes TEXT[] to zone_use_matrix.

Why:
    Loudoun VA 1993-ordinance sprint promotes 18 pending codes by
    looking them up in the official 1993->LCZO crosswalk PDF and
    copying the LCZO equivalent's verdict. The audit trail needs:
      - classification_source='crosswalk' so the source of truth is
        the published crosswalk, not a direct ordinance read or LLM
      - classification_source='inherited_pending' so Town-of-* rows
        that defer to a per-town sprint are explicitly tagged
      - possible_lczo_codes TEXT[] so 1:many crosswalk mappings (one
        1993 code that splits into multiple LCZO districts) can
        carry the candidate set instead of silently picking one

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-21 13:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # ALTER TYPE ADD VALUE is non-transactional in Postgres.
    # Each statement gets its own AUTOCOMMIT execution.
    op.execute("COMMIT")
    op.execute("ALTER TYPE classification_source_enum ADD VALUE IF NOT EXISTS 'crosswalk'")
    op.execute("ALTER TYPE classification_source_enum ADD VALUE IF NOT EXISTS 'inherited_pending'")
    op.execute(
        "ALTER TABLE zone_use_matrix "
        "ADD COLUMN IF NOT EXISTS possible_lczo_codes TEXT[] NULL"
    )

def downgrade() -> None:
    # Postgres doesn't support removing enum values cleanly.
    # Downgrade only drops the column.
    op.execute("ALTER TABLE zone_use_matrix DROP COLUMN IF EXISTS possible_lczo_codes")
