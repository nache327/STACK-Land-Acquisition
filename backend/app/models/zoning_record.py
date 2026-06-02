import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ZoningRule(Base):
    __tablename__ = "zoning_rules"
    __table_args__ = (
        Index("ix_zoning_rules_city", "city"),
        Index("ix_zoning_rules_zone_code", "zone_code"),
        Index("uq_zoning_rules_city_zone_code", "city", "zone_code", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city: Mapped[str] = mapped_column(Text, nullable=False)
    zone_code: Mapped[str] = mapped_column(Text, nullable=False)
    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_lot_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    setbacks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    height_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    overlays: Mapped[list["ZoningOverlay"]] = relationship(back_populates="zoning_rule")


class ZoningOverlay(Base):
    __tablename__ = "zoning_overlays"
    __table_args__ = (
        Index("ix_zoning_overlays_parcel_id", "parcel_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # No inline index=True here — the explicit Index("ix_zoning_overlays_parcel_id")
    # in __table_args__ above already covers this column. Declaring both causes
    # Base.metadata.create_all to emit the same CREATE INDEX twice (duplicate
    # default name) and fail with DuplicateTableError, which broke every test
    # that consumed the db_engine fixture.
    parcel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parcels.id", ondelete="CASCADE"),
        nullable=False,
    )
    zoning_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zoning_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    parcel: Mapped["Parcel"] = relationship()  # type: ignore[name-defined]  # noqa: F821
    zoning_rule: Mapped[ZoningRule | None] = relationship(back_populates="overlays")


class EnrichmentCache(Base):
    __tablename__ = "enrichment_cache"
    __table_args__ = (
        Index("ix_enrichment_cache_parcel_id", "parcel_id"),
        Index("uq_enrichment_cache_parcel_id", "parcel_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # No inline index=True — see ZoningOverlay above; same duplicate-index bug.
    parcel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parcels.id", ondelete="CASCADE"),
        nullable=False,
    )
    zoning_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    slope: Mapped[float | None] = mapped_column(Float, nullable=True)
    flood_zone: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    parcel: Mapped["Parcel"] = relationship()  # type: ignore[name-defined]  # noqa: F821
