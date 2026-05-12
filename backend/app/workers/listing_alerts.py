"""Immediate "🔥 new listing match" alert worker.

Fires after each listings upload (not on cron). For each active
``buybox_filters`` row with daily-email enabled, finds parcels that:

* Have a current matched listing (confidence >= 0.85) from this upload
* Score >= ALERT_SCORE_MIN on the filter
* Haven't been notified about THIS (filter, listing) combo before

Sends one email per filter per upload, batched by jurisdiction so a
single CoStar upload of 50 listings is one email per active filter.
The notified_listings table stores (filter_id, listing_id) so re-
uploading the same file is a no-op.

Why a separate worker from daily_email.py?

* daily_email.py's notified_at gates "this parcel was emailed this
  cycle" — once-per-day cadence, parcel-keyed.
* listing_alerts.py's notified_listings gates "this listing was
  alerted under this filter" — fires on every upload, listing-keyed.

Two dedup tables because a parcel can be re-listed (new ForsaleListing
row, same parcel_id) and we want to fire on the new listing even if
the parcel was previously emailed.
"""
from __future__ import annotations

import html as html_lib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_maker
from app.models.buybox_filter import BuyboxFilter
from app.models.notified_listing import NotifiedListing
from app.services.email_resend import send_email

logger = logging.getLogger(__name__)

# Min composite score for an alert. Stricter than the daily digest's
# floor of 40 — these are interrupt-style emails, so the bar is higher.
ALERT_SCORE_MIN = 85


@dataclass
class AlertRow:
    listing_id: uuid.UUID
    parcel_id: int
    apn: str
    address: str | None
    owner_name: str | None
    jurisdiction_id: uuid.UUID
    jurisdiction_name: str
    score: int
    tier: str
    listing_source: str
    listing_sale_price: float | None
    listing_dom: int | None
    listing_broker_company: str | None
    listing_broker_contact: str | None
    listing_broker_phone: str | None
    listing_broker_email: str | None


async def _eligible_filters_for_jurisdiction(
    db: AsyncSession, jurisdiction_id: uuid.UUID
) -> list[BuyboxFilter]:
    """All email-enabled filters. Listing alerts are global (cross-
    jurisdiction): a user's filter might match parcels in any city
    that's been ingested. We still pass the jurisdiction_id below so
    the SQL only joins parcels in that jurisdiction (the upload that
    triggered the alert is jurisdiction-scoped)."""
    rows = await db.execute(
        select(BuyboxFilter).where(BuyboxFilter.daily_email_enabled.is_(True))
    )
    return list(rows.scalars())


async def _alert_rows_for_filter(
    db: AsyncSession,
    filter_id: uuid.UUID,
    jurisdiction_id: uuid.UUID,
) -> list[AlertRow]:
    """Find listings in this jurisdiction that match this filter and
    haven't been alerted yet. Joins parcel_buybox_scores so the
    score is the live scored value (post listing_score_boost)."""
    sql = text(
        """
        SELECT
            l.id              AS listing_id,
            l.matched_parcel_id AS parcel_id,
            p.apn             AS apn,
            p.address         AS address,
            p.owner_name      AS owner_name,
            j.id              AS jurisdiction_id,
            j.name            AS jurisdiction_name,
            pbs.score         AS score,
            pbs.tier          AS tier,
            l.source          AS listing_source,
            l.sale_price      AS listing_sale_price,
            l.days_on_market  AS listing_dom,
            l.listing_broker_company AS listing_broker_company,
            l.listing_broker_contact AS listing_broker_contact,
            l.listing_broker_phone   AS listing_broker_phone,
            l.listing_broker_email   AS listing_broker_email
        FROM forsale_listings l
        JOIN parcels p       ON p.id = l.matched_parcel_id
        JOIN jurisdictions j ON j.id = p.jurisdiction_id
        JOIN parcel_buybox_scores pbs
              ON pbs.parcel_id = p.id
             AND pbs.buybox_filter_id = :fid
        LEFT JOIN notified_listings nl
              ON nl.filter_id = :fid
             AND nl.listing_id = l.id
        WHERE l.jurisdiction_id = :jid
          AND l.is_current = true
          AND l.matched_parcel_id IS NOT NULL
          AND l.match_confidence >= 0.85
          AND pbs.score >= :min_score
          AND nl.id IS NULL
        ORDER BY pbs.score DESC, l.last_seen_at DESC
        """
    )
    rows = await db.execute(
        sql,
        {
            "fid": filter_id,
            "jid": jurisdiction_id,
            "min_score": ALERT_SCORE_MIN,
        },
    )
    out: list[AlertRow] = []
    for r in rows:
        m = r._mapping
        sp = m["listing_sale_price"]
        out.append(AlertRow(
            listing_id=m["listing_id"],
            parcel_id=m["parcel_id"],
            apn=m["apn"],
            address=m["address"],
            owner_name=m["owner_name"],
            jurisdiction_id=m["jurisdiction_id"],
            jurisdiction_name=m["jurisdiction_name"],
            score=m["score"],
            tier=m["tier"],
            listing_source=m["listing_source"],
            listing_sale_price=float(sp) if sp is not None else None,
            listing_dom=m["listing_dom"],
            listing_broker_company=m["listing_broker_company"],
            listing_broker_contact=m["listing_broker_contact"],
            listing_broker_phone=m["listing_broker_phone"],
            listing_broker_email=m["listing_broker_email"],
        ))
    return out


def _parcel_link(row: AlertRow) -> str:
    base = settings.digest_dashboard_base_url.rstrip("/")
    return f"{base}/dashboard/{row.jurisdiction_id}?parcel={row.apn}"


def _render_alert_subject(filter_name: str, rows: list[AlertRow]) -> str:
    n = len(rows)
    cities = sorted({r.jurisdiction_name for r in rows})
    city_part = cities[0] if len(cities) == 1 else "multiple cities"
    return f"\U0001f525 {n} new listing match{'es' if n != 1 else ''} — {filter_name} in {city_part}"


def _render_alert_text(filter_name: str, rows: list[AlertRow]) -> str:
    lines = [f"\U0001f525 {len(rows)} new listing match(es) — {filter_name}", ""]
    for r in rows:
        price = (
            f"${int(r.listing_sale_price):,}" if r.listing_sale_price is not None else "Price n/a"
        )
        dom = f" (DOM: {r.listing_dom})" if r.listing_dom is not None else ""
        lines.append(f"• {r.address or r.apn} ({r.jurisdiction_name})")
        lines.append(f"  \U0001f3f7️ {price}{dom} · via {r.listing_source}")
        broker = ", ".join(x for x in [r.listing_broker_contact, r.listing_broker_company] if x)
        if broker:
            lines.append(f"  Broker: {broker}")
        contact = " · ".join(x for x in [r.listing_broker_phone, r.listing_broker_email] if x)
        if contact:
            lines.append(f"  Contact: {contact}")
        lines.append(f"  Score: {r.score} ({r.tier})")
        lines.append(f"  {_parcel_link(r)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_alert_html(filter_name: str, rows: list[AlertRow]) -> str:
    items: list[str] = []
    for r in rows:
        title = html_lib.escape(r.address or r.apn)
        city = html_lib.escape(r.jurisdiction_name)
        link = html_lib.escape(_parcel_link(r))
        price = (
            f"${int(r.listing_sale_price):,}" if r.listing_sale_price is not None else "Price n/a"
        )
        dom = f" · DOM {r.listing_dom}" if r.listing_dom is not None else ""
        source = html_lib.escape(r.listing_source)
        broker_line = ""
        if r.listing_broker_company or r.listing_broker_contact:
            broker = html_lib.escape(", ".join(
                x for x in [r.listing_broker_contact, r.listing_broker_company] if x
            ))
            broker_line = f"<div>Broker: <strong>{broker}</strong></div>"
        contact_line = ""
        contact_parts = [x for x in [r.listing_broker_phone, r.listing_broker_email] if x]
        if contact_parts:
            contact_line = (
                "<div>Contact: " + html_lib.escape(" · ".join(contact_parts)) + "</div>"
            )
        items.append(f"""
            <div style="border:1px solid #fcd34d;border-radius:8px;padding:14px 16px;margin:12px 0;background:#fffbeb">
              <div style="font-weight:600;font-size:15px"><a href="{link}" style="color:#0f172a;text-decoration:none">{title}</a></div>
              <div style="color:#475569;font-size:13px;margin-top:2px">{city}</div>
              <div style="margin-top:8px;font-size:13px;color:#92400e">
                \U0001f3f7️ <strong>{price}</strong>{dom} · via {source}
              </div>
              {broker_line}
              {contact_line}
              <div style="margin-top:6px;font-size:13px;color:#0f172a">Score <strong>{r.score}</strong> · {html_lib.escape(r.tier)}</div>
              <a href="{link}" style="display:inline-block;margin-top:8px;color:#0369a1;font-size:13px">Open in dashboard →</a>
            </div>
        """)
    return f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a">
  <div style="max-width:560px;margin:0 auto">
    <h1 style="font-size:18px;margin:0 0 4px">\U0001f525 New listing matches</h1>
    <div style="color:#64748b;font-size:13px;margin-bottom:8px">{html_lib.escape(filter_name)}</div>
    {''.join(items)}
    <div style="color:#94a3b8;font-size:11px;margin-top:24px">
      Sent by ParcelLogic. Manage alerts in the buy-box panel.
    </div>
  </div>
</body></html>"""


async def fire_alerts_for_upload(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Entry point invoked by the upload background task after matching
    completes. Loops through eligible filters, gathers unalerted matches,
    sends one email per filter, records to notified_listings.

    Returns ``{filters: N, alerts: M}`` for caller logging. Both numbers
    can be 0 — that's expected on most uploads.
    """
    filters = await _eligible_filters_for_jurisdiction(db, jurisdiction_id)
    if not filters:
        return {"filters": 0, "alerts": 0}

    total_alerts = 0
    filters_sent = 0
    for f in filters:
        rows = await _alert_rows_for_filter(db, f.id, jurisdiction_id)
        if not rows:
            continue
        if not settings.digest_default_recipient:
            logger.warning(
                "listing_alerts filter=%s: %d alerts ready but DIGEST_DEFAULT_RECIPIENT unset",
                f.name, len(rows),
            )
            continue

        subject = _render_alert_subject(f.name, rows)
        text_body = _render_alert_text(f.name, rows)
        html_body = _render_alert_html(f.name, rows)
        try:
            msg_id = await send_email(
                to=settings.digest_default_recipient,
                subject=subject,
                text=text_body,
                html=html_body,
            )
        except Exception as exc:
            logger.error("listing_alerts send failed (%s): %s", f.name, exc)
            continue

        logger.info(
            "listing_alerts filter=%s rows=%d resend_id=%s",
            f.name, len(rows), msg_id,
        )

        # Record (filter, listing) pairs so re-uploads don't re-alert
        notified = [
            NotifiedListing(
                filter_id=f.id,
                listing_id=r.listing_id,
                parcel_id=r.parcel_id,
                notified_at=datetime.now(timezone.utc),
            )
            for r in rows
        ]
        db.add_all(notified)
        await db.commit()

        total_alerts += len(rows)
        filters_sent += 1

    return {"filters": filters_sent, "alerts": total_alerts}


async def fire_alerts_in_background(jurisdiction_id: uuid.UUID) -> None:
    """Wrapper for BackgroundTasks — opens its own session."""
    async with async_session_maker() as bg_db:
        try:
            counts = await fire_alerts_for_upload(jurisdiction_id, bg_db)
            logger.info("listing_alerts upload juris=%s: %s", jurisdiction_id, counts)
        except Exception as exc:
            logger.error("listing_alerts upload failed juris=%s: %s", jurisdiction_id, exc)


__all__ = ["fire_alerts_for_upload", "fire_alerts_in_background", "ALERT_SCORE_MIN"]
