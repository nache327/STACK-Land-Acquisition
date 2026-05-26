"""Daily buy-box digest worker.

For each ``buybox_filters`` row where ``daily_email_enabled = true`` and
``last_email_sent_at`` is older than 23h, send the top-N unnotified
parcels (by composite score) under that filter as one email. Mark each
emailed parcel's ``parcel_buybox_scores.notified_at`` so we never
re-email the same parcel for the same filter.

Run modes:

* CLI:        ``python -m app.workers.daily_email`` — runs the digest
  once and exits. Wire this to a Railway cron at 7am ET (12:00 UTC
  outside DST, 11:00 UTC during DST) until we add a built-in cron
  scheduler.
* Dramatiq:   ``send_daily_digest_actor.send()`` — for ad-hoc triggering
  (manual smoke tests, web hooks, etc).

Recipient resolution: until per-user email lands, every email-enabled
filter delivers to ``settings.digest_default_recipient``.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import dramatiq
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import long_running_session_maker
# The candidate-selection SQL in _top_parcels_for_filter joins
# parcel_buybox_scores (now ~1M rows after Howard MD + Loudoun +
# Allentown matrix sprints added ~270K each) against parcels,
# jurisdictions, and 3 LATERAL subqueries. Default async_session_maker
# is command_timeout=90s; the query consistently runs 90-180s on
# prod data. long_running_session_maker uses command_timeout=600
# (built originally for the coverage audit sweep) — same shape of
# legitimately-long-but-bounded query.
from app.models.buybox_filter import BuyboxFilter
from app.models.parcel_buybox_score import ParcelBuyboxScore
from app.services.email_resend import send_email
from app.services.job_queue import redis_broker  # noqa: F401  (registers broker)

logger = logging.getLogger(__name__)


@dataclass
class DigestParcel:
    parcel_id: int
    apn: str
    address: str | None
    owner_name: str | None
    score: int
    tier: str
    factors: list[dict]
    jurisdiction_id: str
    jurisdiction_name: str
    # Acres surfaced in the email header so the operator can size-check
    # without opening the dashboard. None when not ingested.
    acres: float | None = None
    # Listing info — populated when the parcel has a current matched
    # listing (any source, confidence >= 0.85). When present, the
    # renderer prints a 🏷️ banner block above the score with broker
    # contact prominent. None means no current listing.
    listing_source: str | None = None
    listing_sale_price: float | None = None
    listing_dom: int | None = None
    listing_broker_company: str | None = None
    listing_broker_contact: str | None = None
    listing_broker_phone: str | None = None
    listing_broker_email: str | None = None
    # Most-recent ready job_id for the jurisdiction. The dashboard
    # route is /dashboard/[jobId] and passes the segment straight to
    # GET /api/jobs/:id. Previous versions used jurisdiction_id here,
    # which 404'd and the page stuck on "Loading…" forever. Now
    # populated from a LATERAL join so deep links actually navigate.
    # None when no ready job exists yet (rare; fallback link uses
    # jurisdiction_id and the UX is the same broken state as before).
    dashboard_job_id: str | None = None
    # Hot Deals v2 soft flags — surfaced in the email as warnings, not
    # selection filters. Each is a (emoji, short_label) pair so the
    # renderer can iterate without re-mapping. Empty list means the
    # deal is fully Actionable (Tier 1). Any non-empty list demotes
    # the deal to "Worth a Look" (Tier 2). See `_soft_flags_for`.
    soft_flags: list[tuple[str, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.soft_flags is None:
            self.soft_flags = []


# ─── Selection ────────────────────────────────────────────────────────────

# Don't re-fire within 23h. Slightly under 24h so a 7am cron never skips
# a day because of clock drift / late starts.
_RESEND_INTERVAL = timedelta(hours=23)
# Soft floor on score — we want "noteworthy" parcels in the digest, not
# the bottom of the score distribution. Maps roughly to the user spec's
# `classification IN ('match', 'borderline')`.
_MIN_SCORE = 40
# Stricter floor when the filter sets `requireListed=true`. The
# operator's goal in listed-only mode is "perfect site, currently for
# sale, broker contact attached" — only Strong-tier+ scores qualify.
_MIN_SCORE_LISTED = 70


async def _eligible_filters(
    db: AsyncSession, force: bool = False
) -> list[BuyboxFilter]:
    """Return email-enabled filters that are due for a digest.

    The 23h gate (last_email_sent_at) is skipped when ``force`` is true,
    so manual smoke-test triggers can re-fire within the same day.
    The per-parcel notified_at gate is independent and still applies —
    re-running force=true won't re-email parcels that already went out.
    """
    stmt = select(BuyboxFilter).where(BuyboxFilter.daily_email_enabled.is_(True))
    if not force:
        cutoff = datetime.now(timezone.utc) - _RESEND_INTERVAL
        stmt = stmt.where(
            (BuyboxFilter.last_email_sent_at.is_(None))
            | (BuyboxFilter.last_email_sent_at < cutoff)
        )
    stmt = stmt.order_by(BuyboxFilter.updated_at.desc())
    return list((await db.execute(stmt)).scalars())


async def _top_parcels_for_filter(
    db: AsyncSession, f: BuyboxFilter
) -> list[DigestParcel]:
    filter_json = f.filter_json or {}
    require_listed = bool(filter_json.get("requireListed"))
    # Hot Deals v2: optional hard filters. NULL = no filter, pass through.
    min_acres = filter_json.get("minAcres")
    max_acres = filter_json.get("maxAcres")
    max_price_per_acre = filter_json.get("maxPricePerAcre")

    # ``require_listed`` is a hard filter: drop parcels with no current
    # matched listing (confidence >= 0.85). The LATERAL join below
    # picks the most-recently-seen listing per parcel; the WHERE branch
    # turns the requirement on/off without two SQL paths.
    #
    # The `zum` LATERAL is new — used for the conditional-zoning and
    # low-confidence soft flags. It picks the most-specific matrix row
    # (municipality-scoped wins over NULL-default) mirroring
    # `buybox_scoring.py`'s lateral pattern so the flags reflect the
    # same row the scorer used.
    sql = text(
        """
        SELECT
            p.id            AS parcel_id,
            p.apn           AS apn,
            p.address       AS address,
            p.owner_name    AS owner_name,
            p.acres         AS acres,
            pbs.score       AS score,
            pbs.tier        AS tier,
            pbs.factors     AS factors,
            j.id            AS jurisdiction_id,
            j.name          AS jurisdiction_name,
            lst.source                  AS listing_source,
            lst.sale_price              AS listing_sale_price,
            lst.days_on_market          AS listing_dom,
            lst.listing_broker_company  AS listing_broker_company,
            lst.listing_broker_contact  AS listing_broker_contact,
            lst.listing_broker_phone    AS listing_broker_phone,
            lst.listing_broker_email    AS listing_broker_email,
            latest_job.id               AS dashboard_job_id,
            -- Soft flags (computed in SQL so the WHERE-level filter and
            -- the email render see the same booleans).
            (p.has_structure = TRUE OR COALESCE(p.improvement_value, 0) > 50000)
                AS soft_has_building,
            (lst.sale_price IS NULL)                       AS soft_no_price,
            (zum.self_storage::text = 'conditional')       AS soft_conditional,
            (zum.confidence IS NOT NULL AND zum.confidence < 0.70)
                AS soft_low_confidence,
            (p.in_flood_zone = TRUE)                       AS soft_flood,
            (p.in_wetland    = TRUE)                       AS soft_wetland
        FROM parcel_buybox_scores pbs
        JOIN parcels p       ON p.id = pbs.parcel_id
        JOIN jurisdictions j ON j.id = p.jurisdiction_id
        LEFT JOIN LATERAL (
            SELECT source, sale_price, days_on_market,
                   listing_broker_company, listing_broker_contact,
                   listing_broker_phone, listing_broker_email
              FROM forsale_listings
             WHERE matched_parcel_id = p.id
               AND is_current = true
               AND match_confidence >= 0.85
             ORDER BY last_seen_at DESC
             LIMIT 1
        ) lst ON true
        LEFT JOIN LATERAL (
            SELECT self_storage, confidence
              FROM zone_use_matrix
             WHERE jurisdiction_id = p.jurisdiction_id
               AND zone_code      = p.zoning_code
               AND (municipality IS NULL OR municipality = p.city)
               AND deleted_at IS NULL
             ORDER BY (municipality IS NULL) ASC
             LIMIT 1
        ) zum ON true
        LEFT JOIN LATERAL (
            -- The dashboard route is /dashboard/[jobId]; the URL
            -- segment is the jobs.id, not the jurisdiction_id. Resolve
            -- the most-recently-finished ready job per jurisdiction so
            -- the email link lands somewhere that loads instead of
            -- spinning forever on a 404.
            SELECT id
              FROM jobs
             WHERE jurisdiction_id = j.id
               AND status = 'ready'
             ORDER BY finished_at DESC NULLS LAST, created_at DESC
             LIMIT 1
        ) latest_job ON true
        WHERE pbs.buybox_filter_id = :fid
          AND pbs.notified_at IS NULL
          AND pbs.score >= :min_score
          AND (NOT :require_listed OR lst.source IS NOT NULL)
          -- Alert-then-digest dedupe: skip parcels that were already
          -- emailed as a real-time listing alert in the last 14 days.
          -- listing_alerts.py keys dedupe on (filter, listing); this
          -- worker keys on parcels.notified_at. Without the cross-check,
          -- a parcel alerted Monday gets digested Tuesday -- 58 Dunkard
          -- Church and 199 Grandview both hit this dupe in the May 13-20
          -- reviewer audit.
          AND NOT EXISTS (
            SELECT 1 FROM notified_listings nl
             WHERE nl.filter_id = :fid
               AND nl.parcel_id = p.id
               AND nl.notified_at > NOW() - INTERVAL '14 days'
          )
          -- Hot Deals v2: hard-filter knobs. NULL bindings pass through
          -- so non-Hot-Deals filters (e.g. Default Box) are unaffected.
          AND (CAST(:min_acres AS DOUBLE PRECISION) IS NULL
               OR p.acres IS NULL
               OR p.acres >= CAST(:min_acres AS DOUBLE PRECISION))
          AND (CAST(:max_acres AS DOUBLE PRECISION) IS NULL
               OR p.acres IS NULL
               OR p.acres <= CAST(:max_acres AS DOUBLE PRECISION))
          -- Price-per-acre cap fires only when both price and acres
          -- are populated. Unpriced listings pass through and surface
          -- as the "no asking price" soft flag instead.
          AND (CAST(:max_price_per_acre AS DOUBLE PRECISION) IS NULL
               OR lst.sale_price IS NULL
               OR p.acres IS NULL
               OR p.acres = 0
               OR (lst.sale_price / p.acres)
                   <= CAST(:max_price_per_acre AS DOUBLE PRECISION))
        ORDER BY pbs.score DESC, pbs.parcel_id
        LIMIT :lim
        """
    )
    rows = await db.execute(
        sql,
        {
            "fid": f.id,
            "min_score": _MIN_SCORE_LISTED if require_listed else _MIN_SCORE,
            "lim": f.daily_email_top_n,
            "require_listed": require_listed,
            "min_acres": min_acres,
            "max_acres": max_acres,
            "max_price_per_acre": max_price_per_acre,
        },
    )
    out: list[DigestParcel] = []
    for r in rows:
        m = r._mapping
        sp = m["listing_sale_price"]
        acres = m["acres"]
        out.append(
            DigestParcel(
                parcel_id=m["parcel_id"],
                apn=m["apn"],
                address=m["address"],
                owner_name=m["owner_name"],
                acres=float(acres) if acres is not None else None,
                score=m["score"],
                tier=m["tier"],
                factors=list(m["factors"] or []),
                jurisdiction_id=str(m["jurisdiction_id"]),
                jurisdiction_name=m["jurisdiction_name"],
                listing_source=m["listing_source"],
                listing_sale_price=float(sp) if sp is not None else None,
                listing_dom=m["listing_dom"],
                listing_broker_company=m["listing_broker_company"],
                listing_broker_contact=m["listing_broker_contact"],
                listing_broker_phone=m["listing_broker_phone"],
                listing_broker_email=m["listing_broker_email"],
                dashboard_job_id=(
                    str(m["dashboard_job_id"]) if m["dashboard_job_id"] else None
                ),
                soft_flags=_soft_flags_from_row(m),
            )
        )
    return out


# ─── Soft-flag derivation ────────────────────────────────────────────────

# Each entry: (sql_column_name, emoji, short_label_for_email).
# Order here drives display order in the email body.
_SOFT_FLAG_RULES: list[tuple[str, str, str]] = [
    ("soft_has_building",   "🏢",  "likely has existing building"),
    ("soft_no_price",       "💸",  "no asking price listed"),
    ("soft_conditional",    "⚖️",   "conditional zoning (entitlement risk)"),
    ("soft_low_confidence", "❓",  "low-confidence zoning verdict (<0.70)"),
    ("soft_flood",          "🌊",  "in flood zone"),
    ("soft_wetland",        "🐸",  "in wetland"),
]


def _soft_flags_from_row(m) -> list[tuple[str, str]]:
    """Pull the boolean soft-flag columns from a row mapping into the
    (emoji, label) pairs the email renderer iterates over.
    Skips flags whose column evaluated to False (or NULL — treated as
    'unknown, do not flag') so the email only surfaces real warnings."""
    return [
        (emoji, label)
        for col, emoji, label in _SOFT_FLAG_RULES
        if bool(m.get(col))
    ]


# ─── Rendering ────────────────────────────────────────────────────────────

def _parcel_link(p: DigestParcel) -> str:
    base = settings.digest_dashboard_base_url.rstrip("/")
    # Use the resolved job_id when available; fall back to the
    # jurisdiction_id (legacy broken behavior) only when no ready job
    # exists. The fallback at least preserves a consistent URL shape
    # for diagnostics — the dashboard will show "Loading…" but that
    # signals "no ready job," which is itself useful information.
    segment = p.dashboard_job_id or p.jurisdiction_id
    # Pass the parcel's DB id (not APN). The dashboard reads
    # ?parcel_id=… on mount, opens the drawer, and flies to the
    # parcel's centroid. APN-based deep links don't resolve without
    # a backend lookup; parcel_id matches the /api/parcels/:id route
    # the drawer already uses.
    return f"{base}/dashboard/{segment}?parcel_id={p.parcel_id}"


def _top_factors(p: DigestParcel, n: int = 5) -> list[dict]:
    """Top-N contributions with non-zero delta, by |delta| descending.

    Filters out zero-delta factors (e.g. "Ring not yet measured"
    placeholders) since they don't move the score and just dilute the
    breakdown. Cap raised from 3 to 5: previously a parcel scoring 100
    with four contributing factors (Base + Storage + Acres + Listed)
    showed three, and the displayed sum mismatched the score by exactly
    the dropped factor.
    """
    non_zero = [f for f in p.factors if float(f.get("delta", 0)) != 0]
    return sorted(
        non_zero,
        key=lambda f: abs(float(f.get("delta", 0))),
        reverse=True,
    )[:n]


def _hidden_factor_count(p: DigestParcel, n: int = 5) -> int:
    """How many non-zero factors got truncated from the displayed top-N."""
    non_zero = [f for f in p.factors if float(f.get("delta", 0)) != 0]
    return max(0, len(non_zero) - n)


def _render_subject(filter_name: str, parcels: list[DigestParcel]) -> str:
    n = len(parcels)
    cities = sorted({p.jurisdiction_name for p in parcels})
    if len(cities) == 1:
        return f"{n} new match{'es' if n != 1 else ''} in {cities[0]} buy-box ({filter_name})"
    return f"{n} new match{'es' if n != 1 else ''} in your buy-box ({filter_name})"


def _listing_banner_html(p: DigestParcel) -> str:
    if not p.listing_source:
        return ""
    price = (
        f"${int(p.listing_sale_price):,}" if p.listing_sale_price is not None else "Price n/a"
    )
    dom = f" · DOM {p.listing_dom} days" if p.listing_dom is not None else ""
    src = html_lib.escape(p.listing_source)
    broker_line = ""
    if p.listing_broker_company or p.listing_broker_contact:
        broker = html_lib.escape(", ".join(
            x for x in [p.listing_broker_contact, p.listing_broker_company] if x
        ))
        broker_line = f"<div style='margin-top:2px'>Broker: <strong>{broker}</strong></div>"
    contact_line = ""
    contact_parts = [x for x in [p.listing_broker_phone, p.listing_broker_email] if x]
    if contact_parts:
        contact_line = (
            "<div style='margin-top:2px'>Contact: "
            + html_lib.escape(" · ".join(contact_parts))
            + "</div>"
        )
    return (
        f"<div style='margin-top:8px;padding:8px 10px;background:#fef3c7;"
        f"border:1px solid #fcd34d;border-radius:6px;font-size:13px;color:#92400e'>"
        f"<div>\U0001f3f7️ <strong>Listed for sale</strong> — {price}{dom} · via {src}</div>"
        f"{broker_line}{contact_line}"
        f"</div>"
    )


def _listing_banner_text(p: DigestParcel) -> list[str]:
    """Render the 🏷️ listing block for a parcel — only when listed."""
    if not p.listing_source:
        return []
    price_part = (
        f"${int(p.listing_sale_price):,}" if p.listing_sale_price is not None else "Price n/a"
    )
    dom_part = f" (DOM: {p.listing_dom} days)" if p.listing_dom is not None else ""
    lines = [
        f"  🏷️ Listed for sale — {price_part}{dom_part} · via {p.listing_source}",
    ]
    if p.listing_broker_company or p.listing_broker_contact:
        broker = ", ".join(
            x for x in [p.listing_broker_contact, p.listing_broker_company] if x
        )
        lines.append(f"     Broker: {broker}")
    contact_parts = [x for x in [p.listing_broker_phone, p.listing_broker_email] if x]
    if contact_parts:
        lines.append(f"     Contact: {' · '.join(contact_parts)}")
    return lines


def _split_by_tier(
    parcels: list[DigestParcel],
) -> tuple[list[DigestParcel], list[DigestParcel]]:
    """Tier 1 = Actionable (no soft flags). Tier 2 = Worth a Look (any soft flag).

    Order within each tier preserves the input order (which the SQL
    already sorted by score DESC). No re-sorting here — that would
    surprise an operator who expects highest-score-first.
    """
    actionable = [p for p in parcels if not p.soft_flags]
    worth_a_look = [p for p in parcels if p.soft_flags]
    return actionable, worth_a_look


def _acres_blurb(p: DigestParcel) -> str:
    if p.acres is None:
        return ""
    return f" · {p.acres:.2f}ac"


def _render_parcel_text(p: DigestParcel) -> list[str]:
    lines: list[str] = []
    lines.append(f"• {p.address or p.apn}{_acres_blurb(p)} ({p.jurisdiction_name})")
    lines.extend(_listing_banner_text(p))
    if p.soft_flags:
        flag_str = ", ".join(f"{emoji} {label}" for emoji, label in p.soft_flags)
        lines.append(f"  ⚠️ Soft flags: {flag_str}")
    if p.owner_name:
        lines.append(f"  Owner: {p.owner_name}")
    lines.append(f"  Score: {p.score} ({p.tier})")
    for f in _top_factors(p):
        sign = "+" if float(f.get("delta", 0)) >= 0 else ""
        lines.append(
            f"    {f.get('label', '?')}: {sign}{f.get('delta')} — {f.get('reason', '')}"
        )
    hidden = _hidden_factor_count(p)
    if hidden > 0:
        lines.append(f"    (+ {hidden} more factor{'s' if hidden != 1 else ''})")
    lines.append(f"  {_parcel_link(p)}")
    lines.append("")
    return lines


def _render_text(filter_name: str, parcels: list[DigestParcel]) -> str:
    actionable, worth_a_look = _split_by_tier(parcels)
    lines = [f"Daily buy-box digest — {filter_name}", ""]

    if actionable:
        lines.append(f"═══ ACTIONABLE — {len(actionable)} deal{'s' if len(actionable) != 1 else ''} ═══")
        lines.append("")
        for p in actionable:
            lines.extend(_render_parcel_text(p))

    if worth_a_look:
        lines.append(f"═══ WORTH A LOOK — {len(worth_a_look)} deal{'s' if len(worth_a_look) != 1 else ''} (one or more soft flags) ═══")
        lines.append("")
        for p in worth_a_look:
            lines.extend(_render_parcel_text(p))

    return "\n".join(lines).strip() + "\n"


def _render_parcel_html(p: DigestParcel) -> str:
    title = html_lib.escape(p.address or p.apn)
    city = html_lib.escape(p.jurisdiction_name)
    owner = html_lib.escape(p.owner_name or "")
    link = html_lib.escape(_parcel_link(p))
    acres_blurb = (
        f"<span style='color:#475569;font-weight:500'>{p.acres:.2f}ac</span> · "
        if p.acres is not None
        else ""
    )
    soft_flags_html = ""
    if p.soft_flags:
        flag_chips = "".join(
            f"<span style='display:inline-block;background:#fff7ed;border:1px solid #fed7aa;"
            f"border-radius:4px;padding:2px 8px;margin:0 4px 4px 0;color:#9a3412;font-size:12px'>"
            f"{emoji} {html_lib.escape(label)}</span>"
            for emoji, label in p.soft_flags
        )
        soft_flags_html = (
            f"<div style='margin-top:8px;padding:6px 8px;background:#fffbeb;"
            f"border-left:3px solid #f59e0b;font-size:12px;color:#78350f'>"
            f"⚠️ <strong>Soft flags:</strong><div style='margin-top:4px'>{flag_chips}</div>"
            f"</div>"
        )
    factor_items = "".join(
        f"<li><strong>{html_lib.escape(str(f.get('label', '?')))}</strong>: "
        f"{'+' if float(f.get('delta', 0)) >= 0 else ''}{html_lib.escape(str(f.get('delta')))} "
        f"— {html_lib.escape(str(f.get('reason', '')))}</li>"
        for f in _top_factors(p)
    )
    hidden = _hidden_factor_count(p)
    if hidden > 0:
        factor_items += (
            f"<li style='color:#94a3b8;list-style:none;padding-left:0'>"
            f"+ {hidden} more factor{'s' if hidden != 1 else ''}"
            f"</li>"
        )
    owner_html = f"<div style='color:#64748b;font-size:13px'>Owner: {owner}</div>" if owner else ""
    listing_html = _listing_banner_html(p)
    return (
        f"<div style=\"border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin:12px 0;background:#fff\">"
        f"  <div style=\"font-weight:600;color:#0f172a;font-size:15px\">"
        f"    <a href=\"{link}\" style=\"color:#0f172a;text-decoration:none\">{title}</a>"
        f"  </div>"
        f"  <div style=\"color:#475569;font-size:13px;margin-top:2px\">{acres_blurb}{city}</div>"
        f"  {listing_html}"
        f"  {soft_flags_html}"
        f"  {owner_html}"
        f"  <div style=\"margin-top:8px;font-size:13px;color:#0f172a\">"
        f"    Score <strong>{p.score}</strong> · {html_lib.escape(p.tier)}"
        f"  </div>"
        f"  <ul style=\"margin:6px 0 0 16px;padding:0;color:#334155;font-size:12px\">{factor_items}</ul>"
        f"  <a href=\"{link}\" style=\"display:inline-block;margin-top:10px;color:#0369a1;font-size:13px\">Open in dashboard →</a>"
        f"</div>"
    )


def _tier_header_html(label: str, count: int, sub: str = "") -> str:
    """Section header rendered between tiers. Plain text + a thin
    accent rule so the email looks the same in Gmail / Outlook /
    Apple Mail / dark-mode readers without relying on CSS classes."""
    sub_html = f" <span style='color:#64748b;font-weight:400;font-size:13px'>{html_lib.escape(sub)}</span>" if sub else ""
    return (
        f"<div style='margin:20px 0 4px;font-size:14px;font-weight:700;"
        f"color:#0f172a;letter-spacing:0.04em;text-transform:uppercase'>"
        f"{label} — {count} deal{'s' if count != 1 else ''}{sub_html}"
        f"</div>"
        f"<div style='height:2px;background:#0f172a;margin-bottom:8px;width:100%'></div>"
    )


def _render_html(filter_name: str, parcels: list[DigestParcel]) -> str:
    actionable, worth_a_look = _split_by_tier(parcels)

    sections: list[str] = []
    if actionable:
        sections.append(_tier_header_html("Actionable", len(actionable)))
        sections.extend(_render_parcel_html(p) for p in actionable)
    if worth_a_look:
        sections.append(_tier_header_html(
            "Worth a Look", len(worth_a_look), sub="one or more soft flags",
        ))
        sections.extend(_render_parcel_html(p) for p in worth_a_look)

    return f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a">
  <div style="max-width:560px;margin:0 auto">
    <h1 style="font-size:18px;margin:0 0 4px">Daily buy-box digest</h1>
    <div style="color:#64748b;font-size:13px;margin-bottom:8px">{html_lib.escape(filter_name)}</div>
    {''.join(sections)}
    <div style="color:#94a3b8;font-size:11px;margin-top:24px">
      Sent by ParcelLogic. Manage daily emails from the buy-box panel.
    </div>
  </div>
</body></html>"""


# ─── Send + bookkeeping ───────────────────────────────────────────────────

async def _send_digest_for_filter(
    db: AsyncSession, f: BuyboxFilter, force: bool = False,
) -> int:
    parcels = await _top_parcels_for_filter(db, f)
    if not parcels:
        logger.info("digest filter=%s: no eligible parcels — skipping", f.name)
        # Still bump last_email_sent_at? No — leave it so a later run picks
        # up parcels that score in during the day.
        return 0

    if not settings.digest_default_recipient:
        logger.warning(
            "digest filter=%s: %d parcels ready but DIGEST_DEFAULT_RECIPIENT is unset — not sending",
            f.name, len(parcels),
        )
        return 0

    subject = _render_subject(f.name, parcels)
    text_body = _render_text(f.name, parcels)
    html_body = _render_html(f.name, parcels)

    msg_id = await send_email(
        to=settings.digest_default_recipient,
        subject=subject,
        text=text_body,
        html=html_body,
    )
    logger.info(
        "digest filter=%s parcels=%d resend_id=%s", f.name, len(parcels), msg_id,
    )

    parcel_ids = [p.parcel_id for p in parcels]
    # Always stamp per-parcel notified_at so the same parcel doesn't
    # appear in two consecutive digests even when manually force-fired
    # — that's per-parcel de-duplication, not a cooldown gate.
    await db.execute(
        update(ParcelBuyboxScore)
        .where(ParcelBuyboxScore.buybox_filter_id == f.id)
        .where(ParcelBuyboxScore.parcel_id.in_(parcel_ids))
        .values(notified_at=datetime.now(timezone.utc))
    )
    # Only stamp the filter-level last_email_sent_at on REAL scheduled
    # runs (force=False). A manual force=true smoke test stamping this
    # timestamp poisoned the next 12:00 UTC cron — the scheduler hit
    # the 23h cooldown and silently skipped. Manual runs are diagnostic
    # by design and must not affect scheduled behavior.
    if not force:
        await db.execute(
            update(BuyboxFilter)
            .where(BuyboxFilter.id == f.id)
            .values(last_email_sent_at=datetime.now(timezone.utc))
        )
    await db.commit()
    return len(parcels)


async def run_once(force: bool = False) -> dict:
    """Send the digest for every eligible filter. Returns
    ``{"filters": N, "parcels": M}`` for callers/CLI.

    ``force`` bypasses the 23h cooldown — intended for manual smoke
    tests, not for cron use.
    """
    filters_processed = 0
    parcels_emailed = 0
    eligible_total = 0
    errors: list[str] = []
    async with long_running_session_maker() as db:
        eligible = await _eligible_filters(db, force=force)
        eligible_total = len(eligible)
        logger.info("digest sweep: %d eligible filter(s)", eligible_total)
        for f in eligible:
            logger.info(
                "digest considering filter id=%s name=%r enabled=%s last_sent=%s",
                f.id, f.name, f.daily_email_enabled, f.last_email_sent_at,
            )
            try:
                sent = await _send_digest_for_filter(db, f, force=force)
                filters_processed += 1
                parcels_emailed += sent
            except Exception as exc:
                logger.exception("digest filter=%s failed; continuing", f.name)
                errors.append(f"{f.name}: {type(exc).__name__}: {exc}")
                await db.rollback()
    return {
        "filters": filters_processed,
        "parcels": parcels_emailed,
        "eligible_total": eligible_total,
        "errors": errors,
    }


# ─── Dramatiq actor (for manual / ad-hoc triggers) ───────────────────────

@dramatiq.actor(max_retries=0, time_limit=10 * 60 * 1000)
def send_daily_digest_actor() -> None:
    asyncio.run(run_once())


# ─── CLI entry point ─────────────────────────────────────────────────────

def _cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    result = asyncio.run(run_once())
    print(f"digest done: {result}")
    # Non-zero exit when any filter errored so Railway's cron logs
    # surface the failure instead of silently marking the run green.
    sys.exit(1 if result.get("errors") else 0)


if __name__ == "__main__":
    _cli()
