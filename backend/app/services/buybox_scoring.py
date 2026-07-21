"""
Server-side composite scoring for parcels under a given BuyboxFilter.

Python port of the placeholder formula in `frontend/lib/compositeScore.ts`,
extended to honor the filter's slider thresholds (acreage min/max,
storage permission requirements, AADT minimum, etc.). The output is one
row per (parcel, buybox_filter_id) in `parcel_buybox_scores`.

The scoring formula is intentionally tunable; the canonical doc lives
above each branch in `score_for_parcel()`. Eventually this should
move behind a config-driven weight table so business users can rebalance
without a code deploy, but for now in-code is fine.

Usage:
    from app.services.buybox_scoring import score_jurisdiction
    n = await score_jurisdiction(jurisdiction_id, buybox_filter_id, db)
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from app.config import settings
from app.models.zone_use_matrix import UsePermission
from app.services.use_verdicts import LGC_SLUG, verdict_expr

logger = logging.getLogger(__name__)


# ─── Tier thresholds ─────────────────────────────────────────────────────

TIER_THRESHOLDS: list[tuple[int, str]] = [
    (80, "excellent"),
    (60, "strong"),
    (40, "decent"),
    (20, "weak"),
    (0,  "avoid"),
]


def tier_for(score: int) -> str:
    for cutoff, name in TIER_THRESHOLDS:
        if score >= cutoff:
            return name
    return "avoid"


# ─── Per-parcel scoring ──────────────────────────────────────────────────

@dataclass
class ParcelInputs:
    """Minimal struct the scorer reads off a parcel + matrix join."""
    parcel_id: int
    storage_permission: str | None      # 'permitted'/'conditional'/'unclear'/'prohibited'/None
    acres: float | None
    aadt: int | None
    in_flood_zone: bool
    in_wetland: bool
    has_structure: bool | None
    # Wealth-density counts for the FILTER's drive-time ring, joined from
    # parcel_ring_metrics. None when the ring hasn't been measured yet
    # (the frontend value-density endpoint populates these lazily).
    homes_over_1m: int | None = None
    homes_over_2m: int | None = None
    homes_over_5m: int | None = None
    # Listing details — populated when the parcel has a current matched
    # listing (from any source) with match_confidence >= 0.85. Source-
    # agnostic by design: LoopNet vs CoStar doesn't change the boost.
    listing_source: str | None = None
    listing_sale_price: float | None = None
    listing_dom: int | None = None
    # Verdict provenance (catch #49 enforcement): which authority produced
    # storage_permission. verdict_matched=False = the LATERAL found no matrix
    # row at all ('ungrounded muni').
    classification_source: str | None = None
    confidence: float | None = None
    human_reviewed: bool = False
    verdict_matched: bool = False
    # True when the parcel falls within a mapped Self-Service Storage overlay
    # district (parcels.overlay_tags contains 'SS'). The overlay affirmatively
    # grants self-storage by special permit on these parcels even though the
    # base district prohibits it (e.g. Billerica § 11.6), so it upgrades the
    # effective storage verdict to 'conditional'. Never downgrades.
    overlay_ss: bool = False


@dataclass
class ScoredParcel:
    parcel_id: int
    score: int
    tier: str
    factors: list[dict] = field(default_factory=list)
    # Lead-eligibility gate outputs (verdict_gate.py) — persisted on the score
    # row so every read path serves score + basis together, never score alone.
    lead_eligible: bool = False
    gate_reason: str | None = None
    verdict_basis: str = "ungrounded muni"


def score_for_parcel(
    p: ParcelInputs, filter_json: dict | None = None, asset_label: str = "Storage"
) -> ScoredParcel:
    """Compute a 0-100 composite score for a single parcel.

    `filter_json` is the BuyboxFilter.filter_json blob — the same shape
    the frontend uses (DEFAULT_FILTER from buy-box-filter.ts):
      {
        minPopulation, minMedianHHI, minMedianHomeValue, minHnwHouseholds,
        minAADT, driveTimeMinutes, matchLogic, ...
      }
    For now we only use minAADT (since population data isn't on the parcel
    row yet — that lives in parcel_ring_metrics, joined separately later).
    """
    factors: list[dict] = [{"label": "Base", "delta": 50, "reason": "Baseline"}]

    # SS-overlay upgrade: a parcel inside a mapped Self-Service Storage overlay
    # has an affirmative special-permit path to self-storage regardless of the
    # base-district verdict (§ 11.6 pattern). Lift a prohibited/unclear/absent
    # base verdict to 'conditional'; never downgrade a permitted/conditional one.
    effective_permission = p.storage_permission
    overlay_applied = False
    if p.overlay_ss and (p.storage_permission or "").lower() in (
        "", UsePermission.prohibited.value, UsePermission.unclear.value,
    ):
        effective_permission = UsePermission.conditional.value
        overlay_applied = True

    # Storage permission
    sp = (effective_permission or "").lower()
    if sp == UsePermission.permitted.value:
        factors.append({"label": asset_label, "delta": 30, "reason": "Permitted by zoning"})
    elif sp == UsePermission.conditional.value:
        factors.append({"label": asset_label, "delta": 15, "reason": "Conditional use"})
    elif sp == UsePermission.prohibited.value:
        factors.append({"label": asset_label, "delta": -25, "reason": "Prohibited by zoning"})
    elif sp == UsePermission.unclear.value:
        factors.append({"label": asset_label, "delta": 0, "reason": "Ordinance unclear — verify"})
    else:
        factors.append({"label": asset_label, "delta": 0, "reason": "No matrix entry yet"})

    if overlay_applied:
        factors.append({
            "label": "SS overlay",
            "delta": 0,
            "reason": "Self-Service Storage overlay — special-permit path",
        })

    # Acreage bonus — bigger lots score higher (max +20 at 30 acres)
    if p.acres is not None and p.acres > 0:
        bonus = round(min(p.acres / 30, 1.0) * 20, 1)
        factors.append({"label": "Acres", "delta": bonus, "reason": f"{p.acres:.1f} ac"})

    # AADT bonus — visibility (5K = 0 pts, 50K = full +15)
    if p.aadt is not None and p.aadt > 0:
        bonus = round(max(min((p.aadt - 5000) / 45000, 1.0), 0.0) * 15, 1)
        if bonus > 0:
            factors.append({
                "label": "Traffic",
                "delta": bonus,
                "reason": f"{p.aadt / 1000:.0f}K AADT",
            })

    # Flood / wetland penalties
    if p.in_flood_zone:
        factors.append({"label": "Flood zone", "delta": -25, "reason": "FEMA SFHA"})
    if p.in_wetland:
        factors.append({"label": "Wetland",    "delta": -15, "reason": "USFWS NWI"})

    # Vacant land bonus
    if p.has_structure is False:
        factors.append({"label": "Vacant", "delta": 5, "reason": "No existing structure"})

    # Filter-driven AADT threshold penalty (if user requires high traffic
    # and parcel falls below, big penalty so they sort to bottom)
    if filter_json and filter_json.get("minAADT") and (p.aadt or 0) < filter_json["minAADT"]:
        delta = -20
        factors.append({
            "label": "AADT threshold",
            "delta": delta,
            "reason": f"Below filter min ({filter_json['minAADT']:,})",
        })

    # Wealth-density contributions. Three signals, decreasing weight as
    # the threshold gets rarer ($1M > $2M > $5M). Each fires when the
    # user has enabled the corresponding slider AND the parcel's ring
    # has been measured (homes_over_NM is non-null). Behaviour for each:
    #   - When the ring meets the filter min, add a positive bonus
    #     proportional to how far above the min we are (capped).
    #   - When the ring is below the filter min, add a fixed penalty so
    #     these parcels sort to the bottom (same shape as minAADT).
    # The frontend already gates the slider with wealth_density_available
    # so we don't see these filter keys on UT/UGRC cities at all.
    _wealth_specs = (
        ("minHomesOver1M", p.homes_over_1m, "Homes ≥$1M", 8.0),  # max +8 contribution
        ("minHomesOver2M", p.homes_over_2m, "Homes ≥$2M", 6.0),  # max +6
        ("minHomesOver5M", p.homes_over_5m, "Homes ≥$5M", 4.0),  # max +4
    )
    if filter_json:
        for key, actual, label, max_bonus in _wealth_specs:
            min_v = filter_json.get(key)
            if min_v is None or min_v <= 0:
                continue
            if actual is None:
                # Ring not measured yet; transparent factor with no delta
                # so the dashboard knows the signal is pending.
                factors.append({
                    "label": label,
                    "delta": 0,
                    "reason": "Ring not yet measured",
                })
                continue
            if actual >= min_v:
                # Bonus: scaled by how far above min we are. min meet = 50%
                # of max bonus; 2× min = full bonus.
                ratio = min(actual / max(min_v, 1), 2.0)
                delta = round(max_bonus * (0.5 + (ratio - 1) * 0.5), 1)
                factors.append({
                    "label": label,
                    "delta": delta,
                    "reason": f"{actual:,} in ring (min {min_v:,})",
                })
            else:
                delta = -10
                factors.append({
                    "label": label,
                    "delta": delta,
                    "reason": f"Only {actual:,} in ring (min {min_v:,})",
                })

    # Listing boost — fires when this parcel has any current matched
    # listing (source-agnostic). Filter knob `listing_score_boost`
    # (default 0; the digest worker / admin UI sets it to ~15 once the
    # listings pipeline is producing matches). A parcel that's actively
    # listed AND meets the buy box can be under contract within days,
    # so it deserves to sort to the top of the digest.
    if filter_json:
        boost = int(filter_json.get("listingScoreBoost") or 0)
        if boost > 0 and p.listing_source:
            reason_parts = [f"Listed on {p.listing_source}"]
            if p.listing_dom is not None:
                reason_parts.append(f"DOM {p.listing_dom}")
            if p.listing_sale_price is not None:
                reason_parts.append(f"${int(p.listing_sale_price):,}")
            factors.append({
                "label": "Listed",
                "delta": boost,
                "reason": " · ".join(reason_parts),
            })

    raw = sum(f["delta"] for f in factors)
    score = max(0, min(100, round(raw)))

    # Lead-eligibility gate (catch #49): a score computed on a heuristic
    # verdict is DEMOTED, never deleted — the row persists with the reason,
    # and the basis tag makes the provenance visible wherever the score shows.
    from app.services.verdict_gate import gate_verdict, verdict_basis

    eligible, reason = gate_verdict(
        self_storage=effective_permission,
        classification_source=p.classification_source,
        confidence=p.confidence,
        human_reviewed=p.human_reviewed,
    )
    basis = verdict_basis(
        p.classification_source, p.human_reviewed, matched=p.verdict_matched
    )
    return ScoredParcel(
        p.parcel_id, score, tier_for(score), factors,
        lead_eligible=eligible, gate_reason=reason, verdict_basis=basis,
    )


# ─── Bulk scoring ────────────────────────────────────────────────────────

def _raw_dsn() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def _has_ss_overlay(overlay_tags: object) -> bool:
    """True when parcels.overlay_tags contains the 'SS' Self-Service Storage
    overlay code. asyncpg may hand back JSONB as a parsed list or a raw str
    depending on codec registration, so tolerate both (and None)."""
    if not overlay_tags:
        return False
    if isinstance(overlay_tags, str):
        try:
            overlay_tags = json.loads(overlay_tags)
        except (ValueError, TypeError):
            return "SS" in overlay_tags
    try:
        return "SS" in overlay_tags
    except TypeError:
        return False


# The `storage_permission` expression is use-case-dependent: self_storage reads
# its column directly (byte-identical to the historical query); luxury_garage_
# condo derives from the sibling columns (see use_verdicts). The LATERAL always
# selects all three sibling columns — the extra two are only read by the LGC
# expression, so the self_storage output is unchanged. `{verdict_sql}` is filled
# ONLY from the code-owned use_verdicts registry, never from user input.
def _select_parcels_sql(verdict_sql: str) -> str:
    return f"""
SELECT
    p.id                AS parcel_id,
    {verdict_sql} AS storage_permission,
    zum.classification_source AS classification_source,
    zum.confidence      AS verdict_confidence,
    zum.human_reviewed  AS human_reviewed,
    p.acres,
    p.aadt,
    p.in_flood_zone,
    p.in_wetland,
    p.has_structure,
    p.overlay_tags     AS overlay_tags,
    prm.homes_over_1m,
    prm.homes_over_2m,
    prm.homes_over_5m,
    lst.source         AS listing_source,
    lst.sale_price     AS listing_sale_price,
    lst.days_on_market AS listing_dom
FROM parcels p
LEFT JOIN LATERAL (
    -- Pick the most specific zone_use_matrix row for this parcel:
    -- a row whose municipality matches parcels.city wins over a
    -- NULL-municipality county-default row. Implemented as a LATERAL
    -- LIMIT 1 ordered by (municipality IS NULL ASC) so non-null rows
    -- sort first; LIMIT 1 collapses the result to whichever wins.
    SELECT self_storage, mini_warehouse, light_industrial,
           classification_source::text AS classification_source,
           confidence, human_reviewed
      FROM zone_use_matrix
     WHERE jurisdiction_id = p.jurisdiction_id
       AND zone_code      = p.zoning_code
       AND (municipality IS NULL OR municipality = p.city)
       AND deleted_at IS NULL
     ORDER BY (municipality IS NULL) ASC
     LIMIT 1
) zum ON true
LEFT JOIN parcel_ring_metrics prm
    ON prm.parcel_id = p.id
   AND prm.drive_time_minutes = $2::int
LEFT JOIN LATERAL (
    SELECT source, sale_price, days_on_market
      FROM forsale_listings
     WHERE matched_parcel_id = p.id
       AND is_current = true
       AND match_confidence >= 0.85
     ORDER BY last_seen_at DESC
     LIMIT 1
) lst ON true
WHERE p.jurisdiction_id = $1::uuid
"""


_UPSERT_SQL = """
INSERT INTO parcel_buybox_scores (parcel_id, buybox_filter_id, score, tier, factors,
                                  lead_eligible, gate_reason, verdict_basis)
VALUES ($1::bigint, $2::uuid, $3::int, $4::text, $5::jsonb, $6::boolean, $7::text, $8::text)
ON CONFLICT ON CONSTRAINT pk_parcel_buybox_scores DO UPDATE
SET score         = EXCLUDED.score,
    tier          = EXCLUDED.tier,
    factors       = EXCLUDED.factors,
    lead_eligible = EXCLUDED.lead_eligible,
    gate_reason   = EXCLUDED.gate_reason,
    verdict_basis = EXCLUDED.verdict_basis,
    computed_at   = NOW()
"""


# Stable IDs of the seed rows created in migration 0015. Auto-scoring
# uses these to find the default BuyboxFilter without needing an auth /
# session context.
DEFAULT_ORG_ID            = uuid.UUID("00000000-0000-0000-0000-000000000001")
SELF_STORAGE_USE_CASE_ID  = uuid.UUID("00000000-0000-0000-0000-000000000002")
LGC_USE_CASE_ID           = uuid.UUID("00000000-0000-0000-0000-000000000003")


async def auto_score_jurisdiction(jurisdiction_id: uuid.UUID) -> int:
    """Score every parcel in a freshly-ingested jurisdiction against EACH of the
    Default Organization's default BuyboxFilters — one per use case (self_storage
    and luxury_garage_condo), so the dashboard's Score column lights up for
    whichever asset the operator toggles to, immediately after ingest.

    Each filter scores into its own ``parcel_buybox_scores`` rows (keyed by
    ``(parcel_id, buybox_filter_id)``), so the LGC pass never disturbs the
    self_storage scores.

    Raises ``RuntimeError`` when NO default BuyboxFilter exists at all. Prior
    versions silently returned 0 and a warning, which let real config gaps
    (e.g. nobody marked a filter is_default=true) ride for weeks unnoticed
    across every new jurisdiction ingest. Caller is expected to wrap in
    try/except so a scoring failure can't fail the larger pipeline, but the
    exception is now visible in job state via ``_stage_failed``.
    """
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.execute("SET statement_timeout = 0")
        rows = await conn.fetch(
            """
            SELECT id, filter_json
            FROM buybox_filters
            WHERE organization_id = $1::uuid
              AND is_default      = true
            ORDER BY use_case_id
            """,
            DEFAULT_ORG_ID,
        )
    finally:
        await conn.close()

    if not rows:
        msg = (
            "auto_score_jurisdiction: no default BuyboxFilter for default org "
            f"{DEFAULT_ORG_ID}. Mark a filter is_default=true via "
            "PATCH /api/buybox-filters/{id} or seed one via migration."
        )
        logger.error(msg)
        raise RuntimeError(msg)

    total = 0
    for row in rows:
        filter_json_raw = row["filter_json"]
        if isinstance(filter_json_raw, str):
            filter_json = json.loads(filter_json_raw)
        else:
            filter_json = filter_json_raw or {}
        total += await score_jurisdiction(jurisdiction_id, row["id"], filter_json)
    return total


async def score_jurisdiction(
    jurisdiction_id: uuid.UUID,
    buybox_filter_id: uuid.UUID,
    filter_json: dict | None = None,
    chunk_size: int = 5000,
) -> int:
    """Score every parcel in a jurisdiction under the given buy-box filter.

    Reads parcels + zone_use_matrix joined on (jurisdiction, zone_code),
    runs `score_for_parcel` per row in pure Python, then bulk-upserts the
    results into parcel_buybox_scores via batched INSERT...ON CONFLICT.

    Uses raw asyncpg (no SQLAlchemy session) to bypass the 32K bind-param
    cap, matching the COPY-ingest pattern in ingestion.py.

    Returns the count of parcels scored.
    """
    # The wealth-density signal is read from parcel_ring_metrics for the
    # ring the FILTER is configured on (driveTimeMinutes). Default to 10
    # when the filter doesn't carry one, matching DEFAULT_FILTER.
    drive_time = 10
    if filter_json:
        try:
            drive_time = int(filter_json.get("driveTimeMinutes") or 10)
        except (TypeError, ValueError):
            drive_time = 10

    conn = await asyncpg.connect(_raw_dsn())
    try:
        # Concurrency dedupe: two identical runs for the same (jurisdiction,
        # filter) interleaving their upserts is safe (ON CONFLICT row-locks,
        # identical values) but wastes 2x the work on a large county AND makes
        # the final persisted score nondeterministic if the two runs read
        # zone_use_matrix at different instants (last upsert wins). This matters
        # now that parallel sessions ground different munis in the same county.
        # Session-level advisory lock keyed on the pair; the duplicate caller
        # skips instead of racing. Auto-released on disconnect, so a crashed run
        # never wedges the key.
        got = await conn.fetchval(
            "SELECT pg_try_advisory_lock(hashtextextended($1, 42))",
            f"score:{jurisdiction_id}:{buybox_filter_id}",
        )
        if not got:
            logger.warning(
                "score_jurisdiction skipped — identical run already in flight "
                "(jurisdiction=%s filter=%s)", jurisdiction_id, buybox_filter_id,
            )
            return 0
        await conn.execute("SET statement_timeout = 0")
        # Resolve the filter's use case to pick the verdict expression. Unknown
        # / missing → self_storage, so the rendered SQL and results are
        # byte-for-byte the historical query for every existing filter.
        slug = await conn.fetchval(
            """
            SELECT uc.slug
              FROM buybox_filters bf
              JOIN use_cases uc ON uc.id = bf.use_case_id
             WHERE bf.id = $1::uuid
            """,
            buybox_filter_id,
        )
        asset_label = "Garage" if slug == LGC_SLUG else "Storage"
        select_sql = _select_parcels_sql(verdict_expr(slug))
        rows = await conn.fetch(select_sql, jurisdiction_id, drive_time)
        logger.info(
            "Scoring %d parcels for jurisdiction %s under filter %s (ring=%d min)",
            len(rows), jurisdiction_id, buybox_filter_id, drive_time,
        )

        scored: list[tuple[int, uuid.UUID, int, str, str]] = []
        for r in rows:
            inputs = ParcelInputs(
                parcel_id=r["parcel_id"],
                storage_permission=r["storage_permission"],
                acres=float(r["acres"]) if r["acres"] is not None else None,
                aadt=r["aadt"],
                in_flood_zone=bool(r["in_flood_zone"]),
                in_wetland=bool(r["in_wetland"]),
                has_structure=r["has_structure"],
                homes_over_1m=r["homes_over_1m"],
                homes_over_2m=r["homes_over_2m"],
                homes_over_5m=r["homes_over_5m"],
                listing_source=r["listing_source"],
                listing_sale_price=(
                    float(r["listing_sale_price"])
                    if r["listing_sale_price"] is not None else None
                ),
                listing_dom=r["listing_dom"],
                classification_source=r["classification_source"],
                confidence=(
                    float(r["verdict_confidence"])
                    if r["verdict_confidence"] is not None else None
                ),
                human_reviewed=bool(r["human_reviewed"]),
                # LEFT LATERAL miss => storage_permission AND source both NULL
                verdict_matched=r["storage_permission"] is not None,
                overlay_ss=_has_ss_overlay(r["overlay_tags"]),
            )
            s = score_for_parcel(inputs, filter_json, asset_label=asset_label)
            scored.append((
                s.parcel_id, buybox_filter_id, s.score, s.tier,
                json.dumps(s.factors),
                s.lead_eligible, s.gate_reason, s.verdict_basis,
            ))

        # Batched UPSERT — chunk_size keeps the wire payload small
        for i in range(0, len(scored), chunk_size):
            chunk = scored[i:i + chunk_size]
            await conn.executemany(_UPSERT_SQL, chunk)
            logger.info("Upserted %d/%d scores", min(i + chunk_size, len(scored)), len(scored))

        return len(scored)
    finally:
        await conn.close()
