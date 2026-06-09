"""Add op5_factory + op5_factory_catchall to classification_source_enum.

Why:
    The Op-5 factory (PR #178 op5_per_muni_runner) tags generated
    zone_use_matrix rows ``classification_source='op5_factory_catchall'``
    (and grounded per-county rows will use ``'op5_factory'``). Neither
    value existed in ``classification_source_enum`` — so a factory matrix
    write would FAIL the enum on insert. This adds both, so factory rows
    are valid AND distinguishable from hand ``'human'`` rows for the
    coordination audit (see backend/docs/zone_matrix_write_contract.md).

    Pairs with the human_reviewed-skip write rule in
    app/services/zone_matrix_write.factory_safe_write (Adam-ack'd
    coordination proposal, 2026-06-08).

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-08 00:00:00.000000
"""
from alembic import op


revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL ADD VALUE is append-only and safe — no table rewrite,
    # no downtime. Idempotent via the DO $$ / IF NOT EXISTS guard
    # (mirrors migration 0009).
    for value in ("op5_factory", "op5_factory_catchall"):
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumlabel = '{value}'
                      AND enumtypid = 'classification_source_enum'::regtype
                ) THEN
                    ALTER TYPE classification_source_enum ADD VALUE '{value}';
                END IF;
            END$$;
        """)


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — downgrade is a no-op.
    pass
