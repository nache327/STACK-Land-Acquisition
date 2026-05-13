"""For-sale listing — source-agnostic snapshot of a property currently
listed (or recently listed) for sale.

One row per (jurisdiction, source, address, sale_status). A property
listed on both CoStar and LoopNet produces two rows on purpose so each
provider's broker info and update cadence is preserved. Cross-source
dedup is a future concern.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ForsaleListing(Base):
    __tablename__ = "forsale_listings"
    __table_args__ = (
        UniqueConstraint(
            "jurisdiction_id", "source", "address", "sale_status",
            name="uq_forsale_listings_juris_source_addr_status",
        ),
        Index("ix_forsale_listings_matched_parcel", "matched_parcel_id"),
        Index("ix_forsale_listings_juris_current", "jurisdiction_id", "is_current"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    zip: Mapped[str | None] = mapped_column(Text, nullable=True)
    sale_status: Mapped[str] = mapped_column(Text, nullable=False)
    sale_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    property_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    secondary_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    size_sf: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    price_per_sf: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    cap_rate: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    days_on_market: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sale_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    property_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    land_area_ac: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    land_area_sf: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    price_per_ac: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    price_per_land_sf: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    num_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_per_unit: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    listing_broker_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_broker_contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_broker_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_broker_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    building_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    zoning_listed: Mapped[str | None] = mapped_column(Text, nullable=True)
    market: Mapped[str | None] = mapped_column(Text, nullable=True)
    submarket: Mapped[str | None] = mapped_column(Text, nullable=True)
    county: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row: Mapped[dict] = mapped_column(JSONB, nullable=False)

    matched_parcel_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("parcels.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    match_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    geocoded_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    geocoded_lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    # Populated when the nearest-parcel tier finds multiple adjacent
    # parcels sharing the primary parcel's owner_name (i.e. an owner
    # selling two+ lots together). Each entry: {id, apn, acres, is_primary}.
    # Primary = the largest-acreage parcel (matched_parcel_id points to it).
    co_listed_parcels: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    dropped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    jurisdiction: Mapped["Jurisdiction"] = relationship(lazy="select")  # noqa: F821
    matched_parcel: Mapped["Parcel | None"] = relationship(lazy="select")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ForsaleListing {self.source}:{self.address} {self.sale_status}>"
