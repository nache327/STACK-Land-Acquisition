import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CompetitorFacility(Base):
    __tablename__ = "competitor_facilities"
    __table_args__ = (
        Index("ix_competitor_facilities_geom", "geom", postgresql_using="gist"),
        Index("ix_competitor_facilities_jurisdiction", "jurisdiction_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(512), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sq_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sqft_source: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    data_source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    geom = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<CompetitorFacility {self.name!r} src={self.data_source}>"
