"""Cascade matcher: ForsaleListing -> Parcel.

Three tiers in order. The first that produces a match writes the
result back to the listing row and returns. Confidence < 0.85 leaves
``matched_parcel_id`` null on purpose — the spec is explicit that
low-confidence matches should NOT auto-apply to scoring.

Tier 1 — Normalized address exact match against parcels in the same
         jurisdiction. Confidence 1.0.
Tier 2 — Strip unit + ZIP+4, retry Tier 1. Confidence 0.95.
Tier 3 — Geocode via Census, spatial ST_DWithin(centroid, lon/lat, 50m).
         1 hit → 0.85, multiple → 0.65 (flag), 0 → unmatched.

`match_pending_listings` is the batch entry point invoked from the
upload background task. It only runs over rows where
``matched_parcel_id IS NULL`` so re-running is idempotent.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forsale_listing import ForsaleListing
from app.services.address_normalizer import normalize, strip_unit
from app.services.geocode_census import geocode_address

logger = logging.getLogger(__name__)

_TIER_1 = "exact_address"
_TIER_2 = "stripped_address"
_TIER_3_ONE = "geocode_spatial_1"
_TIER_3_MANY = "geocode_spatial_multi"


@dataclass
class MatchResult:
    matched_parcel_id: int | None
    match_confidence: float | None
    match_method: str | None
    geocoded_lat: float | None
    geocoded_lon: float | None


async def _tier1_exact(
    listing: ForsaleListing, db: AsyncSession
) -> MatchResult | None:
    """Normalized-address exact match. Confidence 1.0."""
    norm = normalize(listing.address)
    if not norm:
        return None
    row = await db.execute(
        text(
            """
            SELECT id FROM parcels
             WHERE jurisdiction_id = :jid
               AND lower(regexp_replace(coalesce(address, ''), '[.,;:!?\"''`()\\[\\]{}/\\\\]', ' ', 'g')) = :addr
             LIMIT 2
            """
        ).bindparams(jid=listing.jurisdiction_id, addr=norm)
    )
    rows = row.fetchall()
    if len(rows) == 1:
        return MatchResult(
            matched_parcel_id=int(rows[0][0]),
            match_confidence=1.0,
            match_method=_TIER_1,
            geocoded_lat=None,
            geocoded_lon=None,
        )
    # Multiple exact matches (e.g. duplicate address rows in parcels)
    # — push to Tier 3 with geocode, won't auto-apply
    return None


async def _tier2_stripped(
    listing: ForsaleListing, db: AsyncSession
) -> MatchResult | None:
    """Strip unit + ZIP+4 + retry. Confidence 0.95."""
    norm = strip_unit(listing.address)
    if not norm:
        return None
    row = await db.execute(
        text(
            """
            SELECT id FROM parcels
             WHERE jurisdiction_id = :jid
               AND lower(regexp_replace(coalesce(address, ''), '[.,;:!?\"''`()\\[\\]{}/\\\\]', ' ', 'g')) = :addr
             LIMIT 2
            """
        ).bindparams(jid=listing.jurisdiction_id, addr=norm)
    )
    rows = row.fetchall()
    if len(rows) == 1:
        return MatchResult(
            matched_parcel_id=int(rows[0][0]),
            match_confidence=0.95,
            match_method=_TIER_2,
            geocoded_lat=None,
            geocoded_lon=None,
        )
    return None


async def _tier3_geocode(
    listing: ForsaleListing, db: AsyncSession
) -> MatchResult | None:
    """Geocode via Census, then spatial query within 50m. 1 hit = 0.85,
    multiple = 0.65 (flag), 0 = unmatched."""
    geo = await geocode_address(listing.address, listing.city, listing.state)
    if geo is None:
        return None

    rows = (
        await db.execute(
            text(
                """
                SELECT id
                  FROM parcels
                 WHERE jurisdiction_id = :jid
                   AND centroid IS NOT NULL
                   AND ST_DWithin(
                         centroid::geography,
                         ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                         50
                       )
                 LIMIT 5
                """
            ).bindparams(
                jid=listing.jurisdiction_id,
                lon=geo.lon,
                lat=geo.lat,
            )
        )
    ).fetchall()

    if not rows:
        return MatchResult(
            matched_parcel_id=None,
            match_confidence=None,
            match_method=None,
            geocoded_lat=geo.lat,
            geocoded_lon=geo.lon,
        )
    if len(rows) == 1:
        return MatchResult(
            matched_parcel_id=int(rows[0][0]),
            match_confidence=0.85,
            match_method=_TIER_3_ONE,
            geocoded_lat=geo.lat,
            geocoded_lon=geo.lon,
        )
    # Multiple — flag for review, don't auto-apply
    return MatchResult(
        matched_parcel_id=None,
        match_confidence=0.65,
        match_method=_TIER_3_MANY,
        geocoded_lat=geo.lat,
        geocoded_lon=geo.lon,
    )


async def match_listing(
    listing: ForsaleListing, db: AsyncSession
) -> MatchResult:
    """Run the cascade. Writes the result to the listing row. Caller
    must commit. Returns the result so the listing-alert worker can
    decide whether to fire an email."""
    result = await _tier1_exact(listing, db)
    if result is None:
        result = await _tier2_stripped(listing, db)
    if result is None:
        result = await _tier3_geocode(listing, db)
    if result is None:
        # Nothing matched, no geocode
        result = MatchResult(None, None, None, None, None)

    # Confidence < 0.85 → don't apply matched_parcel_id to scoring.
    # Schema column matched_parcel_id is still stored when match_method
    # is set; it's the score side's job to filter on match_confidence.
    listing.matched_parcel_id = result.matched_parcel_id
    listing.match_confidence = (
        None if result.match_confidence is None else float(result.match_confidence)
    )
    listing.match_method = result.match_method
    listing.geocoded_lat = result.geocoded_lat
    listing.geocoded_lon = result.geocoded_lon
    return result


async def match_pending_listings(
    jurisdiction_id: uuid.UUID,
    source: str,
    db: AsyncSession,
) -> dict:
    """Match every unmatched listing for (jurisdiction, source).
    Idempotent — already-matched rows are skipped.

    Returns ``{processed, tier_1, tier_2, tier_3_one, tier_3_multi, unmatched}``
    for diagnostic logging.
    """
    stmt = (
        select(ForsaleListing)
        .where(
            ForsaleListing.jurisdiction_id == jurisdiction_id,
            ForsaleListing.source == source,
            ForsaleListing.is_current.is_(True),
            ForsaleListing.matched_parcel_id.is_(None),
            ForsaleListing.match_method.is_(None),
        )
    )
    listings = list((await db.execute(stmt)).scalars().all())

    counters = {
        "processed": 0,
        "tier_1": 0,
        "tier_2": 0,
        "tier_3_one": 0,
        "tier_3_multi": 0,
        "unmatched": 0,
    }
    for listing in listings:
        result = await match_listing(listing, db)
        counters["processed"] += 1
        method = result.match_method or "unmatched"
        if method == _TIER_1:
            counters["tier_1"] += 1
        elif method == _TIER_2:
            counters["tier_2"] += 1
        elif method == _TIER_3_ONE:
            counters["tier_3_one"] += 1
        elif method == _TIER_3_MANY:
            counters["tier_3_multi"] += 1
        else:
            counters["unmatched"] += 1
    await db.commit()
    logger.info(
        "matched %s/%s listings for juris=%s source=%s: %s",
        counters["processed"] - counters["unmatched"],
        counters["processed"],
        jurisdiction_id,
        source,
        counters,
    )
    return counters


__all__ = ["MatchResult", "match_listing", "match_pending_listings"]
