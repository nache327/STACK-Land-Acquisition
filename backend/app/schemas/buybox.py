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
    # Lead-eligibility gate (catch #49, migration 0043): a score is never
    # served without its provenance. lead_eligible=None = scored before the
    # gate existed (re-score to populate).
    lead_eligible: bool | None = None
    gate_reason: str | None = None
    # 'human-verified' | 'ordinance-parsed' | 'heuristic' | 'ungrounded muni'
    verdict_basis: str | None = None

    class Config:
        from_attributes = True


class BuyboxFilterRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    use_case_id: uuid.UUID
    name: str
    filter_json: dict[str, Any]
    is_default: bool
    daily_email_enabled: bool
    daily_email_top_n: int
    last_email_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BuyboxFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    filter_json: dict[str, Any]
    use_case_id: uuid.UUID | None = None
    is_default: bool = False
    daily_email_enabled: bool = False
    daily_email_top_n: int = Field(default=10, ge=1, le=100)


class BuyboxFilterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    filter_json: dict[str, Any] | None = None
    is_default: bool | None = None
    daily_email_enabled: bool | None = None
    daily_email_top_n: int | None = Field(default=None, ge=1, le=100)
