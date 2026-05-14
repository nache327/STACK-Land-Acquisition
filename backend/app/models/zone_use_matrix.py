import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UsePermission(str, enum.Enum):
    permitted = "permitted"
    conditional = "conditional"
    prohibited = "prohibited"
    unclear = "unclear"


class ClassificationSource(str, enum.Enum):
    llm = "llm"                          # Claude parsed ordinance text, confidence >= 0.70
    rule = "rule"                        # Rule-based fallback classifier only
    human = "human"                      # Human override via PATCH endpoint
    unclear = "unclear"                  # Origin unknown (legacy rows)
    llm_low_confidence = "llm_low_confidence"  # Claude parsed but confidence < 0.70
    llm_rule = "llm_rule"                # Claude parsed; unclear slots filled by rule classifier


class ZoneUseMatrix(Base):
    __tablename__ = "zone_use_matrix"
    # Uniqueness is enforced by a UNIQUE INDEX on
    # (jurisdiction_id, zone_code, COALESCE(municipality, '')) — see
    # migration 0028. Plain UniqueConstraint would treat NULL
    # municipalities as distinct from each other, allowing duplicate
    # county-default rows. Declared as Index here so SQLAlchemy knows
    # it exists; the index itself is created in the migration.
    __table_args__ = ()

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    zone_code: Mapped[str] = mapped_column(String(50), nullable=False)
    zone_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional sub-jurisdiction. NULL = "default for this county"; the
    # scorer falls through to a NULL-municipality row when no township
    # -specific row exists. Populated for county-as-jurisdiction states
    # (NJ, PA, etc.) where shared zone codes mean different things
    # across townships. UT and other township-as-jurisdiction states
    # leave this NULL.
    municipality: Mapped[str | None] = mapped_column(String(255), nullable=True)

    self_storage: Mapped[UsePermission] = mapped_column(
        Enum(UsePermission, name="use_permission_enum"),
        nullable=False,
        default=UsePermission.unclear,
    )
    mini_warehouse: Mapped[UsePermission] = mapped_column(
        Enum(UsePermission, name="use_permission_enum", create_constraint=False),
        nullable=False,
        default=UsePermission.unclear,
    )
    light_industrial: Mapped[UsePermission] = mapped_column(
        Enum(UsePermission, name="use_permission_enum", create_constraint=False),
        nullable=False,
        default=UsePermission.unclear,
    )
    luxury_garage_condo: Mapped[UsePermission] = mapped_column(
        Enum(UsePermission, name="use_permission_enum", create_constraint=False),
        nullable=False,
        default=UsePermission.unclear,
    )

    # JSON array of {"section": "...", "quote": "..."}
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    human_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    classification_source: Mapped[ClassificationSource] = mapped_column(
        Enum(ClassificationSource, name="classification_source_enum"),
        nullable=False,
        default=ClassificationSource.unclear,
        server_default="unclear",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    jurisdiction: Mapped["Jurisdiction"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="zone_matrix"
    )

    def __repr__(self) -> str:
        return f"<ZoneUseMatrix {self.zone_code} ({self.jurisdiction_id})>"
