"""Add zoning_districts table and zone_class_enum

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-20 00:00:00.000000
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ZONE_CLASS_VALUES = (
    "residential",
    "commercial",
    "industrial",
    "mixed_use",
    "agricultural",
    "open_space",
    "special",
    "overlay",
    "unknown",
)

ZONE_SOURCE_VALUES = ("arcgis", "ordinance", "regrid", "manual")


def upgrade() -> None:
    zone_class_enum = postgresql.ENUM(*ZONE_CLASS_VALUES, name="zone_class_enum")
    zone_source_enum = postgresql.ENUM(*ZONE_SOURCE_VALUES, name="zone_source_enum")
    zone_class_enum.create(op.get_bind(), checkfirst=True)
    zone_source_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "zoning_districts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("zone_code", sa.String(100), nullable=False),
        sa.Column("zone_name", sa.String(255), nullable=True),
        sa.Column(
            "zone_class",
            postgresql.ENUM(
                *ZONE_CLASS_VALUES, name="zone_class_enum", create_type=False
            ),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("allowed_uses", postgresql.JSONB(), nullable=True),
        sa.Column("max_far", sa.Numeric(5, 2), nullable=True),
        sa.Column("max_height_ft", sa.Numeric(6, 1), nullable=True),
        sa.Column("max_density_dua", sa.Numeric(7, 2), nullable=True),
        sa.Column("min_lot_area_sqft", sa.Numeric(10, 0), nullable=True),
        sa.Column("raw_attributes", postgresql.JSONB(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="GEOMETRY", srid=4326),
            nullable=True,
        ),
        sa.Column(
            "centroid",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column(
            "source",
            postgresql.ENUM(
                *ZONE_SOURCE_VALUES, name="zone_source_enum", create_type=False
            ),
            nullable=False,
            server_default="arcgis",
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column(
            "human_reviewed",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        # Hash of geometry WKB; lets us de-dupe without relying on polygon equality.
        sa.Column("geom_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "jurisdiction_id",
            "zone_code",
            "geom_hash",
            name="uq_zoning_districts_jur_code_hash",
        ),
    )
    op.create_index(
        "ix_zoning_districts_jurisdiction_code",
        "zoning_districts",
        ["jurisdiction_id", "zone_code"],
    )
    op.create_index(
        "ix_zoning_districts_jurisdiction_class",
        "zoning_districts",
        ["jurisdiction_id", "zone_class"],
    )
    op.create_index(
        "ix_zoning_districts_geom",
        "zoning_districts",
        ["geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_zoning_districts_centroid",
        "zoning_districts",
        ["centroid"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_zoning_districts_centroid", table_name="zoning_districts")
    op.drop_index("ix_zoning_districts_geom", table_name="zoning_districts")
    op.drop_index(
        "ix_zoning_districts_jurisdiction_class", table_name="zoning_districts"
    )
    op.drop_index(
        "ix_zoning_districts_jurisdiction_code", table_name="zoning_districts"
    )
    op.drop_table("zoning_districts")
    op.execute("DROP TYPE IF EXISTS zone_source_enum")
    op.execute("DROP TYPE IF EXISTS zone_class_enum")
