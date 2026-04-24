import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.zoning_district import ZoneClass


class ParcelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jurisdiction_id: uuid.UUID
    apn: str
    address: str | None
    owner_name: str | None
    acres: float | None
    zoning_code: str | None
    zone_class: ZoneClass | None = None
    land_use_code: str | None
    improvement_value: float | None
    has_structure: bool | None
    in_flood_zone: bool
    avg_slope_pct: float | None
    in_wetland: bool
    county_link: str | None
    storage_permission: str | None = None
    created_at: datetime
    updated_at: datetime


class ParcelDetail(ParcelRead):
    """Includes raw source row — only fetched in drawer view."""
    raw: dict[str, Any] | None = None


class ParcelListResponse(BaseModel):
    items: list[ParcelRead]
    total: int
    page: int
    page_size: int


class ParcelFilter(BaseModel):
    zones: list[str] | None = None
    zone_classes: list[str] | None = None
    min_acres: float | None = Field(None, ge=0)
    max_acres: float | None = Field(None, ge=0)
    exclude_flood: bool = False
    exclude_wetland: bool = False
    vacant_only: bool = False
    bbox: list[float] | None = Field(
        None,
        description="[min_lng, min_lat, max_lng, max_lat]",
        min_length=4,
        max_length=4,
    )
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)
