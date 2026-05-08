import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, SmallInteger, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class BuyboxFilter(Base):
    """A saved buy-box filter set scoped to (organization, use_case).

    Replaces the localStorage `presets` blob. The scoring engine reads
    `filter_json` to evaluate each parcel and writes a row to
    parcel_buybox_scores per (parcel, filter).
    """
    __tablename__ = "buybox_filters"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "use_case_id", "name",
            name="uq_buybox_filters_org_use_name",
        ),
        Index("ix_buybox_filters_org_use", "organization_id", "use_case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    use_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("use_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    filter_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    daily_email_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    daily_email_top_n: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=10, server_default=text("10")
    )
    last_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship(  # noqa: F821
        back_populates="buybox_filters"
    )
    use_case: Mapped["UseCase"] = relationship(  # noqa: F821
        back_populates="buybox_filters"
    )
    scores: Mapped[list["ParcelBuyboxScore"]] = relationship(  # noqa: F821
        back_populates="filter", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BuyboxFilter name={self.name} org={self.organization_id}>"
