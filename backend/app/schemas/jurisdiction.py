import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.jurisdiction import CoverageLevel, ParcelSource


class JurisdictionBase(BaseModel):
    name: str
    state: str
    county: str | None = None
    parcel_source: ParcelSource | None = None
    parcel_endpoint: str | None = None
    zoning_endpoint: str | None = None
    ordinance_url: str | None = None


class JurisdictionCreate(JurisdictionBase):
    pass


class JurisdictionRead(JurisdictionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    coverage_level: CoverageLevel | None = None
    bbox: list[float] | None = None
    last_indexed_at: datetime | None
    created_at: datetime


class JurisdictionList(BaseModel):
    items: list[JurisdictionRead]
    total: int
