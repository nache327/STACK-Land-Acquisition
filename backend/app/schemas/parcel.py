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
    # parcels.city (case-sensitive). Surfaced so the drawer can thread it to
    # the Zoning Verifier, which reads the municipality-scoped matrix row.
    city: str | None = None
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
    # Luxury garage condo. There is no reliable stored verdict for this use
    # (the parser infers luxury_garage_condo, but catch #58 in the post-ingest
    # gate forces it to 'prohibited' in the light-industrial / storage-dead
    # zones that are the best LGC targets). So LGC-viability is DERIVED at
    # query time from the trustworthy sibling columns in candidate_search —
    # see _LGC_EFFECTIVE_LABEL there.
    luxury_garage_condo = "luxury_garage_condo"


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
    # Restrict to parcels in these cities (parcels.city). Used to drill into
    # one city within a county-as-jurisdiction (e.g. a Salt Lake County or
    # NJ-county jurisdiction that spans many cities). NULL/empty = all cities.
    cities: list[str] | None = None
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
    # When True the endpoint returns CandidateParcelRowSlim (paint-only
    # fields) instead of the full CandidateParcelRow. The MapLibre paint
    # pipeline only reads parcel_id, geom, zoning_code, zone_class,
    # storage_permission, is_viable; popup detail comes from
    # GET /api/parcels/{parcel_id} on click. Bergen page_size=5000:
    # full response ≈ 4.9 MB / 23 s, slim drops the ~10 popup-only
    # fields and skips the listing-summary second query.
    # Default False preserves the existing contract for all current
    # callers (parcel table, operator scripts, etc).
    slim: bool = False


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
    city: str | None = None
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


class CandidateParcelRowSlim(BaseModel):
    """Paint-only subset of CandidateParcelRow for the map layer.

    Returned when CandidateParcelSearchRequest.slim is True. Drops every
    field the MapLibre paint pipeline doesn't read. Click-time popup
    fetches the heavy detail from GET /api/parcels/{parcel_id}, so no
    field is lost to the operator — only deferred until click.

    `has_listing` and `garage_permission` were added back after the
    initial slim landing (PR #202): Map.tsx:678 reads has_listing for
    the magenta for-sale outline filter, and Map.tsx:892 reads
    garage_permission for the KEEP_LAYER fill. Dropping them broke
    those two paint expressions; restoring them costs ~13 bytes per
    row (~65 KB on a 5000-row Bergen page) — Master accepted the
    trade for paint correctness.
    """
    parcel_id: int
    apn: str
    zoning_code: str | None = None
    zone_class: ZoneClass | None = None
    storage_permission: str | None = None
    # Always present in slim — derived via a scalar EXISTS subquery in
    # the main row SELECT, so slim mode never fires the heavy
    # forsale_listings second-pass query that the full path uses to
    # build listing_summary.
    has_listing: bool = False
    garage_permission: str | None = None
    is_viable: bool
    geom: dict[str, Any] | None = None


class CandidateParcelSearchResponse(BaseModel):
    # Union to keep the response model truthful in both modes. The
    # endpoint's response_model is set to this union'd shape and the
    # service returns whichever variant matches the request flag.
    items: list[CandidateParcelRow] | list[CandidateParcelRowSlim]
    total: int
    page: int
    page_size: int
