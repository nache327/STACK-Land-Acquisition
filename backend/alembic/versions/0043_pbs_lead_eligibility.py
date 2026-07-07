"""Add lead-eligibility + verdict-basis columns to parcel_buybox_scores.

Why (catch #49 enforcement, approved 2026-07-07):
    The scoring feed served heuristic zone_use_matrix verdicts identically to
    human-grounded ones — the digest scored three heuristic-only parcels 96-98
    while human-verified rows were storage-dead. Every served score row now
    carries:
        lead_eligible  — false when the verdict rests on a non-grounded source
                         (demote-don't-delete: the row still serves, dimmed)
        gate_reason    — 'heuristic_source' | 'low_confidence' |
                         'unclear_verdict' (NULL when eligible)
        verdict_basis  — 'human-verified' | 'ordinance-parsed' | 'heuristic'
                         | 'ungrounded muni' (always set; the honesty tag)

    Values are computed by app/services/verdict_gate.py at scoring time; no
    backfill here — the next scoring pass populates them (rows with NULLs
    read as not-yet-rescored).

Operational shape: three nullable ADD COLUMNs, no defaults, no backfill —
metadata-only and boot-safe (see 0042's authoring rules).

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET statement_timeout = 0")
    op.execute(
        "ALTER TABLE parcel_buybox_scores "
        "ADD COLUMN IF NOT EXISTS lead_eligible BOOLEAN NULL"
    )
    op.execute(
        "ALTER TABLE parcel_buybox_scores "
        "ADD COLUMN IF NOT EXISTS gate_reason VARCHAR(32) NULL"
    )
    op.execute(
        "ALTER TABLE parcel_buybox_scores "
        "ADD COLUMN IF NOT EXISTS verdict_basis VARCHAR(32) NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE parcel_buybox_scores DROP COLUMN IF EXISTS verdict_basis")
    op.execute("ALTER TABLE parcel_buybox_scores DROP COLUMN IF EXISTS gate_reason")
    op.execute("ALTER TABLE parcel_buybox_scores DROP COLUMN IF EXISTS lead_eligible")
