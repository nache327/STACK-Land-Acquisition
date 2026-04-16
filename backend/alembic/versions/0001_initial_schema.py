"""Initial schema — jurisdictions, parcels, zone_use_matrix, jobs, shortlists

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # -- jurisdictions -------------------------------------------------------
    op.create_table(
        "jurisdictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("county", sa.String(255), nullable=True),
        sa.Column(
            "parcel_source",
            sa.Enum("city_gis", "county_gis", "regrid", name="parcel_source_enum"),
            nullable=True,
        ),
        sa.Column("parcel_endpoint", sa.String(1024), nullable=True),
        sa.Column("zoning_endpoint", sa.String(1024), nullable=True),
        sa.Column("ordinance_url", sa.String(1024), nullable=True),
        sa.Column(
            "last_indexed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -- parcels -------------------------------------------------------------
    op.create_table(
        "parcels",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("apn", sa.String(255), nullable=False),
        sa.Column("address", sa.String(512), nullable=True),
        sa.Column("owner_name", sa.String(512), nullable=True),
        sa.Column("acres", sa.Numeric(10, 3), nullable=True),
        sa.Column("zoning_code", sa.String(50), nullable=True),
        sa.Column("land_use_code", sa.String(100), nullable=True),
        sa.Column("improvement_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("has_structure", sa.Boolean(), nullable=True),
        sa.Column("in_flood_zone", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("avg_slope_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("in_wetland", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("county_link", sa.String(1024), nullable=True),
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
        sa.Column("raw", postgresql.JSONB(), nullable=True),
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
    )
    op.create_index("ix_parcels_jurisdiction_zoning", "parcels", ["jurisdiction_id", "zoning_code"])
    op.create_index("ix_parcels_apn", "parcels", ["apn"])
    op.create_index("ix_parcels_geom", "parcels", ["geom"], postgresql_using="gist")
    op.create_index("ix_parcels_centroid", "parcels", ["centroid"], postgresql_using="gist")

    # -- zone_use_matrix -----------------------------------------------------
    op.create_table(
        "zone_use_matrix",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("zone_code", sa.String(50), nullable=False),
        sa.Column("zone_name", sa.String(255), nullable=True),
        sa.Column(
            "self_storage",
            sa.Enum(
                "permitted", "conditional", "prohibited", "unclear",
                name="use_permission_enum",
            ),
            nullable=False,
            server_default="unclear",
        ),
        sa.Column(
            "mini_warehouse",
            sa.Enum("permitted", "conditional", "prohibited", "unclear",
                    name="use_permission_enum", create_constraint=False),
            nullable=False,
            server_default="unclear",
        ),
        sa.Column(
            "light_industrial",
            sa.Enum("permitted", "conditional", "prohibited", "unclear",
                    name="use_permission_enum", create_constraint=False),
            nullable=False,
            server_default="unclear",
        ),
        sa.Column(
            "luxury_garage_condo",
            sa.Enum("permitted", "conditional", "prohibited", "unclear",
                    name="use_permission_enum", create_constraint=False),
            nullable=False,
            server_default="unclear",
        ),
        sa.Column("citations", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("human_reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.String(2048), nullable=True),
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
        sa.UniqueConstraint("jurisdiction_id", "zone_code", name="uq_zone_matrix"),
    )
    op.create_index("ix_zone_matrix_jurisdiction", "zone_use_matrix", ["jurisdiction_id"])

    # -- jobs ----------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "discovering_layers",
                "downloading_parcels",
                "parsing_ordinance",
                "running_overlays",
                "ready",
                "failed",
                name="job_status_enum",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("jurisdiction_input", sa.String(512), nullable=True),
        sa.Column("ordinance_url", sa.String(1024), nullable=True),
        sa.Column("target_uses", postgresql.JSONB(), nullable=True),
        sa.Column("ordinance_pdf_path", sa.String(512), nullable=True),
        sa.Column("error_message", sa.String(2048), nullable=True),
        sa.Column("progress", postgresql.JSONB(), nullable=True),
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
    )
    op.create_index("ix_jobs_jurisdiction_id", "jobs", ["jurisdiction_id"])

    # -- shortlists ----------------------------------------------------------
    op.create_table(
        "shortlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("parcel_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
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
    )
    op.create_index("ix_shortlists_jurisdiction_id", "shortlists", ["jurisdiction_id"])


def downgrade() -> None:
    op.drop_table("shortlists")
    op.drop_table("jobs")
    op.drop_table("zone_use_matrix")
    op.drop_table("parcels")
    op.drop_table("jurisdictions")
    op.execute("DROP TYPE IF EXISTS job_status_enum")
    op.execute("DROP TYPE IF EXISTS use_permission_enum")
    op.execute("DROP TYPE IF EXISTS parcel_source_enum")
