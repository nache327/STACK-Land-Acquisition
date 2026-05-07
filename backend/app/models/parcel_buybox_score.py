import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ParcelBuyboxScore(Base):
    """Server-side composite score for a parcel under a specific buy-box filter.

    Replaces the placeholder browser-side `computeScore` in
    `frontend/lib/compositeScore.ts`. The scoring engine writes one row
    per (parcel, buybox_filter) pair and the dashboard reads from here.

    `factors` is a JSONB array of {label, delta, reason} objects so the
    frontend can show the same per-factor breakdown that the placeholder
    showed — same shape, just sourced from the server.
    """
    __tablename__ = "parcel_buybox_scores"
    __table_args__ = (
        PrimaryKeyConstraint("parcel_id", "buybox_filter_id", name="pk_parcel_buybox_scores"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_parcel_buybox_scores_range"),
        # Hot read pattern: top-N parcels for a given filter.
        Index("ix_pbs_filter_score", "buybox_filter_id", text("score DESC")),
    )

    parcel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parcels.id", ondelete="CASCADE"),
        nullable=False,
    )
    buybox_filter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("buybox_filters.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    factors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    filter: Mapped["BuyboxFilter"] = relationship(  # noqa: F821
        back_populates="scores"
    )

    def __repr__(self) -> str:
        return f"<ParcelBuyboxScore parcel={self.parcel_id} score={self.score} tier={self.tier}>"
