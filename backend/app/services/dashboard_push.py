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

Board sync is DECOUPLED from email: filters feed the board via their own
``filter_json.dashboardEnabled`` flag, independent of ``daily_email_enabled``.
A filter can populate the board without emailing (dashboard-only) and vice
versa. (Historically the push rode ``_eligible_filters``, gated on
``daily_email_enabled`` — turning off a digest silently darkened the board.)

Run modes:
  * ``python -m app.services.dashboard_push``              — all dashboard-enabled filters
  * ``python -m app.services.dashboard_push --filter-id N`` — one filter (backfill/test)
  * called automatically at the end of ``daily_email.run_once`` (once/day at the
    digest send hour), so the board refreshes on the same cadence as the email.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time

import asyncpg
from sqlalchemy import select, text

from app.config import settings
from app.db import long_running_session_maker
from app.models.buybox_filter import BuyboxFilter
from app.models.use_case import UseCase
from app.workers.daily_email import (
    DigestParcel,
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
    "score", "tier", "verdict_basis", "asset_type", "factors", "soft_flags",
    "listing_source", "sale_price", "price_per_ac", "days_on_market",
    "broker_company", "broker_contact", "broker_phone", "broker_email",
    # Owner contact from the matched listing (CoStar owner data) — the
    # actionable outreach channel for land (phone + direct mail). Named
    # *_listing / owner_phone / owner_address to avoid colliding with the
    # dashboard-owned MANUAL `owner_contact` disposition column (never pushed).
    "owner_phone", "owner_address", "owner_contact_listing",
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


def _asset_label(uses: set[str]) -> str:
    """Collapse the set of use-case slugs a parcel qualified under into the
    board's asset_type value."""
    has_lgc = "luxury_garage_condo" in uses
    has_ss = "self_storage" in uses
    if has_lgc and has_ss:
        return "both"
    if has_lgc:
        return "luxury_garage_condo"
    return "self_storage"


def _row_for(p: DigestParcel, sup: dict, asset_type: str) -> dict:
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
        "asset_type": asset_type,
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
        "owner_phone": p.owner_phone,
        "owner_address": p.owner_address,
        "owner_contact_listing": p.owner_contact,
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


def _pl_dsn() -> str:
    """ParcelLogic's own asyncpg DSN (plain postgres form)."""
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _sync_dispositions_back(dashboard_conn) -> int:
    """Mirror the dashboard board's decided dispositions into ParcelLogic's
    ``deal_dispositions`` so the digest + listing alerts can suppress deals the
    owner already closed out — closing the one-way-sync gap.

    Pulls every ``deal_prospect`` row whose status isn't the default 'new',
    upserts them, then deletes any local row no longer decided on the board (a
    deal reverted to 'new' or removed) so suppression never sticks stale after
    an un-pass. Best-effort: the caller swallows failures so a disposition-sync
    hiccup never sinks the push/digest."""
    decided = await dashboard_conn.fetch(
        "SELECT parcel_id, status, decided_at FROM deal_prospect "
        "WHERE status IS NOT NULL AND status <> 'new'"
    )
    conn = await asyncpg.connect(_pl_dsn())
    try:
        async with conn.transaction():
            if decided:
                await conn.executemany(
                    """
                    INSERT INTO deal_dispositions (parcel_id, status, decided_at, synced_at)
                    VALUES ($1::bigint, $2::text, $3::timestamptz, now())
                    ON CONFLICT (parcel_id) DO UPDATE
                       SET status     = EXCLUDED.status,
                           decided_at = EXCLUDED.decided_at,
                           synced_at  = now()
                    """,
                    [(r["parcel_id"], r["status"], r["decided_at"]) for r in decided],
                )
            # Drop local rows the board no longer marks decided, so an un-passed
            # deal can surface again. Empty list → deletes all (nothing decided).
            await conn.execute(
                "DELETE FROM deal_dispositions WHERE NOT (parcel_id = ANY($1::bigint[]))",
                [r["parcel_id"] for r in decided],
            )
    finally:
        await conn.close()
    return len(decided)


async def _cleanup_delisted(dashboard_conn) -> int:
    """Remove board cards whose CoStar listing has delisted — but ONLY the ones
    the owner never triaged (status still 'new') and that a listing surfaced in
    the first place (listing_source set). A card moved to ANY other status
    (reviewing / loi_sent / watching / under_contract / passed / dead) is
    preserved no matter what. Self-correcting: if the parcel re-lists, the next
    push re-adds it as a fresh 'new' card. Best-effort.

    run_push only ever UPSERTs, so without this a listing-sourced card lingers on
    the board forever after the listing comes off market — the audit's
    'delisted parcels never removed' gap."""
    candidates = await dashboard_conn.fetch(
        "SELECT parcel_id FROM deal_prospect "
        "WHERE listing_source IS NOT NULL AND status = 'new'"
    )
    if not candidates:
        return 0
    ids = [r["parcel_id"] for r in candidates]
    # Which candidates STILL have a current matched listing in ParcelLogic?
    pl = await asyncpg.connect(_pl_dsn())
    try:
        still = await pl.fetch(
            "SELECT DISTINCT matched_parcel_id FROM forsale_listings "
            "WHERE matched_parcel_id = ANY($1::bigint[]) "
            "AND is_current = true AND match_confidence >= 0.85",
            ids,
        )
    finally:
        await pl.close()
    still_listed = {r["matched_parcel_id"] for r in still}
    stale = [pid for pid in ids if pid not in still_listed]
    if stale:
        # Re-assert status='new' + listing_source in the DELETE so a card the
        # owner triaged between the SELECT and now is never removed.
        await dashboard_conn.execute(
            "DELETE FROM deal_prospect WHERE parcel_id = ANY($1::bigint[]) "
            "AND status = 'new' AND listing_source IS NOT NULL",
            stale,
        )
    return len(stale)


async def _dashboard_filters(db) -> list[BuyboxFilter]:
    """Filters that feed the Deal Pipeline board.

    Selected by the ``dashboardEnabled`` flag in ``filter_json``, INDEPENDENT of
    ``daily_email_enabled`` — board-sync and email are separate toggles. There is
    no 23h cooldown here (that gates re-EMAILS): the board always reflects the
    full current set of dashboard-enabled filters."""
    stmt = (
        select(BuyboxFilter)
        .where(BuyboxFilter.filter_json["dashboardEnabled"].astext == "true")
        .order_by(BuyboxFilter.updated_at.desc())
    )
    return list((await db.execute(stmt)).scalars())


async def run_push(force: bool = True, filter_id: int | None = None) -> dict:
    """Sync current buy-box deals into the dashboard's deal_prospect table.

    ``force`` is retained for caller/CLI compatibility but no longer affects
    filter selection: the board always reflects the full current set of
    dashboard-enabled filters (there is no board-side cooldown). ``filter_id``
    restricts to one filter (backfill / testing) regardless of its flags."""
    t0 = time.monotonic()
    dsn = _dashboard_dsn()
    if not dsn:
        logger.info("dashboard_push: PORTFOLIO_DASHBOARD_DATABASE_URL unset — skipping")
        return {"status": "skipped", "reason": "no_dsn"}

    # Dedupe by parcel_id (a parcel can match multiple filters; the board shows
    # one card, highest score wins). `uses` accumulates every use-case slug the
    # parcel qualified under across all filters, so a parcel eligible under both
    # a self_storage AND a luxury_garage_condo filter lands as asset_type='both'.
    best: dict[int, tuple[DigestParcel, dict]] = {}
    uses: dict[int, set[str]] = {}
    async with long_running_session_maker() as db:
        if filter_id is not None:
            f = (
                await db.execute(select(BuyboxFilter).where(BuyboxFilter.id == filter_id))
            ).scalar_one_or_none()
            filters = [f] if f else []
        else:
            filters = await _dashboard_filters(db)
        for f in filters:
            slug = await db.scalar(
                select(UseCase.slug).where(UseCase.id == f.use_case_id)
            )
            asset = "luxury_garage_condo" if slug == "luxury_garage_condo" else "self_storage"
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
                uses.setdefault(d.parcel_id, set()).add(asset)
                prev = best.get(d.parcel_id)
                if prev is None or (d.score or 0) > (prev[0].score or 0):
                    best[d.parcel_id] = (d, sup.get(d.parcel_id, {}))

    # No early-return on empty rows: the disposition read-back below must run
    # even with 0 fresh deals (a passed/dead deal can exist with nothing new to
    # push today). The push itself is guarded by `if rows:`.
    rows = [
        _row_for(d, s, _asset_label(uses.get(pid, set())))
        for pid, (d, s) in best.items()
    ]

    sql = _upsert_sql()
    conn = await asyncpg.connect(dsn, ssl="require")
    dispositions = 0
    delisted = 0
    try:
        if rows:
            async with conn.transaction():
                for r in rows:
                    await conn.execute(sql, *[r[c] for c in _FACT_COLUMNS])
        # Pull the board's dispositions back regardless of whether there were new
        # facts to push — a passed/dead deal can exist with 0 fresh deals today.
        # Best-effort: a read-back failure must not fail the push/digest.
        try:
            dispositions = await _sync_dispositions_back(conn)
        except Exception:
            logger.exception("dashboard_push: disposition read-back failed; push unaffected")
        # Sweep off untouched cards whose listing has delisted. Best-effort.
        try:
            delisted = await _cleanup_delisted(conn)
        except Exception:
            logger.exception("dashboard_push: delisted cleanup failed; push unaffected")
        # Record push-health so the board can show "last synced" and a stale/failed
        # sync is visible. Best-effort; a missing push_run table (migration lag)
        # must not fail the sync.
        try:
            await conn.execute(
                "INSERT INTO push_run (status, deals_synced, dispositions, "
                "delisted_removed, filters, duration_ms) VALUES ('ok',$1,$2,$3,$4,$5)",
                len(rows), dispositions, delisted, len(filters),
                int((time.monotonic() - t0) * 1000),
            )
        except Exception:
            logger.exception("dashboard_push: push_run record failed; sync unaffected")
    finally:
        await conn.close()

    logger.info(
        "dashboard_push: synced %d deal(s) across %d filter(s); %d disposition(s) pulled back; "
        "%d delisted card(s) removed",
        len(rows), len(filters), dispositions, delisted,
    )
    return {
        "status": "ok",
        "synced": len(rows),
        "filters": len(filters),
        "dispositions": dispositions,
        "delisted_removed": delisted,
    }


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
