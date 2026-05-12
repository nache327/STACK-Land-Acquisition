"""forsale_listings + notified_listings — Layer 4: For-Sale Listings

Source-agnostic listings table. Operators upload Excel/CSV exports
from CoStar / LoopNet / Crexi (parsers in app.services.listings_parsers)
which normalize provider-specific columns into the canonical shape
defined here. Match results live on the same row so a single SELECT
joins parcels → listing → broker info for emails and the map layer.

Uniqueness on (jurisdiction_id, source, address, sale_status):
the same property listed on CoStar AND LoopNet is intentionally two
rows. Cross-source dedup is a future problem.

notified_listings tracks "this filter has already been alerted about
this listing" so re-uploading the same file doesn't blast the user
with duplicate \U0001f525 emails. Distinct from
ParcelBuyboxScore.notified_at which dedups the *daily digest* path.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "forsale_listings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("jurisdiction_id", UUID(as_uuid=True),
                  sa.ForeignKey("jurisdictions.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_file", sa.Text, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),

        # Canonical normalized fields
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("city", sa.Text, nullable=True),
        sa.Column("state", sa.Text, nullable=True),
        sa.Column("zip", sa.Text, nullable=True),
        sa.Column("sale_status", sa.Text, nullable=False),
        sa.Column("sale_category", sa.Text, nullable=True),
        sa.Column("property_type", sa.Text, nullable=True),
        sa.Column("secondary_type", sa.Text, nullable=True),
        sa.Column("rating", sa.SmallInteger, nullable=True),
        sa.Column("size_sf", sa.Numeric, nullable=True),
        sa.Column("sale_price", sa.Numeric, nullable=True),
        sa.Column("price_per_sf", sa.Numeric, nullable=True),
        sa.Column("cap_rate", sa.Numeric, nullable=True),
        sa.Column("days_on_market", sa.Integer, nullable=True),
        sa.Column("sale_type", sa.Text, nullable=True),
        sa.Column("property_name", sa.Text, nullable=True),
        sa.Column("land_area_ac", sa.Numeric, nullable=True),
        sa.Column("land_area_sf", sa.Numeric, nullable=True),
        sa.Column("price_per_ac", sa.Numeric, nullable=True),
        sa.Column("price_per_land_sf", sa.Numeric, nullable=True),
        sa.Column("num_units", sa.Integer, nullable=True),
        sa.Column("price_per_unit", sa.Numeric, nullable=True),
        sa.Column("listing_broker_company", sa.Text, nullable=True),
        sa.Column("listing_broker_contact", sa.Text, nullable=True),
        sa.Column("listing_broker_phone", sa.Text, nullable=True),
        sa.Column("listing_broker_email", sa.Text, nullable=True),
        sa.Column("building_class", sa.Text, nullable=True),
        sa.Column("zoning_listed", sa.Text, nullable=True),
        sa.Column("market", sa.Text, nullable=True),
        sa.Column("submarket", sa.Text, nullable=True),
        sa.Column("county", sa.Text, nullable=True),
        sa.Column("raw_row", JSONB, nullable=False),

        # Match results
        sa.Column("matched_parcel_id", sa.BigInteger,
                  sa.ForeignKey("parcels.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("match_confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("match_method", sa.Text, nullable=True),
        sa.Column("geocoded_lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("geocoded_lon", sa.Numeric(10, 7), nullable=True),

        # Lifecycle
        sa.Column("is_current", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("dropped_at", sa.DateTime(timezone=True), nullable=True),

        sa.UniqueConstraint(
            "jurisdiction_id", "source", "address", "sale_status",
            name="uq_forsale_listings_juris_source_addr_status",
        ),
    )
    op.create_index(
        "ix_forsale_listings_matched_parcel",
        "forsale_listings", ["matched_parcel_id"],
    )
    op.create_index(
        "ix_forsale_listings_juris_current",
        "forsale_listings", ["jurisdiction_id", "is_current"],
    )
    op.create_index(
        "ix_forsale_listings_raw_row",
        "forsale_listings", ["raw_row"],
        postgresql_using="gin",
    )

    op.create_table(
        "notified_listings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("filter_id", UUID(as_uuid=True),
                  sa.ForeignKey("buybox_filters.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("listing_id", UUID(as_uuid=True),
                  sa.ForeignKey("forsale_listings.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("parcel_id", sa.BigInteger,
                  sa.ForeignKey("parcels.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("filter_id", "listing_id",
                            name="uq_notified_listings_filter_listing"),
    )
    op.create_index(
        "ix_notified_listings_filter",
        "notified_listings", ["filter_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notified_listings_filter", table_name="notified_listings")
    op.drop_table("notified_listings")
    op.drop_index("ix_forsale_listings_raw_row", table_name="forsale_listings")
    op.drop_index("ix_forsale_listings_juris_current", table_name="forsale_listings")
    op.drop_index("ix_forsale_listings_matched_parcel", table_name="forsale_listings")
    op.drop_table("forsale_listings")
