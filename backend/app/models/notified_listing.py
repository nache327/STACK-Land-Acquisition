"""Tracks which (filter, listing) pairs have already triggered a
"new listing match" alert email. Prevents re-alerting on the same
listing across multiple uploads.

Distinct from ``ParcelBuyboxScore.notified_at`` — that column gates
the *nightly digest* path (one row per (parcel, filter)). This table
gates the *immediate listing-alert* path (one row per (filter, listing)).
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NotifiedListing(Base):
    __tablename__ = "notified_listings"
    __table_args__ = (
        UniqueConstraint("filter_id", "listing_id",
                         name="uq_notified_listings_filter_listing"),
        Index("ix_notified_listings_filter", "filter_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    filter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("buybox_filters.id", ondelete="CASCADE"),
        nullable=False,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("forsale_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    parcel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parcels.id", ondelete="CASCADE"),
        nullable=False,
    )
    notified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
