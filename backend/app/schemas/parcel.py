import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    # Total assessed value (land + improvements) from the per-state mapper.
    # Populated at ingest from parcels.raw; null when the source layer
    # doesn't publish enough fields to derive it.
    assessed_value: float | None = None
    is_residential: bool | None = None
    has_structure: bool | None
    in_flood_zone: bool
    avg_slope_pct: float | None
    in_wetland: bool
    county_link: str | None
    storage_permission: str | None = None
    created_at: datetime
    updated_at: datetime

    # Flood/wetland flags are NULL for parcels whose ingest hasn't run the
    # FEMA/wetland overlay yet (common right after a fresh county load).
    # Treat NULL as "not flagged" so the row still serializes — these are
    # display booleans, and "unknown" surfaces as unflagged rather than
    # 500-ing the whole list. See _coerce_flag on CandidateParcelRow too.
    @field_validator("in_flood_zone", "in_wetland", mode="before")
    @classmethod
    def _coerce_flag(cls, v: object) -> bool:
        return bool(v)


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
    # When true, restrict results to parcels with a current matched
    # for-sale listing (any source, confidence >= 0.85). Bound to
    # BuyBoxFilter.requireListed on the dashboard. SQL-level filter
    # so both the map and the parcels-list see the same focused set,
    # regardless of acres/score sort.
    listed_only: bool = False


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


class ListingSummary(BaseModel):
    """Per-parcel listing rollup surfaced on the dashboard.

    Pulled from the most-recently-seen current listing matched to
    this parcel (any source, confidence >= 0.85). Populated by the
    LATERAL join in candidate_search; null when no listing exists.
    """
    has_listing: bool = False
    sale_price: float | None = None
    days_on_market: int | None = None
    sale_status: str | None = None
    source: str | None = None
    broker_company: str | None = None
    match_method: str | None = None


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
    aadt: int | None = None
    has_structure: bool | None
    is_viable: bool
    violation_reasons: list[str]
    geom: dict[str, Any] | None = None
    listing_summary: ListingSummary | None = None

    # NULL flood/wetland flags (ingest hasn't run the overlay) coerce to
    # False so a fresh-loaded county still renders on the map instead of
    # 500-ing. Mirrors ParcelRead._coerce_flag.
    @field_validator("in_flood_zone", "in_wetland", mode="before")
    @classmethod
    def _coerce_flag(cls, v: object) -> bool:
        return bool(v)


class CandidateParcelSearchResponse(BaseModel):
    items: list[CandidateParcelRow]
    total: int
    page: int
    page_size: int
