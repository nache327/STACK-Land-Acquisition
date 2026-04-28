import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.zoning_district import ZoneClass


class Parcel(Base):
    __tablename__ = "parcels"
    __table_args__ = (
        Index("ix_parcels_jurisdiction_zoning", "jurisdiction_id", "zoning_code"),
        Index("ix_parcels_jurisdiction_zone_class", "jurisdiction_id", "zone_class"),
        Index("ix_parcels_apn", "apn"),
        Index("ix_parcels_geom", "geom", postgresql_using="gist"),
        Index("ix_parcels_centroid", "centroid", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    apn: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    lng: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    acres: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    zoning_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    zone_class: Mapped[ZoneClass | None] = mapped_column(
        Enum(ZoneClass, name="zone_class_enum", create_constraint=False),
        nullable=True,
    )
    land_use_code: Mapped[str | None] = mapped_column(String(512), nullable=True)
    improvement_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    has_structure: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    in_flood_zone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    avg_slope_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    in_wetland: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    county_link: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # PostGIS geometry columns — GEOMETRY (not POLYGON) to accept MultiPolygon
    geom = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)
    centroid = mapped_column(Geometry("POINT", srid=4326), nullable=True)

    # Full source row from ArcGIS / Regrid
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    jurisdiction: Mapped["Jurisdiction"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="parcels"
    )

    def __repr__(self) -> str:
        return f"<Parcel apn={self.apn} zone={self.zoning_code}>"
