"""zoning_sources — durable registry of zoning-source candidates per
jurisdiction (and optionally per-municipality for states like NJ where
zoning is municipal).

Discovery candidates are written here with `confidence_label='discovered'`.
The operator reviews, promotes the best fit to `confidence_label='verified'`
via the `_sources/{id}/verify` endpoint, and the platform then has a
durable record of what's been tried + what's the canonical source.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ZoningSource(Base):
    __tablename__ = "zoning_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # For NJ-style work: jurisdiction_id is the COUNTY, municipality_name
    # names a specific town within it.
    municipality_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    county: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    parcel_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    zoning_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    shapefile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_matches: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)

    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured per-component score deltas, e.g.
    # {"name_match": 25, "geometry_polygon": 20, "wrong_state": -40}.
    # Complements `reasons` (human-readable text).
    confidence_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    discovered_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasons: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)

    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
