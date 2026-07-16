"""Push matched buy-box deals into the portfolio dashboard's Supabase.

The dashboard runs on a SEPARATE Supabase project, so its Deal Pipeline board
can't JOIN against ParcelLogic — deals are pushed. This reuses the digest's own
selection (``daily_email._top_parcels_for_filter``) so the board shows exactly
what the buy-box email would, then upserts each deal into the dashboard's
``deal_prospect`` table.

Only the FACT columns are written; the dashboard-owned disposition columns
(status / note / owner_contact / decided_*) are excluded from the DO UPDATE set
so a re-sync never clobbers the user's decisions. Idempotent.

No-op unless ``PORTFOLIO_DASHBOARD_DATABASE_URL`` is set.

Run modes:
  * ``python -m app.services.dashboard_push``              — all email-enabled filters
  * ``python -m app.services.dashboard_push --filter-id N`` — one filter (backfill/test)
  * called automatically at the end of ``daily_email.run_once`` (once/day at the
    digest send hour), so the board refreshes on the same cadence as the email.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

import asyncpg
from sqlalchemy import select, text

from app.config import settings
from app.db import long_running_session_maker
from app.models.buybox_filter import BuyboxFilter
from app.workers.daily_email import (
    DigestParcel,
    _eligible_filters,
    _parcel_link,
    _top_parcels_for_filter,
)

logger = logging.getLogger(__name__)

# Cap per filter — the board is a triage queue, not a data dump. Listed-deal
# filters return well under this; log if we ever truncate (no silent caps).
_PUSH_LIMIT = 500

# Fact columns pushed to deal_prospect, in positional-parameter order.
# parcel_id is the conflict key; the disposition columns are intentionally
# ABSENT so re-syncs never overwrite the user's decisions.
_FACT_COLUMNS = [
    "parcel_id", "apn", "jurisdiction_id", "jurisdiction_name",
    "address", "city", "state", "zip", "owner_name", "acres",
    "score", "tier", "verdict_basis", "factors", "soft_flags",
    "listing_source", "sale_price", "price_per_ac", "days_on_market",
    "broker_company", "broker_contact", "broker_phone", "broker_email",
    "lat", "lng", "parcellogic_link",
]
_JSONB_COLUMNS = {"factors", "soft_flags"}
# NUMERIC target columns — cast the bind to float8 so asyncpg encodes a Python
# float (it demands Decimal for a bare numeric param); PG coerces float8→numeric.
_FLOAT_COLUMNS = {"acres", "sale_price", "price_per_ac"}


async def _supplement(db, parcel_ids: list[int]) -> dict[int, dict]:
    """Fetch city/state/zip/price_per_ac (not carried on DigestParcel). Prefers
    the current listing's location — better for outreach — over the parcel's."""
    if not parcel_ids:
        return {}
    rows = await db.execute(
        text(
            """
        SELECT p.id AS parcel_id,
               p.city AS parcel_city, p.state AS parcel_state,
               lst.address AS listing_address, lst.city AS listing_city,
               lst.state AS listing_state, lst.zip AS listing_zip,
               lst.price_per_ac AS price_per_ac
          FROM parcels p
          LEFT JOIN LATERAL (
              SELECT address, city, state, zip, price_per_ac
                FROM forsale_listings
               WHERE matched_parcel_id = p.id
                 AND is_current = true
                 AND match_confidence >= 0.85
               ORDER BY last_seen_at DESC
               LIMIT 1
          ) lst ON true
         WHERE p.id = ANY(:ids)
        """
        ),
        {"ids": parcel_ids},
    )
    return {r._mapping["parcel_id"]: dict(r._mapping) for r in rows}


def _row_for(p: DigestParcel, sup: dict) -> dict:
    """Flatten a DigestParcel + supplement into a deal_prospect fact row."""
    has_listing = bool(p.listing_source)
    address = (sup.get("listing_address") if has_listing else None) or p.address
    city = (sup.get("listing_city") if has_listing else None) or sup.get("parcel_city")
    state = (sup.get("listing_state") if has_listing else None) or sup.get("parcel_state")
    zip_ = sup.get("listing_zip") if has_listing else None
    ppa = sup.get("price_per_ac")
    return {
        "parcel_id": p.parcel_id,
        "apn": p.apn,
        "jurisdiction_id": p.jurisdiction_id,
        "jurisdiction_name": p.jurisdiction_name,
        "address": address,
        "city": city,
        "state": state,
        "zip": zip_,
        "owner_name": p.owner_name,
        "acres": p.acres,
        "score": p.score,
        "tier": p.tier,
        "verdict_basis": p.verdict_basis,
        "factors": json.dumps(p.factors or []),
        "soft_flags": json.dumps(
            [{"emoji": e, "label": lbl} for e, lbl in (p.soft_flags or [])]
        ),
        "listing_source": p.listing_source,
        "sale_price": p.listing_sale_price,
        "price_per_ac": float(ppa) if ppa is not None else None,
        "days_on_market": p.listing_dom,
        "broker_company": p.listing_broker_company,
        "broker_contact": p.listing_broker_contact,
        "broker_phone": p.listing_broker_phone,
        "broker_email": p.listing_broker_email,
        "lat": p.lat,
        "lng": p.lng,
        "parcellogic_link": _parcel_link(p),
    }


def _upsert_sql() -> str:
    placeholders = []
    for i, c in enumerate(_FACT_COLUMNS, start=1):
        ph = f"${i}"
        if c in _JSONB_COLUMNS:
            ph += "::jsonb"
        elif c in _FLOAT_COLUMNS:
            ph += "::float8"
        placeholders.append(ph)
    set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in _FACT_COLUMNS if c != "parcel_id")
    return (
        f"INSERT INTO deal_prospect ({', '.join(_FACT_COLUMNS)}, last_synced_at) "
        f"VALUES ({', '.join(placeholders)}, now()) "
        f"ON CONFLICT (parcel_id) DO UPDATE SET {set_clause}, last_synced_at = now()"
    )


def _dashboard_dsn() -> str | None:
    dsn = settings.portfolio_dashboard_database_url
    if not dsn:
        return None
    # asyncpg wants a plain postgres DSN, not the SQLAlchemy +asyncpg form.
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


async def run_push(force: bool = True, filter_id: int | None = None) -> dict:
    """Sync current buy-box deals into the dashboard's deal_prospect table.

    ``force`` (default True) ignores the digest's 23h cooldown — the board should
    reflect the full current set regardless of when the email last sent.
    ``filter_id`` restricts to one filter (backfill / testing) regardless of its
    enabled flag."""
    dsn = _dashboard_dsn()
    if not dsn:
        logger.info("dashboard_push: PORTFOLIO_DASHBOARD_DATABASE_URL unset — skipping")
        return {"status": "skipped", "reason": "no_dsn"}

    # Dedupe by parcel_id (a parcel can match multiple filters; the board shows
    # one card, highest score wins).
    best: dict[int, tuple[DigestParcel, dict]] = {}
    async with long_running_session_maker() as db:
        if filter_id is not None:
            f = (
                await db.execute(select(BuyboxFilter).where(BuyboxFilter.id == filter_id))
            ).scalar_one_or_none()
            filters = [f] if f else []
        else:
            filters = await _eligible_filters(db, force=force)
        for f in filters:
            deals = await _top_parcels_for_filter(
                db, f, include_notified=True, limit=_PUSH_LIMIT
            )
            if len(deals) >= _PUSH_LIMIT:
                logger.warning(
                    "dashboard_push: filter %s hit the %d-deal cap — board truncated",
                    f.id, _PUSH_LIMIT,
                )
            sup = await _supplement(db, [d.parcel_id for d in deals])
            for d in deals:
                prev = best.get(d.parcel_id)
                if prev is None or (d.score or 0) > (prev[0].score or 0):
                    best[d.parcel_id] = (d, sup.get(d.parcel_id, {}))

    rows = [_row_for(d, s) for d, s in best.values()]
    if not rows:
        logger.info("dashboard_push: 0 deals to sync (%d filter(s))", len(filters))
        return {"status": "ok", "synced": 0, "filters": len(filters)}

    sql = _upsert_sql()
    conn = await asyncpg.connect(dsn, ssl="require")
    try:
        async with conn.transaction():
            for r in rows:
                await conn.execute(sql, *[r[c] for c in _FACT_COLUMNS])
    finally:
        await conn.close()

    logger.info(
        "dashboard_push: synced %d deal(s) across %d filter(s)", len(rows), len(filters)
    )
    return {"status": "ok", "synced": len(rows), "filters": len(filters)}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Push buy-box deals to the dashboard board.")
    ap.add_argument("--filter-id", type=int, default=None, help="sync a single filter id")
    ap.add_argument(
        "--respect-cooldown",
        action="store_true",
        help="only sync filters due for an email (default: sync all)",
    )
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = asyncio.run(
        run_push(force=not args.respect_cooldown, filter_id=args.filter_id)
    )
    print(f"dashboard_push: {result}")


if __name__ == "__main__":
    main()
