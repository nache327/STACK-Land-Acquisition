"""Per-muni primary-source ordinance fingerprints — the freshness sentinel's state.

One current row per ordinance URL (latest-upsert, like ``needle_snapshot``):
the BASELINE columns capture the host's state when the muni's verdicts were
grounded (or first fingerprinted); the CURRENT columns are refreshed monthly by
``scripts/ordinance_sentinel.py`` (spawned from the watchdog tick). A mismatch
per ``app.services.ordinance_freshness.decide_drift`` stamps ``drift_detected_at``
+ ``drift_reason`` and the muni enters the human re-verify queue; a human
re-grounds from the primary source and re-baselines via the script's
``--rebaseline`` flag. Documentation model only (never imported at runtime —
same pattern as ``needle_snapshot``): the table is created by migration 0057
and read/written with raw asyncpg from the sentinel script.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class OrdinanceFingerprint(Base):
    __tablename__ = "ordinance_fingerprints"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Nullable: directory munis don't all map 1:1 to a jurisdictions row
    # (NJ/PA jurisdiction = county; the muni is the sentinel's unit).
    jurisdiction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jurisdictions.id", ondelete="SET NULL")
    )
    state: Mapped[str | None] = mapped_column(String(2))
    municipality: Mapped[str] = mapped_column(Text, nullable=False)
    ordinance_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    host_kind: Mapped[str | None] = mapped_column(String(20))
    # Municode chapter fetches are keyed by productId (recorded in the muni's
    # apply script); without it the row honestly reports needs-manual.
    municode_product_id: Mapped[int | None] = mapped_column(Integer)

    # Baseline = host state the verdicts were grounded against.
    baseline_hash: Mapped[str | None] = mapped_column(String(64))
    baseline_new_laws: Mapped[int | None] = mapped_column(Integer)
    baseline_job_id: Mapped[str | None] = mapped_column(Text)
    baseline_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Prose grounding stamp when known, e.g. "current through Ord 4681 / Supp 80".
    verified_as_of: Mapped[str | None] = mapped_column(Text)

    # Current = latest sentinel fetch.
    current_hash: Mapped[str | None] = mapped_column(String(64))
    current_new_laws: Mapped[int | None] = mapped_column(Integer)
    current_job_id: Mapped[str | None] = mapped_column(Text)
    codified_through: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetch_error: Mapped[str | None] = mapped_column(Text)

    # Sticky until a human re-verifies + --rebaseline clears it.
    drift_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drift_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
