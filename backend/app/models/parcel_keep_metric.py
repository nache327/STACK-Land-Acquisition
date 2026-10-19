from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ParcelKeepMetric(Base):
    """Garage-condo (LGC) keep-market metrics per candidate parcel.

    Wealth DEPTH within a 20-minute drive + drive time to the nearest $1M+ cluster,
    and the lane / price band / velocity flag derived from them by
    ``app.services.keep_market`` (the single source of the lane rules). Populated by
    ``scripts/precompute_keep_metrics.py`` (tract-clustered, like the ring precompute).
    Read by the LGC lane only — storage scoring and needles never join this table.
    """
    __tablename__ = "parcel_keep_metrics"
    __table_args__ = (
        Index("ix_parcel_keep_metrics_tract", "tract_geoid"),
    )

    parcel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("parcels.id", ondelete="CASCADE"), primary_key=True
    )
    tract_geoid: Mapped[str | None] = mapped_column(Text, nullable=True)
    hh_200k_20: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_1m_count_20: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_1m_share_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    seasonal_share_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    young_old_200k_ratio_20: Mapped[float | None] = mapped_column(Float, nullable=True)
    wealth_center_drive_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    wealth_center_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    wealth_center_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    county_home_ppsf: Mapped[float | None] = mapped_column(Float, nullable=True)
    keep_lane: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_band_low: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_band_high: Mapped[int | None] = mapped_column(Integer, nullable=True)
    velocity_flag: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Garage-condo units (built or planned) within ~30 min — info only (migration 0059;
    # filled by scripts/backfill_keep_competitors.py and precompute_keep_metrics.py).
    competitor_units_30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ParcelKeepMetric parcel={self.parcel_id} lane={self.keep_lane}>"
