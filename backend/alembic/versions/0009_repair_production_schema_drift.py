"""Repair production schema drift for zoning coverage recovery.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-21 00:00:01.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: Union[str, None] = "0008"
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
COVERAGE_LEVEL_VALUES = ("full", "zoning_only", "parcels_only", "partial")
OVERLAY_TYPE_VALUES = (
    "flood_sfha",
    "wetland_nwi",
    "historic_district",
    "opportunity_zone",
    "zoning_overlay",
    "special_purpose_district",
    "steep_slope",
)
OVERLAY_VIEWS = [
    ("overlays_flood_sfha", "flood_sfha"),
    ("overlays_wetland_nwi", "wetland_nwi"),
    ("overlays_historic_district", "historic_district"),
    ("overlays_opportunity_zone", "opportunity_zone"),
    ("overlays_zoning_overlay", "zoning_overlay"),
    ("overlays_special_purpose_district", "special_purpose_district"),
    ("overlays_steep_slope", "steep_slope"),
]


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names(schema="public")


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    zone_class_enum = postgresql.ENUM(*ZONE_CLASS_VALUES, name="zone_class_enum")
    zone_source_enum = postgresql.ENUM(*ZONE_SOURCE_VALUES, name="zone_source_enum")
    coverage_enum = postgresql.ENUM(*COVERAGE_LEVEL_VALUES, name="coverage_level_enum")
    overlay_enum = postgresql.ENUM(*OVERLAY_TYPE_VALUES, name="overlay_type_enum")

    zone_class_enum.create(bind, checkfirst=True)
    zone_source_enum.create(bind, checkfirst=True)
    coverage_enum.create(bind, checkfirst=True)
    overlay_enum.create(bind, checkfirst=True)

    if not _has_table(inspector, "zoning_districts"):
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
        inspector = inspect(bind)

    if not _has_index(inspector, "zoning_districts", "ix_zoning_districts_jurisdiction_code"):
        op.create_index(
            "ix_zoning_districts_jurisdiction_code",
            "zoning_districts",
            ["jurisdiction_id", "zone_code"],
        )
    if not _has_index(inspector, "zoning_districts", "ix_zoning_districts_jurisdiction_class"):
        op.create_index(
            "ix_zoning_districts_jurisdiction_class",
            "zoning_districts",
            ["jurisdiction_id", "zone_class"],
        )
    if not _has_index(inspector, "zoning_districts", "ix_zoning_districts_geom"):
        op.create_index(
            "ix_zoning_districts_geom",
            "zoning_districts",
            ["geom"],
            postgresql_using="gist",
        )
    if not _has_index(inspector, "zoning_districts", "ix_zoning_districts_centroid"):
        op.create_index(
            "ix_zoning_districts_centroid",
            "zoning_districts",
            ["centroid"],
            postgresql_using="gist",
        )

    inspector = inspect(bind)
    if not _has_column(inspector, "parcels", "zone_class"):
        op.add_column(
            "parcels",
            sa.Column(
                "zone_class",
                postgresql.ENUM(
                    *ZONE_CLASS_VALUES,
                    name="zone_class_enum",
                    create_type=False,
                ),
                nullable=True,
            ),
        )
    inspector = inspect(bind)
    if not _has_index(inspector, "parcels", "ix_parcels_jurisdiction_zone_class"):
        op.create_index(
            "ix_parcels_jurisdiction_zone_class",
            "parcels",
            ["jurisdiction_id", "zone_class"],
        )

    inspector = inspect(bind)
    if not _has_column(inspector, "jurisdictions", "coverage_level"):
        op.add_column(
            "jurisdictions",
            sa.Column(
                "coverage_level",
                postgresql.ENUM(
                    *COVERAGE_LEVEL_VALUES,
                    name="coverage_level_enum",
                    create_type=False,
                ),
                nullable=True,
            ),
        )
    inspector = inspect(bind)
    if not _has_column(inspector, "jurisdictions", "bbox"):
        op.add_column(
            "jurisdictions",
            sa.Column("bbox", postgresql.JSONB(), nullable=True),
        )

    inspector = inspect(bind)
    if not _has_table(inspector, "overlays"):
        op.create_table(
            "overlays",
            sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
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
        inspector = inspect(bind)

    if not _has_index(inspector, "overlays", "ix_overlays_type_jurisdiction"):
        op.create_index(
            "ix_overlays_type_jurisdiction",
            "overlays",
            ["overlay_type", "jurisdiction_id"],
        )
    if not _has_index(inspector, "overlays", "ix_overlays_geom"):
        op.create_index(
            "ix_overlays_geom",
            "overlays",
            ["geom"],
            postgresql_using="gist",
        )

    for view_name, overlay_type in OVERLAY_VIEWS:
        op.execute(
            f"""
            CREATE OR REPLACE VIEW {view_name} AS
            SELECT id, jurisdiction_id, source, attributes, geom, fetched_at
            FROM overlays
            WHERE overlay_type = '{overlay_type}'
            """
        )


def downgrade() -> None:
    # The repair migration intentionally acts as a one-way reconciliation step
    # for production drift. Downgrading would require destructive cleanup of
    # production data objects and is intentionally unsupported.
    pass
