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
import os
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
    # Parcel centroid (lng/lat, SRID 4326) — passed in the deep-link so the
    # dashboard map flies straight to the site at close zoom instead of fitting
    # the whole county first (faster load, lands on the parcel).
    lat: float | None = None
    lng: float | None = None
    # Verdict provenance (catch #49 enforcement, 2026-07-07): the score alone
    # misleads — every digest row renders score + basis together.
    #   verdict_basis: 'human-verified' | 'ordinance-parsed' | 'heuristic'
    #                  | 'ungrounded muni'
    #   storage_dead:  True when a GROUNDED verdict says self-storage is
    #                  prohibited — the row stays in generic lanes tagged
    #                  '🚫 storage-dead (generic land)' instead of vanishing.
    verdict_basis: str | None = None
    storage_dead: bool = False
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
# UTC hour the digest is allowed to send (12:00 UTC = 7am EST / 8am EDT).
# The cron service ticks every 10 min all day for the watchdog; this gate
# keeps the digest to the intended morning window. It lives HERE in Python
# rather than as a shell `[ "$(date -u +%H)" = "12" ]` test in the cron
# start command — that shell form silently evaluated false on Railway
# (the $(date) substitution didn't behave at runtime), so the digest
# never fired and went 4 days dark (May 23–27). Python reads the UTC hour
# reliably and is unit-testable.
#
# Configurable via the DIGEST_SEND_HOUR_UTC env var (default 12). Setting
# it to the current UTC hour on the cron service makes the next 10-min
# tick send immediately — an ops lever to fire an off-cycle digest with
# no code change. The 23h cooldown still applies, so flipping it on (and
# back) sends at most once per 23h. Invalid values fall back to 12.
try:
    _DIGEST_SEND_HOUR_UTC = int(os.getenv("DIGEST_SEND_HOUR_UTC", "12"))
    if not 0 <= _DIGEST_SEND_HOUR_UTC <= 23:
        _DIGEST_SEND_HOUR_UTC = 12
except (TypeError, ValueError):
    _DIGEST_SEND_HOUR_UTC = 12
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
    db: AsyncSession,
    f: BuyboxFilter,
    *,
    include_notified: bool = False,
    limit: int | None = None,
) -> list[DigestParcel]:
    """Select the top matched parcels for a filter.

    Defaults reproduce the digest behavior: only un-notified parcels (so the
    same parcel is never re-emailed) up to ``f.daily_email_top_n``.

    The dashboard push-sync passes ``include_notified=True`` (it wants ALL
    current eligible deals, re-synced idempotently, not just today's new ones)
    and its own ``limit``. Both callers share this one SQL so the board shows
    exactly what the email selects."""
    filter_json = f.filter_json or {}
    require_listed = bool(filter_json.get("requireListed"))
    # Opt-in: drop unpriced listings instead of surfacing them behind the
    # `soft_no_price` flag. Off by default — Worth a Look still surfaces
    # no-price listings until a filter sets {"requirePriced": true}.
    require_priced = bool(filter_json.get("requirePriced"))
    # Hot Deals v2: optional hard filters. NULL = no filter, pass through.
    min_acres = filter_json.get("minAcres")
    max_acres = filter_json.get("maxAcres")
    max_price_per_acre = filter_json.get("maxPricePerAcre")
    # maxTotalPrice closes the 15ac * $900k/ac = $13.5M sneak-through —
    # both per-acre AND total caps need to fire for a deal to qualify.
    max_total_price = filter_json.get("maxTotalPrice")
    # Storage Needles dedicated-track gate (see
    # scripts/_drafts/_storage_needles_track_design.md). NULL = current
    # behavior (no self_storage gate). "only" restricts to human-reviewed
    # self_storage permitted/conditional parcels so wealth-pocket needles
    # surface on their own ranked track instead of being out-ranked by
    # market-agnostic no-verdict deals. "exclude" gates them OUT (so the
    # general buy-box email doesn't double-list a needle). NULL-safe.
    storage_verdict_mode = filter_json.get("storageVerdictMode")
    # Incremental-only LGC lane: when set, keep ONLY parcels where storage is
    # NOT viable (self_storage/mini_warehouse neither permitted nor conditional).
    # This restricts the LGC digest to the pool the storage digest never
    # surfaces (light-industrial / storage-dead zones), so a both-viable parcel
    # emails once — via the storage lane — never twice. Off for self_storage;
    # the LGC score itself (which ranks the lane) already encodes the LGC
    # verdict, so the digest body stays self_storage-simple here.
    exclude_storage_viable = bool(filter_json.get("excludeStorageViable"))

    # Pre-narrow into a MATERIALIZED `eligible` CTE BEFORE the three
    # LATERAL joins (listing / zone-matrix / dashboard-job). The driving
    # table depends on require_listed:
    #
    #   require_listed=true (Hot Deals): `score >= :min_score` matches
    #     ~354k parcels for the filter — score is barely selective. The
    #     selective predicate is "has a current matched listing"
    #     (~600 rows total), so DRIVE from forsale_listings and join INTO
    #     pbs/parcels. DISTINCT ON (p.id) collapses parcels with multiple
    #     current listings (the outer `lst` LATERAL re-picks the
    #     most-recent one, so which listing wins here is irrelevant).
    #     ~0.9 s vs ~69 s for the old pbs-driven LATERAL-over-all plan
    #     (verified on prod, identical row set).
    #
    #   require_listed=false (e.g. Default Box): no listing requirement to
    #     drive from, so scan pbs via ix_pbs_filter_unnotified
    #     (buybox_filter_id, score DESC) WHERE notified_at IS NULL.
    #
    # AS MATERIALIZED is load-bearing in both: without it Postgres inlines
    # the CTE and re-runs the LATERAL subqueries per-row across the whole
    # set (the pre-fix plan). Materializing keeps the LATERALs below
    # against just the narrowed result.
    #
    # The `zum` LATERAL feeds the conditional-zoning / low-confidence soft
    # flags; it picks the most-specific matrix row (municipality-scoped
    # wins over NULL-default) mirroring buybox_scoring.py.
    _eligible_cols = """
                p.id              AS parcel_id,
                p.apn             AS apn,
                p.address         AS address,
                p.owner_name      AS owner_name,
                p.acres           AS acres,
                ST_Y(ST_Centroid(COALESCE(p.centroid, ST_Centroid(p.geom)))) AS lat,
                ST_X(ST_Centroid(COALESCE(p.centroid, ST_Centroid(p.geom)))) AS lng,
                p.has_structure   AS has_structure,
                p.improvement_value AS improvement_value,
                p.in_flood_zone   AS in_flood_zone,
                p.in_wetland      AS in_wetland,
                p.zoning_code     AS zoning_code,
                p.city            AS city,
                p.jurisdiction_id AS jurisdiction_id,
                pbs.score         AS score,
                pbs.tier          AS tier,
                pbs.factors       AS factors
    """
    # Parcel/score-only predicates shared by both driving shapes. NULL
    # acres bindings pass through. The NOT EXISTS is the alert-then-digest
    # dedupe: skip parcels already emailed as a real-time listing alert in
    # the last 14 days (58 Dunkard Church / 199 Grandview both hit this
    # dupe in the May 13-20 reviewer audit).
    # The notified_at gate and the 14-day alert-dedupe are the digest's
    # "don't re-email the same parcel" logic. The dashboard push wants the
    # complete current set (re-synced idempotently), so include_notified drops
    # both — leaving only the score/acres eligibility predicates.
    _notified_gate = "" if include_notified else """
              AND pbs.notified_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM notified_listings nl
                 WHERE nl.filter_id = :fid
                   AND nl.parcel_id = p.id
                   AND nl.notified_at > NOW() - INTERVAL '14 days'
              )"""
    _eligible_predicates = f"""
              AND pbs.score >= :min_score
              AND (CAST(:min_acres AS DOUBLE PRECISION) IS NULL
                   OR p.acres IS NULL
                   OR p.acres >= CAST(:min_acres AS DOUBLE PRECISION))
              AND (CAST(:max_acres AS DOUBLE PRECISION) IS NULL
                   OR p.acres IS NULL
                   OR p.acres <= CAST(:max_acres AS DOUBLE PRECISION))
              {_notified_gate}
    """
    if require_listed:
        # Listings-driven: forsale_listings (current, conf>=0.85) is the
        # selective set. INNER joins to parcels + pbs; DISTINCT ON collapses
        # multi-listing parcels back to one row each.
        eligible_cte = f"""
        WITH eligible AS MATERIALIZED (
            SELECT DISTINCT ON (p.id)
            {_eligible_cols}
            FROM forsale_listings fl
            JOIN parcels p ON p.id = fl.matched_parcel_id
            JOIN parcel_buybox_scores pbs
                 ON pbs.parcel_id = p.id
                AND pbs.buybox_filter_id = :fid
            WHERE fl.is_current = true
              AND fl.match_confidence >= 0.85
            {_eligible_predicates}
            ORDER BY p.id
        )
        """
    else:
        # pbs-driven: no listing requirement to narrow on.
        eligible_cte = f"""
        WITH eligible AS MATERIALIZED (
            SELECT
            {_eligible_cols}
            FROM parcel_buybox_scores pbs
            JOIN parcels p ON p.id = pbs.parcel_id
            WHERE pbs.buybox_filter_id = :fid
            {_eligible_predicates}
        )
        """
    from app.services.verdict_gate import lead_eligible_sql, verdict_basis_sql

    sql = text(
        eligible_cte
        + f"""
        SELECT
            ({verdict_basis_sql('zum')}) AS verdict_basis,
            ({lead_eligible_sql('zum')}) AS lead_eligible,
            (({lead_eligible_sql('zum')})
             AND zum.self_storage::text = 'prohibited') AS storage_dead,
            e.parcel_id     AS parcel_id,
            e.apn           AS apn,
            e.address       AS address,
            e.owner_name    AS owner_name,
            e.acres         AS acres,
            e.lat           AS lat,
            e.lng           AS lng,
            e.score         AS score,
            e.tier          AS tier,
            e.factors       AS factors,
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
            (e.has_structure = TRUE OR COALESCE(e.improvement_value, 0) > 50000)
                AS soft_has_building,
            (lst.sale_price IS NULL)                       AS soft_no_price,
            (zum.self_storage::text = 'conditional')       AS soft_conditional,
            (zum.confidence IS NOT NULL AND zum.confidence < 0.70)
                AS soft_low_confidence,
            (e.in_flood_zone = TRUE)                       AS soft_flood,
            (e.in_wetland    = TRUE)                       AS soft_wetland,
            -- NULL acres = lot size unverified (mostly condo units whose
            -- ingest carried no parcel geometry). They pass the acres
            -- hard filters via the `OR p.acres IS NULL` branches, so we
            -- surface them — but flagged, which demotes them to
            -- "Worth a Look" rather than polluting Actionable.
            (e.acres IS NULL)                              AS soft_acres_unverified
        FROM eligible e
        JOIN jurisdictions j ON j.id = e.jurisdiction_id
        LEFT JOIN LATERAL (
            SELECT source, sale_price, days_on_market,
                   listing_broker_company, listing_broker_contact,
                   listing_broker_phone, listing_broker_email
              FROM forsale_listings
             WHERE matched_parcel_id = e.parcel_id
               AND is_current = true
               AND match_confidence >= 0.85
             ORDER BY last_seen_at DESC
             LIMIT 1
        ) lst ON true
        LEFT JOIN LATERAL (
            -- self_storage + siblings: the sibling columns feed the LGC
            -- verdict expression (verdict_sql). Extra columns are ignored by
            -- the self_storage expression, so the storage digest is unchanged.
            SELECT self_storage, mini_warehouse,
                   confidence, human_reviewed, classification_source
              FROM zone_use_matrix
             WHERE jurisdiction_id = e.jurisdiction_id
               AND zone_code      = e.zoning_code
               AND (municipality IS NULL OR municipality = e.city)
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
             WHERE jurisdiction_id = e.jurisdiction_id
               AND status = 'ready'
             ORDER BY finished_at DESC NULLS LAST, created_at DESC
             LIMIT 1
        ) latest_job ON true
        -- Listing-dependent filters stay here: they need lst, which only
        -- exists after the LATERAL join above.
        WHERE (NOT :require_listed OR lst.source IS NOT NULL)
          -- Opt-in: drop unpriced listings entirely (sale_price NULL or 0).
          -- Off by default; gate is a no-op until a filter sets
          -- requirePriced=true in its filter_json. (NOTE: this literal is an
          -- f-string — keep curly braces out of comments here.)
          AND (NOT :require_priced
               OR (lst.sale_price IS NOT NULL AND lst.sale_price > 0))
          -- Price-per-acre cap fires only when both price and acres
          -- are populated. Unpriced listings pass through and surface
          -- as the "no asking price" soft flag instead.
          AND (CAST(:max_price_per_acre AS DOUBLE PRECISION) IS NULL
               OR lst.sale_price IS NULL
               OR e.acres IS NULL
               OR e.acres = 0
               OR (lst.sale_price / e.acres)
                   <= CAST(:max_price_per_acre AS DOUBLE PRECISION))
          -- Total-price ceiling. Unpriced listings pass through and
          -- surface as the "no asking price" soft flag instead.
          AND (CAST(:max_total_price AS DOUBLE PRECISION) IS NULL
               OR lst.sale_price IS NULL
               OR lst.sale_price <= CAST(:max_total_price AS DOUBLE PRECISION))
          -- Storage Needles gate. NULL -> no gate (current behavior).
          -- 'only' -> keep ONLY human-reviewed self_storage needles.
          -- 'exclude' -> drop needles (NULL-safe: no-verdict + non-needle
          -- rows pass, so the general buy-box still surfaces them).
          -- CAST to text: asyncpg cannot infer the bind type from
          -- `$n IS NULL` + untyped-literal comparisons alone and raises
          -- AmbiguousParameterError at prepare time (same reason the
          -- price caps above CAST to DOUBLE PRECISION). Without this the
          -- whole digest crashes for every filter, not just SN.
          AND (
                CAST(:storage_verdict_mode AS TEXT) IS NULL
             OR (CAST(:storage_verdict_mode AS TEXT) = 'only'
                 AND zum.self_storage::text IN ('permitted', 'conditional')
                 AND zum.human_reviewed = TRUE)
             OR (CAST(:storage_verdict_mode AS TEXT) = 'exclude'
                 AND NOT COALESCE(
                       zum.self_storage::text IN ('permitted', 'conditional')
                       AND zum.human_reviewed, FALSE))
          )
          -- Incremental-only LGC lane. When excludeStorageViable is set, drop
          -- any parcel where storage itself is viable (permitted/conditional on
          -- self_storage or mini_warehouse) so a both-viable parcel emails only
          -- via the storage digest. NULL-safe; a no-op for self_storage filters.
          AND (
                NOT :exclude_storage_viable
             OR NOT COALESCE(
                   zum.self_storage::text  IN ('permitted', 'conditional')
                OR zum.mini_warehouse::text IN ('permitted', 'conditional'),
                   FALSE)
          )
        ORDER BY e.score DESC, e.parcel_id
        LIMIT :lim
        """
    )
    rows = await db.execute(
        sql,
        {
            "fid": f.id,
            "min_score": _MIN_SCORE_LISTED if require_listed else _MIN_SCORE,
            "lim": limit or f.daily_email_top_n,
            "require_listed": require_listed,
            "require_priced": require_priced,
            "min_acres": min_acres,
            "max_acres": max_acres,
            "max_price_per_acre": max_price_per_acre,
            "max_total_price": max_total_price,
            "storage_verdict_mode": storage_verdict_mode,
            "exclude_storage_viable": exclude_storage_viable,
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
                lat=float(m["lat"]) if m["lat"] is not None else None,
                lng=float(m["lng"]) if m["lng"] is not None else None,
                soft_flags=_soft_flags_from_row(m),
                verdict_basis=m["verdict_basis"],
                storage_dead=bool(m["storage_dead"]),
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
    ("soft_acres_unverified", "📐", "acres unverified"),
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
    # the drawer already uses. lat/lng (centroid) let the map fly
    # straight to the site at close zoom instead of fitting the county
    # first — faster load, lands on the parcel.
    url = f"{base}/dashboard/{segment}?parcel_id={p.parcel_id}"
    if p.lat is not None and p.lng is not None:
        url += f"&lat={p.lat:.6f}&lng={p.lng:.6f}"
    return url


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
    # Score is never shown without its verdict basis (catch #49): a 96 on a
    # heuristic guess must not read like a verified 96.
    lines.append(f"  Score: {p.score} ({p.tier}) · basis: {p.verdict_basis or 'unknown'}"
                 + (" · 🚫 storage-dead (generic land)" if p.storage_dead else ""))
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
        f"    · <span style=\"color:{'#166534' if p.verdict_basis == 'human-verified' else '#92400e'};"
        f"font-size:12px\">{html_lib.escape(p.verdict_basis or 'unknown')}</span>"
        f"{'&nbsp;· <span style=\"color:#b91c1c;font-size:12px\">🚫 storage-dead (generic land)</span>' if p.storage_dead else ''}"
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

    # holdWorthALook (filter_json, Nache directive 2026-07-15): email ONLY the
    # Actionable tier; Worth-a-Look parcels are held for in-app review. Subset
    # BEFORE rendering AND before the notified_at stamp below — a held parcel
    # must NOT be marked notified, or it would never re-surface once its soft
    # flags clear (or the hold is lifted).
    if bool((f.filter_json or {}).get("holdWorthALook")):
        actionable, worth_a_look = _split_by_tier(parcels)
        if worth_a_look:
            logger.info(
                "digest filter=%s: holdWorthALook — holding %d worth-a-look parcel(s) in-app",
                f.name, len(worth_a_look),
            )
        parcels = actionable
        if not parcels:
            logger.info(
                "digest filter=%s: holdWorthALook — no actionable parcels, not sending",
                f.name,
            )
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

    # Mirror the same deals onto the portfolio dashboard's Deal Pipeline board
    # (separate Supabase). Best-effort: a push failure is logged but never sinks
    # the digest's exit status (email is the priority; the board is secondary).
    # No-op when PORTFOLIO_DASHBOARD_DATABASE_URL is unset. Lazy import breaks the
    # dashboard_push ↔ daily_email import cycle.
    dashboard_push_result = None
    try:
        from app.services.dashboard_push import run_push

        dashboard_push_result = await run_push(force=True)
    except Exception:
        logger.exception("dashboard push failed; digest unaffected")

    return {
        "filters": filters_processed,
        "parcels": parcels_emailed,
        "eligible_total": eligible_total,
        "errors": errors,
        "dashboard_push": dashboard_push_result,
    }


# ─── Dramatiq actor (for manual / ad-hoc triggers) ───────────────────────

@dramatiq.actor(max_retries=0, time_limit=10 * 60 * 1000)
def send_daily_digest_actor() -> None:
    asyncio.run(run_once())


# ─── CLI entry point ─────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Send the daily buy-box digest.")
    ap.add_argument(
        "--force",
        action="store_true",
        help="bypass the UTC send-hour gate AND the 23h cooldown "
        "(manual smoke test). Does not stamp last_email_sent_at.",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Send-hour gate. The combined watchdog+digest cron ticks every 10 min,
    # so without this every tick would send. We only send during the
    # 12:00 UTC hour. Checked here (not in the cron shell command) because
    # the prior shell `$(date -u +%H)` gate never fired on Railway.
    hour = datetime.now(timezone.utc).hour
    if not args.force and hour != _DIGEST_SEND_HOUR_UTC:
        print(
            f"digest skip: UTC hour {hour:02d} != send hour "
            f"{_DIGEST_SEND_HOUR_UTC:02d} (use --force to override)"
        )
        sys.exit(0)

    result = asyncio.run(run_once(force=args.force))
    print(f"digest done: {result}")
    # Non-zero exit when any filter errored so Railway's cron logs
    # surface the failure instead of silently marking the run green.
    sys.exit(1 if result.get("errors") else 0)


if __name__ == "__main__":
    _cli()
