"""Server-side buy-box: organizations, use_cases, parcel_ring_metrics,
buybox_filters, parcel_buybox_scores

Foundation for moving buy-box state out of the browser (IndexedDB +
localStorage) into Postgres so it survives across devices and supports
multi-tenancy + scheduled scoring.

This migration is purely additive — it creates 5 new tables and 1
seed row (the default Organization). It does not modify any existing
table or column. Safe to run while parcel/zoning ingestion is in flight.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-07 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Stable UUIDs for seed rows so frontend can hardcode references during
# the bootstrap phase before real auth lands. Never reuse these UUIDs.
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
SELF_STORAGE_USE_CASE_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    # ── organizations ─────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("plan", sa.String(32), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    # ── use_cases ─────────────────────────────────────────────────────────
    # organization_id NULL = system-defined use case visible to all orgs.
    op.create_table(
        "use_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # use_keys tells the scorer which zone_use_matrix columns matter
        # for this use case, e.g. ['self_storage', 'mini_warehouse'] both
        # contribute to the same scoring permission lookup.
        sa.Column("use_keys", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    # Per-org slug uniqueness; system rows (organization_id IS NULL) get a
    # separate partial unique index.
    op.create_index(
        "uq_use_cases_org_slug",
        "use_cases",
        ["organization_id", "slug"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )
    op.create_index(
        "uq_use_cases_system_slug",
        "use_cases",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )

    # ── parcel_ring_metrics ───────────────────────────────────────────────
    # Precomputed demographic-ring data per parcel × drive-time. Replaces
    # the browser IndexedDB cache; lets the server score parcels without
    # the user's browser having to crunch isochrones.
    op.create_table(
        "parcel_ring_metrics",
        sa.Column("parcel_id", sa.BigInteger(),
                  sa.ForeignKey("parcels.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("drive_time_minutes", sa.Integer(), nullable=False),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("median_hhi", sa.Numeric(12, 2), nullable=True),
        sa.Column("median_home_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("hnw_households", sa.Integer(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("parcel_id", "drive_time_minutes",
                                name="pk_parcel_ring_metrics"),
    )
    op.create_index(
        "ix_parcel_ring_metrics_parcel",
        "parcel_ring_metrics",
        ["parcel_id"],
    )

    # ── buybox_filters ────────────────────────────────────────────────────
    # Saved filter sets per (org, use_case). Replaces the browser presets
    # in localStorage. The system default for each use_case lives here too
    # (organization_id can reference the default org row).
    op.create_table(
        "buybox_filters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("use_case_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("use_cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("filter_json", postgresql.JSONB(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "use_case_id", "name",
                            name="uq_buybox_filters_org_use_name"),
    )
    op.create_index(
        "ix_buybox_filters_org_use",
        "buybox_filters",
        ["organization_id", "use_case_id"],
    )
    # Enforce at most ONE default per (org, use_case) via partial unique index.
    op.create_index(
        "uq_buybox_filters_one_default",
        "buybox_filters",
        ["organization_id", "use_case_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )

    # ── parcel_buybox_scores ──────────────────────────────────────────────
    # Per-parcel composite scores keyed by (parcel, buybox_filter). One
    # row per scored parcel × filter combination. Cascade-deleted with
    # the parcel or filter.
    op.create_table(
        "parcel_buybox_scores",
        sa.Column("parcel_id", sa.BigInteger(),
                  sa.ForeignKey("parcels.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("buybox_filter_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("buybox_filters.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("factors", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("parcel_id", "buybox_filter_id",
                                name="pk_parcel_buybox_scores"),
        sa.CheckConstraint("score >= 0 AND score <= 100",
                           name="ck_parcel_buybox_scores_range"),
    )
    # Hot read pattern: top-N parcels for a given filter.
    op.create_index(
        "ix_pbs_filter_score",
        "parcel_buybox_scores",
        ["buybox_filter_id", sa.text("score DESC")],
    )

    # ── Seed: default org + system 'self_storage' use case ────────────────
    op.execute(sa.text(
        f"""
        INSERT INTO organizations (id, name, slug, plan)
        VALUES ('{DEFAULT_ORG_ID}'::uuid, 'Default Organization', 'default', 'free')
        ON CONFLICT (slug) DO NOTHING
        """
    ))
    op.execute(sa.text(
        f"""
        INSERT INTO use_cases (id, organization_id, slug, name, description, use_keys)
        VALUES (
            '{SELF_STORAGE_USE_CASE_ID}'::uuid,
            NULL,
            'self_storage',
            'Self-Storage',
            'Self-storage / mini-warehouse facility site selection',
            '["self_storage", "mini_warehouse"]'::jsonb
        )
        ON CONFLICT DO NOTHING
        """
    ))


def downgrade() -> None:
    # Drop in reverse FK dependency order.
    op.drop_index("ix_pbs_filter_score", table_name="parcel_buybox_scores")
    op.drop_table("parcel_buybox_scores")

    op.drop_index("uq_buybox_filters_one_default", table_name="buybox_filters")
    op.drop_index("ix_buybox_filters_org_use", table_name="buybox_filters")
    op.drop_table("buybox_filters")

    op.drop_index("ix_parcel_ring_metrics_parcel", table_name="parcel_ring_metrics")
    op.drop_table("parcel_ring_metrics")

    op.drop_index("uq_use_cases_system_slug", table_name="use_cases")
    op.drop_index("uq_use_cases_org_slug", table_name="use_cases")
    op.drop_table("use_cases")

    op.drop_table("organizations")
