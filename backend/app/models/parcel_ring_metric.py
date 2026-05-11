from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, PrimaryKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ParcelRingMetric(Base):
    """Precomputed demographic-ring metrics for a parcel × drive-time.

    Replaces the in-browser IndexedDB cache so server-side scoring can
    run without each user's browser having to crunch isochrones.
    """
    __tablename__ = "parcel_ring_metrics"
    __table_args__ = (
        PrimaryKeyConstraint("parcel_id", "drive_time_minutes", name="pk_parcel_ring_metrics"),
        Index("ix_parcel_ring_metrics_parcel", "parcel_id"),
    )

    parcel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parcels.id", ondelete="CASCADE"),
        nullable=False,
    )
    drive_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_hhi: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    median_home_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    hnw_households: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Wealth-density counts: residential parcels with total assessed value
    # >= 1M / 2M / 5M whose centroid falls inside this drive-time ring.
    # Lazily populated by POST /api/parcels/value-density.
    homes_over_1m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    homes_over_2m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    homes_over_5m: Mapped[int | None] = mapped_column(Integer, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ParcelRingMetric parcel={self.parcel_id} dt={self.drive_time_minutes}min>"
