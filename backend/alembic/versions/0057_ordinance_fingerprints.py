"""ordinance_fingerprints — primary-source freshness sentinel state

Verified verdicts rot silently: nothing detects that a grounded muni's
ordinance was amended after grounding (Chelmsford's CBLT district, the Hudson
recodification). This table holds one row per monitored ordinance URL with a
BASELINE fingerprint (host state at grounding) and a CURRENT fingerprint
(refreshed monthly by scripts/ordinance_sentinel.py off the watchdog tick).
Drift stamps drift_detected_at/drift_reason and routes the muni to human
re-verification — the sentinel monitors the PRIMARY host (eCode360 new-laws
badge + print-endpoint chapter hash; Municode latest-job id), never a vendor
mirror, which can only lag the host it scrapes.

Also adds ops_cron_heartbeat.sentinel_code so the tick's sentinel outcome is
observable next to watchdog/refresh/digest.

Light CREATE TABLE + idempotent ADD COLUMN — safe at Railway boot.

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ordinance_fingerprints",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "jurisdiction_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("municipality", sa.Text(), nullable=False),
        sa.Column("ordinance_url", sa.Text(), nullable=False, unique=True),
        sa.Column("host_kind", sa.String(20), nullable=True),
        sa.Column("municode_product_id", sa.Integer(), nullable=True),
        sa.Column("baseline_hash", sa.String(64), nullable=True),
        sa.Column("baseline_new_laws", sa.Integer(), nullable=True),
        sa.Column("baseline_job_id", sa.Text(), nullable=True),
        sa.Column("baseline_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_as_of", sa.Text(), nullable=True),
        sa.Column("current_hash", sa.String(64), nullable=True),
        sa.Column("current_new_laws", sa.Integer(), nullable=True),
        sa.Column("current_job_id", sa.Text(), nullable=True),
        sa.Column("codified_through", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetch_error", sa.Text(), nullable=True),
        sa.Column("drift_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drift_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    # Stalest-first work selection for the capped monthly tick.
    op.create_index(
        "ix_ordinance_fingerprints_fetched_at",
        "ordinance_fingerprints",
        [sa.text("fetched_at ASC NULLS FIRST")],
    )
    # The open re-verify queue.
    op.create_index(
        "ix_ordinance_fingerprints_drift",
        "ordinance_fingerprints",
        ["drift_detected_at"],
        postgresql_where=sa.text("drift_detected_at IS NOT NULL"),
    )
    op.execute(
        "ALTER TABLE ops_cron_heartbeat ADD COLUMN IF NOT EXISTS sentinel_code integer"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ops_cron_heartbeat DROP COLUMN IF EXISTS sentinel_code")
    op.drop_index("ix_ordinance_fingerprints_drift", table_name="ordinance_fingerprints")
    op.drop_index("ix_ordinance_fingerprints_fetched_at", table_name="ordinance_fingerprints")
    op.drop_table("ordinance_fingerprints")
