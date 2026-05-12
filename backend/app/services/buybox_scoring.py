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


@dataclass
class ScoredParcel:
    parcel_id: int
    score: int
    tier: str
    factors: list[dict] = field(default_factory=list)


def score_for_parcel(p: ParcelInputs, filter_json: dict | None = None) -> ScoredParcel:
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

    # Storage permission
    sp = (p.storage_permission or "").lower()
    if sp == UsePermission.permitted.value:
        factors.append({"label": "Storage", "delta": 30, "reason": "Permitted by zoning"})
    elif sp == UsePermission.conditional.value:
        factors.append({"label": "Storage", "delta": 15, "reason": "Conditional use"})
    elif sp == UsePermission.prohibited.value:
        factors.append({"label": "Storage", "delta": -25, "reason": "Prohibited by zoning"})
    elif sp == UsePermission.unclear.value:
        factors.append({"label": "Storage", "delta": 0, "reason": "Ordinance unclear — verify"})
    else:
        factors.append({"label": "Storage", "delta": 0, "reason": "No matrix entry yet"})

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
        boost = int(filter_json.get("listing_score_boost") or 0)
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
    return ScoredParcel(p.parcel_id, score, tier_for(score), factors)


# ─── Bulk scoring ────────────────────────────────────────────────────────

def _raw_dsn() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


_SELECT_PARCELS_SQL = """
SELECT
    p.id                AS parcel_id,
    zum.self_storage::text AS storage_permission,
    p.acres,
    p.aadt,
    p.in_flood_zone,
    p.in_wetland,
    p.has_structure,
    prm.homes_over_1m,
    prm.homes_over_2m,
    prm.homes_over_5m,
    lst.source         AS listing_source,
    lst.sale_price     AS listing_sale_price,
    lst.days_on_market AS listing_dom
FROM parcels p
LEFT JOIN zone_use_matrix zum
    ON zum.jurisdiction_id = p.jurisdiction_id
   AND zum.zone_code      = p.zoning_code
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
INSERT INTO parcel_buybox_scores (parcel_id, buybox_filter_id, score, tier, factors)
VALUES ($1::bigint, $2::uuid, $3::int, $4::text, $5::jsonb)
ON CONFLICT ON CONSTRAINT pk_parcel_buybox_scores DO UPDATE
SET score       = EXCLUDED.score,
    tier        = EXCLUDED.tier,
    factors     = EXCLUDED.factors,
    computed_at = NOW()
"""


# Stable IDs of the seed rows created in migration 0015. Auto-scoring
# uses these to find the default BuyboxFilter without needing an auth /
# session context.
DEFAULT_ORG_ID            = uuid.UUID("00000000-0000-0000-0000-000000000001")
SELF_STORAGE_USE_CASE_ID  = uuid.UUID("00000000-0000-0000-0000-000000000002")


async def auto_score_jurisdiction(jurisdiction_id: uuid.UUID) -> int:
    """Score every parcel in a freshly-ingested jurisdiction against the
    Default Organization's `self_storage` default BuyboxFilter.

    Used by the pipeline as the last step after parcels + zoning + matrix
    + overlays are populated, so the dashboard's Score column lights up
    immediately without a manual bootstrap run.

    Safely returns 0 when the default filter doesn't exist (e.g. before
    migration 0015 lands or in a test DB without the seeds). Caller
    should already wrap in try/except so a scoring failure can't fail
    the larger pipeline.
    """
    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.execute("SET statement_timeout = 0")
        row = await conn.fetchrow(
            """
            SELECT id, filter_json
            FROM buybox_filters
            WHERE organization_id = $1::uuid
              AND use_case_id     = $2::uuid
              AND is_default      = true
            LIMIT 1
            """,
            DEFAULT_ORG_ID, SELF_STORAGE_USE_CASE_ID,
        )
    finally:
        await conn.close()

    if row is None:
        logger.warning(
            "auto_score_jurisdiction: no default BuyboxFilter for "
            "(default org × self_storage). Skipping."
        )
        return 0

    filter_json_raw = row["filter_json"]
    if isinstance(filter_json_raw, str):
        filter_json = json.loads(filter_json_raw)
    else:
        filter_json = filter_json_raw or {}

    return await score_jurisdiction(jurisdiction_id, row["id"], filter_json)


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
        await conn.execute("SET statement_timeout = 0")
        rows = await conn.fetch(_SELECT_PARCELS_SQL, jurisdiction_id, drive_time)
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
            )
            s = score_for_parcel(inputs, filter_json)
            scored.append((
                s.parcel_id, buybox_filter_id, s.score, s.tier,
                json.dumps(s.factors),
            ))

        # Batched UPSERT — chunk_size keeps the wire payload small
        for i in range(0, len(scored), chunk_size):
            chunk = scored[i:i + chunk_size]
            await conn.executemany(_UPSERT_SQL, chunk)
            logger.info("Upserted %d/%d scores", min(i + chunk_size, len(scored)), len(scored))

        return len(scored)
    finally:
        await conn.close()
