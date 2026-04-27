from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CensusTract(Base):
    __tablename__ = "census_tracts"
    __table_args__ = (
        Index("ix_census_tracts_geom", "geom", postgresql_using="gist"),
        Index("ix_census_tracts_state_county", "state_fips", "county_fips"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    geoid: Mapped[str] = mapped_column(String(11), nullable=False, unique=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    county_fips: Mapped[str] = mapped_column(String(3), nullable=False)
    tract_fips: Mapped[str] = mapped_column(String(6), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CensusTract {self.geoid} pop={self.population}>"
