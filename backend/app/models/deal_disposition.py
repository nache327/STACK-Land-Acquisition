"""Mirror of the portfolio dashboard's deal-pipeline dispositions.

The dashboard's ``deal_prospect`` board is where the owner triages pushed deals
(status = new / reviewing / loi_sent / watching / under_contract / passed / dead).
Those decisions live in the SEPARATE dashboard Supabase. This table is
ParcelLogic's local copy, refreshed by ``dashboard_push`` on each sync, so
ParcelLogic can stop re-surfacing a deal the owner already closed out
(passed / dead / under_contract) in the digest + listing alerts — closing the
one-way-sync gap flagged in the 2026-07-17 audit.

One row per parcel (the dashboard board is one card per parcel). Not every
disposition is stored — only the ones that should affect surfacing; see
``dashboard_push._sync_dispositions_back``.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DealDisposition(Base):
    __tablename__ = "deal_dispositions"

    parcel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("parcels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Dashboard board status verbatim (new / reviewing / loi_sent / watching /
    # under_contract / passed / dead).
    status: Mapped[str] = mapped_column(String, nullable=False)
    # When the owner set the disposition (dashboard-side decided_at); null if
    # never explicitly decided.
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When ParcelLogic last pulled this row back from the dashboard.
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
