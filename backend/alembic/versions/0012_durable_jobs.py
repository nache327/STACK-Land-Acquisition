"""Add durable job worker tables and operational fields

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-28 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for value in ("queued", "running", "retrying", "cancelled"):
        op.execute(f"ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("jobs", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("jobs", sa.Column("dedupe_key", sa.String(length=768), nullable=True))
    op.add_column("jobs", sa.Column("locked_by", sa.String(length=128), nullable=True))
    op.add_column("jobs", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_jobs_dedupe_key", "jobs", ["dedupe_key"])
    # Dedupe only against non-terminal jobs. We use finished_at IS NULL here
    # rather than `status NOT IN (terminal)` because Postgres requires functions
    # in index predicates to be IMMUTABLE — the implicit `enum::text` cast is
    # not, and newly-added enum values (`cancelled`) are not visible in the
    # same transaction. finished_at sidesteps both problems.
    op.create_index(
        "uq_jobs_active_dedupe_key",
        "jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL AND finished_at IS NULL"),
    )

    op.create_table(
        "job_steps",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("step", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=2048), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_steps_job_id", "job_steps", ["job_id"])
    op.create_index("ix_job_steps_step", "job_steps", ["step"])
    op.create_index("ix_job_steps_status", "job_steps", ["status"])

    op.create_table(
        "job_artifacts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step", sa.String(length=128), nullable=False),
        sa.Column("artifact_type", sa.String(length=128), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("storage_uri", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_artifacts_job_id", "job_artifacts", ["job_id"])
    op.create_index("ix_job_artifacts_step", "job_artifacts", ["step"])
    op.create_index("ix_job_artifacts_artifact_type", "job_artifacts", ["artifact_type"])


def downgrade() -> None:
    op.drop_index("ix_job_artifacts_artifact_type", table_name="job_artifacts")
    op.drop_index("ix_job_artifacts_step", table_name="job_artifacts")
    op.drop_index("ix_job_artifacts_job_id", table_name="job_artifacts")
    op.drop_table("job_artifacts")
    op.drop_index("ix_job_steps_status", table_name="job_steps")
    op.drop_index("ix_job_steps_step", table_name="job_steps")
    op.drop_index("ix_job_steps_job_id", table_name="job_steps")
    op.drop_table("job_steps")
    op.drop_index("uq_jobs_active_dedupe_key", table_name="jobs")
    op.drop_index("ix_jobs_dedupe_key", table_name="jobs")
    for column in (
        "attempts",
        "locked_at",
        "locked_by",
        "dedupe_key",
        "force",
        "cancel_requested_at",
        "finished_at",
        "started_at",
        "queued_at",
    ):
        op.drop_column("jobs", column)
