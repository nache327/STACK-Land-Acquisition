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
from app.db import async_session_maker
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


# ─── Selection ────────────────────────────────────────────────────────────

# Don't re-fire within 23h. Slightly under 24h so a 7am cron never skips
# a day because of clock drift / late starts.
_RESEND_INTERVAL = timedelta(hours=23)
# Soft floor on score — we want "noteworthy" parcels in the digest, not
# the bottom of the score distribution. Maps roughly to the user spec's
# `classification IN ('match', 'borderline')`.
_MIN_SCORE = 40


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
    sql = text(
        """
        SELECT
            p.id            AS parcel_id,
            p.apn           AS apn,
            p.address       AS address,
            p.owner_name    AS owner_name,
            pbs.score       AS score,
            pbs.tier        AS tier,
            pbs.factors     AS factors,
            j.id            AS jurisdiction_id,
            j.name          AS jurisdiction_name
        FROM parcel_buybox_scores pbs
        JOIN parcels p       ON p.id = pbs.parcel_id
        JOIN jurisdictions j ON j.id = p.jurisdiction_id
        WHERE pbs.buybox_filter_id = :fid
          AND pbs.notified_at IS NULL
          AND pbs.score >= :min_score
        ORDER BY pbs.score DESC, pbs.parcel_id
        LIMIT :lim
        """
    )
    rows = await db.execute(
        sql, {"fid": f.id, "min_score": _MIN_SCORE, "lim": f.daily_email_top_n}
    )
    out: list[DigestParcel] = []
    for r in rows:
        m = r._mapping
        out.append(
            DigestParcel(
                parcel_id=m["parcel_id"],
                apn=m["apn"],
                address=m["address"],
                owner_name=m["owner_name"],
                score=m["score"],
                tier=m["tier"],
                factors=list(m["factors"] or []),
                jurisdiction_id=str(m["jurisdiction_id"]),
                jurisdiction_name=m["jurisdiction_name"],
            )
        )
    return out


# ─── Rendering ────────────────────────────────────────────────────────────

def _parcel_link(p: DigestParcel) -> str:
    base = settings.digest_dashboard_base_url.rstrip("/")
    return f"{base}/dashboard/{p.jurisdiction_id}?parcel={p.apn}"


def _top_factors(p: DigestParcel, n: int = 3) -> list[dict]:
    """Top-N |delta| contributions; delta is signed."""
    return sorted(p.factors, key=lambda f: abs(float(f.get("delta", 0))), reverse=True)[:n]


def _render_subject(filter_name: str, parcels: list[DigestParcel]) -> str:
    n = len(parcels)
    cities = sorted({p.jurisdiction_name for p in parcels})
    if len(cities) == 1:
        return f"{n} new match{'es' if n != 1 else ''} in {cities[0]} buy-box ({filter_name})"
    return f"{n} new match{'es' if n != 1 else ''} in your buy-box ({filter_name})"


def _render_text(filter_name: str, parcels: list[DigestParcel]) -> str:
    lines = [f"Daily buy-box digest — {filter_name}", ""]
    for p in parcels:
        lines.append(f"• {p.address or p.apn} ({p.jurisdiction_name})")
        if p.owner_name:
            lines.append(f"  Owner: {p.owner_name}")
        lines.append(f"  Score: {p.score} ({p.tier})")
        for f in _top_factors(p):
            sign = "+" if float(f.get("delta", 0)) >= 0 else ""
            lines.append(
                f"    {f.get('label', '?')}: {sign}{f.get('delta')} — {f.get('reason', '')}"
            )
        lines.append(f"  {_parcel_link(p)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_html(filter_name: str, parcels: list[DigestParcel]) -> str:
    rows: list[str] = []
    for p in parcels:
        title = html_lib.escape(p.address or p.apn)
        city = html_lib.escape(p.jurisdiction_name)
        owner = html_lib.escape(p.owner_name or "")
        link = html_lib.escape(_parcel_link(p))
        factor_items = "".join(
            f"<li><strong>{html_lib.escape(str(f.get('label', '?')))}</strong>: "
            f"{'+' if float(f.get('delta', 0)) >= 0 else ''}{html_lib.escape(str(f.get('delta')))} "
            f"— {html_lib.escape(str(f.get('reason', '')))}</li>"
            for f in _top_factors(p)
        )
        owner_html = f"<div style='color:#64748b;font-size:13px'>Owner: {owner}</div>" if owner else ""
        rows.append(
            f"""
            <div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin:12px 0;background:#fff">
              <div style="font-weight:600;color:#0f172a;font-size:15px">
                <a href="{link}" style="color:#0f172a;text-decoration:none">{title}</a>
              </div>
              <div style="color:#475569;font-size:13px;margin-top:2px">{city}</div>
              {owner_html}
              <div style="margin-top:8px;font-size:13px;color:#0f172a">
                Score <strong>{p.score}</strong> · {html_lib.escape(p.tier)}
              </div>
              <ul style="margin:6px 0 0 16px;padding:0;color:#334155;font-size:12px">{factor_items}</ul>
              <a href="{link}" style="display:inline-block;margin-top:10px;color:#0369a1;font-size:13px">Open in dashboard →</a>
            </div>
            """
        )
    return f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a">
  <div style="max-width:560px;margin:0 auto">
    <h1 style="font-size:18px;margin:0 0 4px">Daily buy-box digest</h1>
    <div style="color:#64748b;font-size:13px;margin-bottom:8px">{html_lib.escape(filter_name)}</div>
    {''.join(rows)}
    <div style="color:#94a3b8;font-size:11px;margin-top:24px">
      Sent by ParcelLogic. Manage daily emails from the buy-box panel.
    </div>
  </div>
</body></html>"""


# ─── Send + bookkeeping ───────────────────────────────────────────────────

async def _send_digest_for_filter(db: AsyncSession, f: BuyboxFilter) -> int:
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
    await db.execute(
        update(ParcelBuyboxScore)
        .where(ParcelBuyboxScore.buybox_filter_id == f.id)
        .where(ParcelBuyboxScore.parcel_id.in_(parcel_ids))
        .values(notified_at=datetime.now(timezone.utc))
    )
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
    async with async_session_maker() as db:
        eligible = await _eligible_filters(db, force=force)
        eligible_total = len(eligible)
        logger.info("digest sweep: %d eligible filter(s)", eligible_total)
        for f in eligible:
            logger.info(
                "digest considering filter id=%s name=%r enabled=%s last_sent=%s",
                f.id, f.name, f.daily_email_enabled, f.last_email_sent_at,
            )
            try:
                sent = await _send_digest_for_filter(db, f)
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
    sys.exit(0)


if __name__ == "__main__":
    _cli()
