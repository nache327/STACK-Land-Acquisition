import uuid
from datetime import datetime
from enum import Enum
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


class TargetUse(str, Enum):
    self_storage = "self_storage"


class ParcelSearchSort(str, Enum):
    acres_desc = "acres_desc"
    acres_asc = "acres_asc"
    apn_asc = "apn_asc"
    address_asc = "address_asc"


class CandidateParcelSearchFilters(BaseModel):
    zones: list[str] | None = None
    zone_classes: list[ZoneClass] | None = None
    storage_permissions: list[str] | None = None
    min_acres: float | None = Field(None, ge=0)
    max_acres: float | None = Field(None, ge=0)
    vacant_only: bool = False
    exclude_flood: bool = False
    exclude_wetland: bool = False


class CandidateParcelSearchRequest(BaseModel):
    jurisdiction_id: uuid.UUID
    target_use: TargetUse = TargetUse.self_storage
    filters: CandidateParcelSearchFilters = Field(default_factory=CandidateParcelSearchFilters)
    bbox: list[float] | None = Field(
        None,
        description="[xmin, ymin, xmax, ymax]",
        min_length=4,
        max_length=4,
    )
    search: str | None = Field(None, max_length=255)
    page: int = Field(1, ge=1)
    page_size: int = Field(100, ge=1, le=5000)
    sort: ParcelSearchSort = ParcelSearchSort.acres_desc


class CandidateParcelRow(BaseModel):
    parcel_id: int
    apn: str
    address: str | None
    acres: float | None
    zoning_code: str | None = None
    zone_class: ZoneClass | None = None
    storage_permission: str | None = None
    garage_permission: str | None = None
    storage_allowed: bool
    storage_conditional: bool
    in_flood_zone: bool
    in_wetland: bool
    has_structure: bool | None
    is_viable: bool
    violation_reasons: list[str]
    geom: dict[str, Any] | None = None


class CandidateParcelSearchResponse(BaseModel):
    items: list[CandidateParcelRow]
    total: int
    page: int
    page_size: int
