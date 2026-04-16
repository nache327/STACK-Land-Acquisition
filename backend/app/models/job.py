import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class JobStatus(str, enum.Enum):
    pending = "pending"
    discovering_layers = "discovering_layers"
    downloading_parcels = "downloading_parcels"
    parsing_ordinance = "parsing_ordinance"
    running_overlays = "running_overlays"
    ready = "ready"
    failed = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jurisdictions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status_enum"),
        nullable=False,
        default=JobStatus.pending,
    )

    # Raw user input — preserved so we can diagnose failures
    jurisdiction_input: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ordinance_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # e.g. ["self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo"]
    target_uses: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # For PDF uploads — stored path
    ordinance_pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Structured progress details for each stage
    progress: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    jurisdiction: Mapped["Jurisdiction | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="jobs"
    )

    def __repr__(self) -> str:
        return f"<Job {self.id} status={self.status}>"
