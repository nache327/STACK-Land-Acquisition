import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OverlayType(str, enum.Enum):
    flood_sfha = "flood_sfha"
    wetland_nwi = "wetland_nwi"
    historic_district = "historic_district"
    opportunity_zone = "opportunity_zone"
    zoning_overlay = "zoning_overlay"
    special_purpose_district = "special_purpose_district"
    steep_slope = "steep_slope"


class Overlay(Base):
    __tablename__ = "overlays"
    __table_args__ = (
        Index(
            "ix_overlays_type_jurisdiction",
            "overlay_type",
            "jurisdiction_id",
        ),
        Index(
            "ix_overlays_geom",
            "geom",
            postgresql_using="gist",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=True,
    )
    overlay_type: Mapped[OverlayType] = mapped_column(
        Enum(OverlayType, name="overlay_type_enum", create_constraint=False),
        nullable=False,
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    geom = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Overlay {self.overlay_type} j={self.jurisdiction_id}>"
