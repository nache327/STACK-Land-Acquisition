"""zoning_sources — durable registry of candidate + verified zoning sources

Today zoning-source discovery results are ephemeral: `_discover-zoning`
returns ranked candidates but doesn't persist them. Operators have to
re-run the discovery + re-eyeball candidates each time, and there's no
audit trail of which source was eventually picked + verified.

This table records every candidate from the discovery engine (with
confidence + reasoning), supports per-municipality entries for NJ-style
work (where one county's zoning is split across many towns), and tracks
validation state so the operator knows what's been tried + what's still
pending review.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zoning_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("jurisdiction_id", UUID(as_uuid=True),
                  sa.ForeignKey("jurisdictions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("municipality_name", sa.Text, nullable=True),
        sa.Column("county", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("parcel_endpoint", sa.Text, nullable=True),
        sa.Column("zoning_endpoint", sa.Text, nullable=True),
        sa.Column("shapefile_url", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("feature_count", sa.Integer, nullable=True),
        sa.Column("geometry_type", sa.Text, nullable=True),
        sa.Column("field_matches", JSONB, nullable=True),
        sa.Column("confidence_score", sa.Integer, nullable=True),
        sa.Column("confidence_label", sa.Text, nullable=True),
        sa.Column("validation_status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("discovered_by", sa.Text, nullable=True),
        sa.Column("reasons", JSONB, nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_zoning_sources_jurisdiction", "zoning_sources", ["jurisdiction_id"])
    op.create_index(
        "ix_zoning_sources_state_county_muni",
        "zoning_sources",
        ["state", "county", "municipality_name"],
    )
    op.create_index(
        "ix_zoning_sources_validation_status",
        "zoning_sources",
        ["validation_status", "confidence_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_zoning_sources_validation_status", table_name="zoning_sources")
    op.drop_index("ix_zoning_sources_state_county_muni", table_name="zoning_sources")
    op.drop_index("ix_zoning_sources_jurisdiction", table_name="zoning_sources")
    op.drop_table("zoning_sources")
