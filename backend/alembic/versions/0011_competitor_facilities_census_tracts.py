"""Add competitor_facilities and census_tracts tables

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-27 00:00:00.000000
"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "competitor_facilities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(512), nullable=True),
        sa.Column("operator", sa.String(512), nullable=True),
        sa.Column("address", sa.String(512), nullable=True),
        # sq_ft = NULL means use the config default at query time; flagged as "estimated" in UI
        sa.Column("sq_ft", sa.Integer(), nullable=True),
        # How sq_ft was determined: 'building_area' | 'regrid' | 'default'
        sa.Column("sqft_source", sa.String(32), nullable=False, server_default="default"),
        # 'google_places' | 'kmz' | 'manual'
        sa.Column("data_source", sa.String(32), nullable=False),
        # Google Place ID or KMZ placemark ID — used for idempotent upserts
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Nullable — Google Places results are global, not scoped to one jurisdiction
        sa.Column(
            "jurisdiction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jurisdictions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_competitor_facilities_geom",
        "competitor_facilities",
        ["geom"],
        postgresql_using="gist",
    )
    # Functional geography index — critical for fast ST_DWithin radius queries
    op.execute(
        "CREATE INDEX ix_competitor_facilities_geog "
        "ON competitor_facilities USING GIST ((geom::geography))"
    )
    op.create_index(
        "ix_competitor_facilities_jurisdiction",
        "competitor_facilities",
        ["jurisdiction_id"],
    )
    # Unique on (data_source, external_id) for idempotent upserts
    op.execute(
        "CREATE UNIQUE INDEX uq_competitor_facilities_external_id "
        "ON competitor_facilities (data_source, external_id) "
        "WHERE external_id IS NOT NULL"
    )

    op.create_table(
        "census_tracts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        # 11-digit FIPS: state(2) + county(3) + tract(6)
        sa.Column("geoid", sa.String(11), nullable=False, unique=True),
        sa.Column("state_fips", sa.String(2), nullable=False),
        sa.Column("county_fips", sa.String(3), nullable=False),
        sa.Column("tract_fips", sa.String(6), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        # ACS B01003_001E total population estimate
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
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
        "ix_census_tracts_geom",
        "census_tracts",
        ["geom"],
        postgresql_using="gist",
    )
    op.create_index(
        "ix_census_tracts_state_county",
        "census_tracts",
        ["state_fips", "county_fips"],
    )

    # View for pg_tileserv so competitors render as a tile layer
    op.execute(
        """
        CREATE OR REPLACE VIEW competitor_facilities_view AS
        SELECT id, name, operator, address, sq_ft, sqft_source,
               data_source, attributes, geom, fetched_at, jurisdiction_id
        FROM competitor_facilities
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS competitor_facilities_view")
    op.drop_index("uq_competitor_facilities_external_id", table_name="competitor_facilities")
    op.drop_index("ix_competitor_facilities_geog", table_name="competitor_facilities")
    op.drop_index("ix_competitor_facilities_geom", table_name="competitor_facilities")
    op.drop_index("ix_competitor_facilities_jurisdiction", table_name="competitor_facilities")
    op.drop_table("competitor_facilities")
    op.drop_index("ix_census_tracts_geom", table_name="census_tracts")
    op.drop_index("ix_census_tracts_state_county", table_name="census_tracts")
    op.drop_table("census_tracts")
