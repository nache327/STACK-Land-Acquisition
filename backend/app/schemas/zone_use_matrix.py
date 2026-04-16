import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.zone_use_matrix import UsePermission


class CitationSchema(BaseModel):
    section: str
    quote: str = Field(..., max_length=200)


class ZoneUseMatrixRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jurisdiction_id: uuid.UUID
    zone_code: str
    zone_name: str | None
    self_storage: UsePermission
    mini_warehouse: UsePermission
    light_industrial: UsePermission
    luxury_garage_condo: UsePermission
    citations: list[CitationSchema] | None
    confidence: float | None
    human_reviewed: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ZoneUseMatrixUpdate(BaseModel):
    """Human override — analyst can correct a cell and add a comment."""
    self_storage: UsePermission | None = None
    mini_warehouse: UsePermission | None = None
    light_industrial: UsePermission | None = None
    luxury_garage_condo: UsePermission | None = None
    notes: str | None = None


class ZoneMatrixResponse(BaseModel):
    zones: list[ZoneUseMatrixRead]
    unknown_zones: list[str] = []
    parser_warnings: list[str] = []


# Parser output contract — validated before writing to DB
class ParserZoneResult(BaseModel):
    code: str
    name: str | None = None
    self_storage: UsePermission
    mini_warehouse: UsePermission
    light_industrial: UsePermission
    luxury_garage_condo: UsePermission
    citations: list[CitationSchema] = []
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class ParserOutput(BaseModel):
    zones: list[ParserZoneResult]
    unknown_zones: list[str] = []
    parser_warnings: list[str] = []
