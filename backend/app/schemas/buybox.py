"""
Pydantic schemas for the server-side buy-box API.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScoreFactor(BaseModel):
    """A single signed contribution to a composite score."""
    label: str
    delta: float
    reason: str


class ParcelScoreRead(BaseModel):
    parcel_id: int
    buybox_filter_id: uuid.UUID
    score: int
    tier: str
    factors: list[ScoreFactor] = Field(default_factory=list)
    computed_at: datetime

    class Config:
        from_attributes = True


class BuyboxFilterRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    use_case_id: uuid.UUID
    name: str
    filter_json: dict[str, Any]
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BuyboxFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    filter_json: dict[str, Any]
    use_case_id: uuid.UUID | None = None
    is_default: bool = False


class BuyboxFilterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    filter_json: dict[str, Any] | None = None
    is_default: bool | None = None
