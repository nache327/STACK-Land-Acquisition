"""Extend classification_source enum with llm_low_confidence and llm_rule values

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-23 00:00:00.000000

llm_low_confidence: LLM ran but returned confidence < 0.70 — needs human verification
llm_rule: LLM ran; unclear slots were filled by the rule-based classifier
"""
from alembic import op


# revision identifiers
revision = "0009"
down_revision = "0008b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL ADD VALUE is append-only and safe — no table rewrite, no downtime.
    # Values are only added if they don't already exist (idempotent via DO $$).
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'llm_low_confidence'
                  AND enumtypid = 'classification_source_enum'::regtype
            ) THEN
                ALTER TYPE classification_source_enum ADD VALUE 'llm_low_confidence';
            END IF;
        END$$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'llm_rule'
                  AND enumtypid = 'classification_source_enum'::regtype
            ) THEN
                ALTER TYPE classification_source_enum ADD VALUE 'llm_rule';
            END IF;
        END$$;
    """)


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — downgrade is a no-op.
    pass
