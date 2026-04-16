import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ParcelSource(str, enum.Enum):
    city_gis = "city_gis"
    county_gis = "county_gis"
    regrid = "regrid"


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    county: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parcel_source: Mapped[ParcelSource | None] = mapped_column(
        Enum(ParcelSource, name="parcel_source_enum"), nullable=True
    )
    parcel_endpoint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    zoning_endpoint: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ordinance_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships (populated in Phase 2+)
    parcels: Mapped[list["Parcel"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="jurisdiction", lazy="select"
    )
    zone_matrix: Mapped[list["ZoneUseMatrix"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="jurisdiction", lazy="select"
    )
    jobs: Mapped[list["Job"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="jurisdiction", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Jurisdiction {self.name} ({self.state})>"
