import enum
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ZoneClass(str, enum.Enum):
    residential = "residential"
    commercial = "commercial"
    industrial = "industrial"
    mixed_use = "mixed_use"
    agricultural = "agricultural"
    open_space = "open_space"
    special = "special"
    overlay = "overlay"
    unknown = "unknown"


class ZoneSource(str, enum.Enum):
    arcgis = "arcgis"
    ordinance = "ordinance"
    regrid = "regrid"
    manual = "manual"


class ZoningDistrict(Base):
    __tablename__ = "zoning_districts"
    __table_args__ = (
        UniqueConstraint(
            "jurisdiction_id",
            "zone_code",
            "geom_hash",
            name="uq_zoning_districts_jur_code_hash",
        ),
        Index(
            "ix_zoning_districts_jurisdiction_code",
            "jurisdiction_id",
            "zone_code",
        ),
        Index(
            "ix_zoning_districts_jurisdiction_class",
            "jurisdiction_id",
            "zone_class",
        ),
        Index(
            "ix_zoning_districts_geom",
            "geom",
            postgresql_using="gist",
        ),
        Index(
            "ix_zoning_districts_centroid",
            "centroid",
            postgresql_using="gist",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=False,
    )
    zone_code: Mapped[str] = mapped_column(String(100), nullable=False)
    zone_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    zone_class: Mapped[ZoneClass] = mapped_column(
        Enum(ZoneClass, name="zone_class_enum", create_constraint=False),
        nullable=False,
        default=ZoneClass.unknown,
    )

    allowed_uses: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    max_far: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    max_height_ft: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    max_density_dua: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)
    min_lot_area_sqft: Mapped[float | None] = mapped_column(Numeric(10, 0), nullable=True)

    raw_attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    geom = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=True)
    centroid = mapped_column(Geometry("POINT", srid=4326), nullable=True)

    source: Mapped[ZoneSource] = mapped_column(
        Enum(ZoneSource, name="zone_source_enum", create_constraint=False),
        nullable=False,
        default=ZoneSource.arcgis,
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    human_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    geom_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
        back_populates="zoning_districts"
    )

    def __repr__(self) -> str:
        return f"<ZoningDistrict {self.zone_code} ({self.zone_class})>"
