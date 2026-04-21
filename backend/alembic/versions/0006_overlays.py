"""Add overlays table + per-type views for pg_tileserv

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-20 00:00:03.000000
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OVERLAY_TYPE_VALUES = (
    "flood_sfha",
    "wetland_nwi",
    "historic_district",
    "opportunity_zone",
    "zoning_overlay",
    "special_purpose_district",
    "steep_slope",
)

# Views exposed via pg_tileserv (one per overlay type). Published layers become
# /public.{view_name}/{z}/{x}/{y}.pbf automatically.
_VIEWS = [
    ("overlays_flood_sfha", "flood_sfha"),
    ("overlays_wetland_nwi", "wetland_nwi"),
    ("overlays_historic_district", "historic_district"),
    ("overlays_opportunity_zone", "opportunity_zone"),
    ("overlays_zoning_overlay", "zoning_overlay"),
    ("overlays_special_purpose_district", "special_purpose_district"),
    ("overlays_steep_slope", "steep_slope"),
]


def upgrade() -> None:
    overlay_enum = postgresql.ENUM(*OVERLAY_TYPE_VALUES, name="overlay_type_enum")
    overlay_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "overlays",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        # Nullable — some overlays (e.g., FEMA nationwide) don't belong to one jurisdiction.
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "overlay_type",
            postgresql.ENUM(
                *OVERLAY_TYPE_VALUES,
                name="overlay_type_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="GEOMETRY", srid=4326),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_overlays_type_jurisdiction",
        "overlays",
        ["overlay_type", "jurisdiction_id"],
    )
    op.create_index(
        "ix_overlays_geom", "overlays", ["geom"], postgresql_using="gist"
    )

    # Per-type views so pg_tileserv publishes each overlay as its own tile layer.
    for view_name, overlay_type in _VIEWS:
        op.execute(
            f"""
            CREATE OR REPLACE VIEW {view_name} AS
            SELECT id, jurisdiction_id, source, attributes, geom, fetched_at
            FROM overlays
            WHERE overlay_type = '{overlay_type}'
            """
        )


def downgrade() -> None:
    for view_name, _ in _VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {view_name}")
    op.drop_index("ix_overlays_geom", table_name="overlays")
    op.drop_index("ix_overlays_type_jurisdiction", table_name="overlays")
    op.drop_table("overlays")
    op.execute("DROP TYPE IF EXISTS overlay_type_enum")
