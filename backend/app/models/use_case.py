import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UseCase(Base):
    __tablename__ = "use_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    # NULL means "system-defined" — visible to every organization.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Names of zone_use_matrix columns this use case scores against.
    # e.g. ["self_storage", "mini_warehouse"]
    use_keys: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization: Mapped["Organization | None"] = relationship(  # noqa: F821
        back_populates="use_cases"
    )
    buybox_filters: Mapped[list["BuyboxFilter"]] = relationship(  # noqa: F821
        back_populates="use_case", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UseCase slug={self.slug} org={self.organization_id}>"
