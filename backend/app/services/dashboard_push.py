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
    _is_demoted,
    _top_parcels_for_filter,
)

logger = logging.getLogger(__name__)

# Cap per filter — the board is a triage queue, not a data dump. Raised to fit the full
# LGC Hot deals lane, which exceeded the old 500 cap ("board truncated" warnings). Still a
# real ceiling: if a lane exceeds this we log a truncation warning (no silent caps).
_PUSH_LIMIT = 2000

# Fact columns pushed to deal_prospect, in positional-parameter order.
# parcel_id is the conflict key; the disposition columns are intentionally
# ABSENT so re-syncs never overwrite the user's decisions.
_FACT_COLUMNS = [
    "parcel_id", "apn", "jurisdiction_id", "jurisdiction_name",
    "address", "city", "state", "zip", "owner_name", "acres",
    "score", "tier", "verdict_basis", "use_verdict", "asset_type", "factors", "soft_flags",
    # Actionable-vs-Verify, computed ONCE at the source by daily_email._is_demoted
    # and pushed so the board READS it. Deliberately not re-derived dashboard-side
    # from raw soft_flags: that produced two definitions of "Actionable" (the
    # digest tiered on disqualifying flags only, the board tabs on "any flag at
    # all"), so the board showed ~0 Actionable while 342 cards qualified. Two
    # writers of one meaning is the A-4.7 problem; this keeps a single definition.
    "is_actionable",
    "listing_source", "sale_price", "price_per_ac", "days_on_market",
    "broker_company", "broker_contact", "broker_phone", "broker_email",
    # Owner contact from the matched listing (CoStar owner data) — the
    # actionable outreach channel for land (phone + direct mail). Named
    # *_listing / owner_phone / owner_address to avoid colliding with the
    # dashboard-owned MANUAL `owner_contact` disposition column (never pushed).
    "owner_phone", "owner_address", "owner_contact_listing",
    "lat", "lng", "parcellogic_link",
    # Assessor situs (parcels.address/city) alongside the listing-preferred
    # `address` above. When a parcel has a CoStar listing, `address` shows the
    # marketing/listing address (e.g. "400 Campus Drive") which can differ from
    # the situs the operator clicked ("91 Cottontail Ln"); surfacing both kills
    # the "is this the same property?" doubt. The card renders situs as a
    # secondary line when it differs from address.
    "situs_address", "situs_city",
    # Triage context (2026-07-25 audit A-2). The card previously carried score,
    # price and acres — but none of the wealth/demand facts the buy box is
    # DEFINED by, so three of the six things the operator actually triages on
    # (3-mi population, ring wealth, saturation) were unanswerable from the card
    # and the `factors` JSON couldn't disambiguate "fine" from "unmeasured".
    # NULL always means unmeasured here, never zero.
    "ring_median_home_value", "ring_median_hhi", "ring_hnw_households",
    "pop_3mi", "sqft_per_capita_3mi",
]
# Keep-market columns (garage-condo lane, Phase B): lane / supported $/SF band /
# velocity flag from ParcelLogic's parcel_keep_metrics. They are NEW nullable columns
# on the dashboard's deal_prospect, added by a dashboard-repo migration that may land
# after this code deploys — so they are NOT in _FACT_COLUMNS. run_push detects which of
# them exist on the board once per run (information_schema) and only then includes
# them, so the push never fails on a board that hasn't migrated yet.
_KEEP_COLUMNS = ["keep_lane", "keep_price_low", "keep_price_high", "keep_velocity_flag"]
# Board asset types that carry keep data (a storage-only card gets NULLs).
_KEEP_ASSET_TYPES = ("luxury_garage_condo", "both")
_JSONB_COLUMNS = {"factors", "soft_flags"}
# NUMERIC target columns — cast the bind to float8 so asyncpg encodes a Python
# float (it demands Decimal for a bare numeric param); PG coerces float8→numeric.
_FLOAT_COLUMNS = {"acres", "sale_price", "price_per_ac", "sqft_per_capita_3mi"}

# Board statuses that mean "never show me this parcel again". Their cards are
# deleted from the board once mirrored into deal_dispositions, and the mirror row
# is kept as a tombstone so the parcel is never re-pushed — even when a fresh
# CoStar report lists it again. Everything else (reviewing / watching / loi_sent
# / under_contract) stays on the board untouched.
_CLOSED_STATUSES = ("passed", "dead")


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
               p.owner_mailing_address AS owner_mailing_address,
               p.owner_mailing_csz AS owner_mailing_csz,
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


_VIABLE = ("permitted", "conditional")


def _promote_lgc_verdict(row: dict, lgc_verdict: str | None) -> None:
    """On a 'both' card the self_storage row wins precedence, so its use_verdict is
    pushed. When storage is unconfirmed (unclear/NULL) but the garage condo is BY RIGHT
    (Nache 2026-10-15: pitched as the light-industrial / storage use), show the garage
    condo's verdict instead — otherwise the card reads "not confirmed" and the
    dashboard's LOI gate blocks a deal we can pursue."""
    if (row.get("asset_type") == "both"
            and row.get("use_verdict") not in _VIABLE
            and lgc_verdict in _VIABLE):
        row["use_verdict"] = lgc_verdict


def _owner_mailing(sup: dict) -> str | None:
    """Compose the assessor owner MAILING address (street + city/state/zip) from
    the _supplement row, as a single line to match the board's owner_address
    field. Used as the fallback for off-market needle cards that have no CoStar
    listing owner (the 2026-07-22 owner-mailing backfill populated these on
    parcels for ~93% of needles)."""
    street = (sup.get("owner_mailing_address") or "").strip()
    csz = (sup.get("owner_mailing_csz") or "").strip()
    combined = ", ".join(x for x in (street, csz) if x)
    return combined or None


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
        # Effective use-verdict → the board's viable-vs-verify tier. prohibited
        # is hard-gated out upstream, so this is permitted/conditional (viable)
        # or unclear/NULL (verify / worth a look).
        "use_verdict": p.use_verdict,
        "asset_type": asset_type,
        "factors": json.dumps(p.factors or []),
        # One definition, evaluated here — see the _FACT_COLUMNS note.
        "is_actionable": not _is_demoted(p),
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
        # Owner mailing address: prefer the CoStar listing owner (has phone too),
        # else fall back to the assessor owner-mailing backfilled on the parcel —
        # so off-market needle cards show a mailable owner address, not just the
        # ~104 CoStar-listed deals. owner_name already flows via DigestParcel.
        "owner_address": p.owner_address or _owner_mailing(sup),
        "owner_contact_listing": p.owner_contact,
        "lat": p.lat,
        "lng": p.lng,
        "parcellogic_link": _parcel_link(p),
        # Situs is always the assessor address/city, regardless of listing.
        "situs_address": p.address,
        "situs_city": sup.get("parcel_city"),
        # Triage context. All NULL-safe: NULL = unmeasured, which the card must
        # render as "—"/unknown rather than as a zero or a failure.
        "ring_median_home_value": p.ring_median_home_value,
        "ring_median_hhi": p.ring_median_hhi,
        "ring_hnw_households": p.ring_hnw_households,
        "pop_3mi": p.pop_3mi,
        "sqft_per_capita_3mi": p.sqft_per_capita_3mi,
    }


def _upsert_sql(columns: list[str] | None = None) -> str:
    cols = list(columns) if columns is not None else _FACT_COLUMNS
    placeholders = []
    for i, c in enumerate(cols, start=1):
        ph = f"${i}"
        if c in _JSONB_COLUMNS:
            ph += "::jsonb"
        elif c in _FLOAT_COLUMNS:
            ph += "::float8"
        placeholders.append(ph)
    set_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "parcel_id")
    return (
        f"INSERT INTO deal_prospect ({', '.join(cols)}, last_synced_at) "
        f"VALUES ({', '.join(placeholders)}, now()) "
        f"ON CONFLICT (parcel_id) DO UPDATE SET {set_clause}, last_synced_at = now()"
    )


async def _board_keep_columns(dashboard_conn) -> list[str]:
    """Which _KEEP_COLUMNS exist on the board's deal_prospect (in _KEEP_COLUMNS order).

    Detected once per run so the push degrades to the pre-keep column set on a board
    whose migration hasn't landed, instead of failing the whole sync."""
    rows = await dashboard_conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'deal_prospect' AND table_schema = current_schema() "
        "AND column_name = ANY($1::text[])",
        _KEEP_COLUMNS,
    )
    present = {r["column_name"] for r in rows}
    return [c for c in _KEEP_COLUMNS if c in present]


async def _keep_metrics(parcel_ids: list[int]) -> dict[int, dict]:
    """parcel_keep_metrics for the given parcels, keyed by parcel_id, mapped onto the
    board's keep_* column names. Separate (best-effort at the call site) so the
    digest's own selection SQL stays untouched."""
    if not parcel_ids:
        return {}
    conn = await asyncpg.connect(_pl_dsn())
    try:
        rows = await conn.fetch(
            "SELECT parcel_id, keep_lane, price_band_low, price_band_high, velocity_flag "
            "FROM parcel_keep_metrics WHERE parcel_id = ANY($1::bigint[])",
            parcel_ids,
        )
    finally:
        await conn.close()
    return {
        r["parcel_id"]: {
            "keep_lane": r["keep_lane"],
            "keep_price_low": r["price_band_low"],
            "keep_price_high": r["price_band_high"],
            "keep_velocity_flag": r["velocity_flag"],
        }
        for r in rows
    }


def _apply_keep(row: dict, keep: dict | None) -> None:
    """Attach the keep_* fields: garage-condo / 'both' cards only, NULL otherwise
    (NULL = unmeasured / not applicable, never a value)."""
    use = row.get("asset_type") in _KEEP_ASSET_TYPES and keep
    for c in _KEEP_COLUMNS:
        row[c] = keep.get(c) if use else None


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
            # deal can surface again — EXCEPT passed/dead tombstones: their cards
            # are deleted from the board on purpose (_purge_closed), so absence
            # from the board is expected and must not resurrect them.
            await conn.execute(
                "DELETE FROM deal_dispositions WHERE NOT (parcel_id = ANY($1::bigint[])) "
                "AND NOT (status = ANY($2::text[]))",
                [r["parcel_id"] for r in decided],
                list(_CLOSED_STATUSES),
            )
    finally:
        await conn.close()
    return len(decided)


async def _closed_parcel_ids() -> set[int]:
    """Parcels the owner passed on or killed — never pushed to the board again."""
    conn = await asyncpg.connect(_pl_dsn())
    try:
        rows = await conn.fetch(
            "SELECT parcel_id FROM deal_dispositions WHERE status = ANY($1::text[])",
            list(_CLOSED_STATUSES),
        )
    finally:
        await conn.close()
    return {r["parcel_id"] for r in rows}


async def _purge_closed(dashboard_conn, closed: set[int]) -> int:
    """Delete passed/dead cards from the board. Only ids already tombstoned in
    deal_dispositions are eligible, and the status is re-asserted in the DELETE,
    so a card un-passed since the read-back is never removed."""
    if not closed:
        return 0
    res = await dashboard_conn.execute(
        "DELETE FROM deal_prospect WHERE parcel_id = ANY($1::bigint[]) "
        "AND status = ANY($2::text[])",
        list(closed),
        list(_CLOSED_STATUSES),
    )
    return int(res.split()[-1])


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
    # one card). Precedence is by LANE, not by score — self_storage wins over
    # luxury_garage_condo, because scores from different filters aren't on a
    # comparable scale (see the loop below). `uses` accumulates every use-case
    # slug the parcel qualified under across all filters, so a parcel eligible
    # under both a self_storage AND an LGC filter lands as asset_type='both'.
    best: dict[int, tuple[DigestParcel, dict]] = {}
    # Which lane's row currently backs each card — drives the deterministic
    # self_storage-wins precedence below (see the comment there).
    best_asset: dict[int, str] = {}
    uses: dict[int, set[str]] = {}
    # The LGC lane's own verdict per parcel, so a 'both' card backed by an
    # unconfirmed storage row can still show the garage condo as by right.
    lgc_verdicts: dict[int, str | None] = {}
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
                db, f, include_notified=True, limit=_PUSH_LIMIT, slug=slug
            )
            if len(deals) >= _PUSH_LIMIT:
                logger.warning(
                    "dashboard_push: filter %s hit the %d-deal cap — board truncated",
                    f.id, _PUSH_LIMIT,
                )
            sup = await _supplement(db, [d.parcel_id for d in deals])
            for d in deals:
                uses.setdefault(d.parcel_id, set()).add(asset)
                if asset == "luxury_garage_condo":
                    lgc_verdicts[d.parcel_id] = d.use_verdict
                prev_asset = best_asset.get(d.parcel_id)
                # Which lane's row backs a dual-qualified card? NOT max(score):
                # a self_storage score and an LGC score come from different
                # filter_json (different bonuses/thresholds), so they are not on
                # a comparable scale — comparing them let an LGC row's
                # use_verdict/factors describe a card labelled 'both', and the
                # winner flipped as either filter's config changed. Explicit
                # precedence instead: self_storage wins, because it is the
                # ordinance-grounded verdict (the LGC verdict is derived from
                # sibling columns). `uses` still records both lanes, so
                # asset_type='both' is unaffected.
                if prev_asset is None or (
                    asset == "self_storage" and prev_asset != "self_storage"
                ):
                    best[d.parcel_id] = (d, sup.get(d.parcel_id, {}))
                    best_asset[d.parcel_id] = asset

    # No early-return on empty rows: the disposition read-back below must run
    # even with 0 fresh deals (a passed/dead deal can exist with nothing new to
    # push today). The push itself is guarded by `if rows:`.
    rows = [
        _row_for(d, s, _asset_label(uses.get(pid, set())))
        for pid, (d, s) in best.items()
    ]
    for r in rows:
        _promote_lgc_verdict(r, lgc_verdicts.get(r["parcel_id"]))

    # Keep-market facts for garage-condo cards. Best-effort: a missing table (migration
    # lag) or a read failure pushes the cards without them rather than failing the sync.
    try:
        keep = await _keep_metrics(
            [r["parcel_id"] for r in rows if r.get("asset_type") in _KEEP_ASSET_TYPES]
        )
    except Exception:
        logger.exception("dashboard_push: keep-metrics read failed; pushing without them")
        keep = {}
    for r in rows:
        _apply_keep(r, keep.get(r["parcel_id"]))

    conn = await asyncpg.connect(dsn, ssl="require")
    dispositions = 0
    delisted = 0
    purged = 0
    try:
        # Pull the board's dispositions back FIRST, regardless of whether there are
        # new facts to push, so today's passed/dead marks are tombstoned before the
        # upsert below could touch those parcels. Best-effort: a read-back failure
        # must not fail the push/digest — but then nothing is purged this run.
        synced_back = False
        try:
            dispositions = await _sync_dispositions_back(conn)
            synced_back = True
        except Exception:
            logger.exception("dashboard_push: disposition read-back failed; push unaffected")
        try:
            closed = await _closed_parcel_ids()
        except Exception:
            logger.exception("dashboard_push: closed-deal lookup failed; push unaffected")
            closed = set()
        rows = [r for r in rows if r["parcel_id"] not in closed]
        # Include the keep_* columns only where the board has them (see _KEEP_COLUMNS).
        try:
            keep_cols = await _board_keep_columns(conn)
        except Exception:
            logger.exception("dashboard_push: keep-column detection failed; pushing without them")
            keep_cols = []
        columns = _FACT_COLUMNS + keep_cols
        sql = _upsert_sql(columns)
        if rows:
            async with conn.transaction():
                for r in rows:
                    await conn.execute(sql, *[r.get(c) for c in columns])
        if synced_back:
            try:
                purged = await _purge_closed(conn, closed)
            except Exception:
                logger.exception("dashboard_push: closed-card purge failed; push unaffected")
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
        "%d delisted card(s) removed; %d passed/dead card(s) purged",
        len(rows), len(filters), dispositions, delisted, purged,
    )
    return {
        "status": "ok",
        "synced": len(rows),
        "filters": len(filters),
        "dispositions": dispositions,
        "delisted_removed": delisted,
        "closed_purged": purged,
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Push buy-box deals to the dashboard board.")
    ap.add_argument("--filter-id", type=str, default=None,
                    help="sync a single buybox_filters.id (a UUID). Was typed int, which could never match the uuid PK, so the flag was silently inert.")
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
