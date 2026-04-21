from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.zoning_district import ZoneClass, ZoneSource


class ZoningDistrictRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jurisdiction_id: uuid.UUID
    zone_code: str
    zone_name: str | None = None
    zone_class: ZoneClass
    allowed_uses: list[str] | None = None
    max_far: float | None = None
    max_height_ft: float | None = None
    max_density_dua: float | None = None
    min_lot_area_sqft: float | None = None
    source: ZoneSource
    confidence: float | None = None
    human_reviewed: bool
    created_at: datetime
    updated_at: datetime


class ZoningDistrictList(BaseModel):
    items: list[ZoningDistrictRead]
    total: int


class ZoningDistrictUpdate(BaseModel):
    """PATCH payload for human override."""

    zone_class: ZoneClass | None = None
    zone_name: str | None = None
    allowed_uses: list[str] | None = None
    max_far: float | None = None
    max_height_ft: float | None = None
    max_density_dua: float | None = None
    min_lot_area_sqft: float | None = None


class ParserZoneClassification(BaseModel):
    """
    Output shape for the ordinance parser — one record per distinct zone code.
    Replaces the storage-specific ParserZoneResult for new pipelines.
    """

    code: str
    name: str | None = None
    zone_class: ZoneClass = ZoneClass.unknown
    allowed_uses: list[str] = []
    max_far: float | None = None
    max_height_ft: float | None = None
    max_density_dua: float | None = None
    min_lot_area_sqft: float | None = None
    confidence: float = 0.0
    citations: list[dict[str, Any]] = []
    notes: str | None = None


class ParserClassificationOutput(BaseModel):
    zones: list[ParserZoneClassification]
    unknown_zones: list[str] = []
    parser_warnings: list[str] = []
