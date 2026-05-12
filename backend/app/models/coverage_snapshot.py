"""coverage_snapshots — cached per-jurisdiction coverage rollup.

Mirrors backend/scripts/audit_zoning_coverage.JurisdictionAudit field-for-
field. Written by `backend/app/services/coverage_audit.refresh_all_snapshots`
and read by GET /api/admin/coverage.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CoverageSnapshot(Base):
    __tablename__ = "coverage_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jurisdiction_name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    county: Mapped[str | None] = mapped_column(Text, nullable=True)
    coverage_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    has_bbox: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    parcel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcel_with_geom_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcel_with_zoning_code_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcel_with_zone_class_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcel_distinct_zone_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vacant_parcel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flood_parcel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wetland_parcel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    zoning_district_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zoning_district_with_geom_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matrix_zone_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matrix_self_storage_permitted_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matrix_self_storage_conditional_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matrix_self_storage_prohibited_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matrix_self_storage_unclear_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matrix_human_reviewed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    parcels_with_zoning_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcels_with_matrix_match: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcels_self_storage_permitted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcels_self_storage_conditional: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcels_self_storage_prohibited: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcels_self_storage_unclear: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parcel_distinct_zone_with_matrix_match_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    parcel_geom_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    parcel_zoning_code_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    parcel_zone_class_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    zoning_polygon_coverage_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    matrix_zone_match_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    matrix_distinct_zone_match_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    self_storage_classified_parcel_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    self_storage_positive_parcel_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    operational_readiness: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocking_gaps: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    unmatched_zone_samples: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)

    source: Mapped[str | None] = mapped_column(Text, nullable=True)
