"""Precomputed wealth-gated needle metrics, one current row per jurisdiction.

The needle count (grounded verdict + wealth ring + acreage) is a heavy per-parcel
matrix LATERAL, so it's computed nightly by ``scripts/precompute_needles.py`` and
read cheaply here by the in-app needles-by-county view. Upserted (PK =
jurisdiction_id): the table always holds the latest snapshot, not a time series.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NeedleSnapshot(Base):
    __tablename__ = "needle_snapshot"

    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    jurisdiction_name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str | None] = mapped_column(String)
    # Wealth-gated (acres>=1.5, dt10 ring HV>=475k & HHI>=100k, human-reviewed).
    storage_needles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lgc_needles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # LGC-viable AND storage-NOT-viable — the pool the storage lane never shows.
    lgc_incremental: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Current CoStar listings sitting on a needle parcel (actionable now).
    storage_deals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lgc_deals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
