"""Cascade matcher: ForsaleListing -> Parcel.

Six tiers. The first that produces a match writes the result back to
the listing and returns. Confidence < 0.85 stores match_method (so
the operator sees what happened) and matched_parcel_id (so the UI
can still surface the card), but with the lower confidence the
scorer's listing_score_boost should NOT auto-apply — that decision
lives in buybox_scoring.

  Tier 1 — Normalized address exact match. Confidence 1.0.
  Tier 2 — Strip unit + ZIP+4, retry. Confidence 0.95.
  Tier 3 — Census geocode + ST_DWithin(100m), 1 hit. Confidence 0.85.
  Tier 4 — Nominatim (OSM) geocode + ST_DWithin(100m), 1 hit.
           Free OSM fallback for grid-style addresses Census can't
           resolve (Utah "1170 E 3200 N", etc). Confidence 0.85.
  Tier 5 — Multiple parcels within radius, same owner_name as the
           NEAREST. Treat as a same-owner cluster sale. Primary =
           largest acreage. co_listed_parcels populated. Confidence
           0.85 (owner corroboration = high).
  Tier 6 — Multiple parcels within radius, no shared owner. Pick the
           NEAREST. Confidence 0.75 (no corroboration).

`match_pending_listings` is the batch entry point invoked from the
upload background task. Idempotent — only re-touches rows where
match_method IS NULL.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forsale_listing import ForsaleListing
from app.services.address_normalizer import normalize, strip_unit
from app.services.geocode_census import geocode_address as geocode_census
from app.services.geocode_nominatim import geocode_address as geocode_nominatim

logger = logging.getLogger(__name__)

_TIER_1 = "exact_address"
_TIER_2 = "stripped_address"
_TIER_3 = "geocode_census_1"
_TIER_4 = "geocode_nominatim_1"
_TIER_5 = "geocode_owner_cluster"
_TIER_6 = "geocode_nearest"
# Stamped when ``rematch_listing`` finds a single-parcel hit using the
# listing's previously-cached geocoded_lat/lon (no re-geocode call). Lets
# operators tell rematch hits apart from first-ingest hits in diagnostics.
_TIER_GEOCODE_CACHED = "geocode_cached_1"

# Spatial radius for geocode-based tiers. 100m is generous enough to
# handle minor address drift (broker types "Main St" vs county's
# "Main Street") without sweeping in unrelated parcels in suburban
# parcel grids.
_SPATIAL_RADIUS_M = 100


@dataclass
class GeocodedPoint:
    lat: float
    lon: float
    source: str  # 'census' | 'nominatim'


@dataclass
class MatchResult:
    matched_parcel_id: int | None
    match_confidence: float | None
    match_method: str | None
    geocoded_lat: float | None
    geocoded_lon: float | None
    co_listed_parcels: list | None = None


# ── Tier 1/2 — direct address comparison ─────────────────────────────────────


async def _tier1_exact(
    listing: ForsaleListing, db: AsyncSession
) -> MatchResult | None:
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
    return None


async def _tier2_stripped(
    listing: ForsaleListing, db: AsyncSession
) -> MatchResult | None:
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


# ── Geocode chain: Census, then Nominatim ────────────────────────────────────


async def _geocode_any(listing: ForsaleListing) -> GeocodedPoint | None:
    """Try Census first (faster, U.S.-tuned). Fall back to Nominatim
    when Census produces no match — recovers Utah grid addresses and
    other formats Census doesn't index."""
    c = await geocode_census(listing.address, listing.city, listing.state)
    if c is not None:
        return GeocodedPoint(lat=c.lat, lon=c.lon, source="census")
    n = await geocode_nominatim(listing.address, listing.city, listing.state)
    if n is not None:
        return GeocodedPoint(lat=n.lat, lon=n.lon, source="nominatim")
    return None


# ── Tier 3-6 — geocode-driven matching ───────────────────────────────────────


async def _tier_geocode(
    listing: ForsaleListing, db: AsyncSession
) -> MatchResult | None:
    """Single function covering the geocode-driven tiers 3-6. We do
    one geocode call (chained Census→Nominatim) and one spatial query,
    then branch on the count of matches and the owner_name distribution.
    """
    geo = await _geocode_any(listing)
    if geo is None:
        return None
    return await _match_against_geocoded_point(listing, geo, db)


async def _match_against_geocoded_point(
    listing: ForsaleListing, geo: GeocodedPoint, db: AsyncSession
) -> MatchResult | None:
    """Run the spatial-search half of the geocode cascade against an
    already-computed point. Factored out of ``_tier_geocode`` so the
    rematch path can reuse a listing's previously-stored coords without
    calling the geocoder again.
    """
    # Pull up to 10 parcels within radius, sorted by distance ascending,
    # along with owner_name + acres for cluster + primary selection.
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    p.id,
                    p.apn,
                    p.owner_name,
                    p.acres,
                    ST_Distance(
                        p.centroid::geography,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                    ) AS dist_m
                  FROM parcels p
                 WHERE p.jurisdiction_id = :jid
                   AND p.centroid IS NOT NULL
                   AND ST_DWithin(
                         p.centroid::geography,
                         ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                         :radius
                       )
                 ORDER BY dist_m ASC
                 LIMIT 10
                """
            ).bindparams(
                jid=listing.jurisdiction_id,
                lon=geo.lon,
                lat=geo.lat,
                radius=_SPATIAL_RADIUS_M,
            )
        )
    ).all()

    if not rows:
        # Geocoded but no parcels nearby — store lat/lon so operator
        # can investigate, leave matched_parcel_id null.
        return MatchResult(
            matched_parcel_id=None,
            match_confidence=None,
            match_method=None,
            geocoded_lat=geo.lat,
            geocoded_lon=geo.lon,
        )

    if len(rows) == 1:
        # Single hit — clean match.
        r = rows[0]
        if geo.source == "cached":
            method = _TIER_GEOCODE_CACHED
        elif geo.source == "census":
            method = _TIER_3
        else:
            method = _TIER_4
        return MatchResult(
            matched_parcel_id=int(r.id),
            match_confidence=0.85,
            match_method=method,
            geocoded_lat=geo.lat,
            geocoded_lon=geo.lon,
        )

    # Multiple hits. First try same-owner clustering.
    nearest = rows[0]
    if nearest.owner_name:
        owner_key = nearest.owner_name.strip().lower()
        cluster = [
            r for r in rows
            if r.owner_name and r.owner_name.strip().lower() == owner_key
        ]
        if len(cluster) > 1:
            # Same owner sells N adjacent lots — record all, set
            # primary = largest acreage so the operator sees the
            # marquee parcel first.
            sorted_by_acres = sorted(
                cluster,
                key=lambda r: float(r.acres or 0),
                reverse=True,
            )
            primary = sorted_by_acres[0]
            co_listed = [
                {
                    "id": int(r.id),
                    "apn": r.apn,
                    "acres": float(r.acres) if r.acres is not None else None,
                    "is_primary": int(r.id) == int(primary.id),
                }
                for r in sorted_by_acres
            ]
            return MatchResult(
                matched_parcel_id=int(primary.id),
                match_confidence=0.85,
                match_method=_TIER_5,
                geocoded_lat=geo.lat,
                geocoded_lon=geo.lon,
                co_listed_parcels=co_listed,
            )

    # No owner cluster — pick the nearest parcel with lower confidence.
    # Operator will see match_method=geocode_nearest and confidence
    # 0.75 in the drawer, signaling "verify this".
    return MatchResult(
        matched_parcel_id=int(nearest.id),
        match_confidence=0.75,
        match_method=_TIER_6,
        geocoded_lat=geo.lat,
        geocoded_lon=geo.lon,
    )


# ── Public API ───────────────────────────────────────────────────────────────


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
        result = await _tier_geocode(listing, db)
    if result is None:
        result = MatchResult(None, None, None, None, None)

    listing.matched_parcel_id = result.matched_parcel_id
    listing.match_confidence = (
        None if result.match_confidence is None else float(result.match_confidence)
    )
    listing.match_method = result.match_method
    listing.geocoded_lat = result.geocoded_lat
    listing.geocoded_lon = result.geocoded_lon
    listing.co_listed_parcels = result.co_listed_parcels
    return result


async def match_pending_listings(
    jurisdiction_id: uuid.UUID,
    source: str,
    db: AsyncSession,
) -> dict:
    """Match every unmatched listing for (jurisdiction, source).
    Idempotent — only re-runs on rows where match_method IS NULL.

    Returns counters by tier for diagnostic logging.
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

    counters: dict[str, int] = {
        "processed": 0,
        "tier_1": 0,
        "tier_2": 0,
        "tier_3_census": 0,
        "tier_4_nominatim": 0,
        "tier_5_owner_cluster": 0,
        "tier_6_nearest": 0,
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
        elif method == _TIER_3:
            counters["tier_3_census"] += 1
        elif method == _TIER_4:
            counters["tier_4_nominatim"] += 1
        elif method == _TIER_5:
            counters["tier_5_owner_cluster"] += 1
        elif method == _TIER_6:
            counters["tier_6_nearest"] += 1
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


async def rematch_listing(
    listing: ForsaleListing, db: AsyncSession
) -> MatchResult:
    """Re-run the cascade against an EXISTING listing without re-geocoding.

    Tiers 1-2 (exact + stripped address) rerun unconditionally because
    they're cheap and may benefit from matcher logic improvements. Tiers
    3-6 reuse ``listing.geocoded_lat`` / ``listing.geocoded_lon`` if
    present, stamped with ``_TIER_GEOCODE_CACHED`` in the single-hit case
    so operators can tell rematch hits apart from first-ingest hits.

    Listings that were never geocoded (geocoded_lat IS NULL) get tiers
    1-2 only — they stay unmatched if address-based logic still can't
    place them. Geocoding is intentionally NOT re-run; that's the
    upstream geocoder's job during ingest.

    Caller must commit.
    """
    result = await _tier1_exact(listing, db)
    if result is None:
        result = await _tier2_stripped(listing, db)
    if (
        result is None
        and listing.geocoded_lat is not None
        and listing.geocoded_lon is not None
    ):
        point = GeocodedPoint(
            lat=float(listing.geocoded_lat),
            lon=float(listing.geocoded_lon),
            source="cached",
        )
        result = await _match_against_geocoded_point(listing, point, db)
    if result is None:
        # Preserve existing coords on the no-match path — we didn't
        # re-geocode, so blanking them would lose data.
        result = MatchResult(
            matched_parcel_id=None,
            match_confidence=None,
            match_method=None,
            geocoded_lat=listing.geocoded_lat,
            geocoded_lon=listing.geocoded_lon,
            co_listed_parcels=None,
        )

    listing.matched_parcel_id = result.matched_parcel_id
    listing.match_confidence = (
        None if result.match_confidence is None else float(result.match_confidence)
    )
    listing.match_method = result.match_method
    # Intentionally not touching geocoded_lat/lon — rematch is no-regeocode.
    listing.co_listed_parcels = result.co_listed_parcels
    return result


__all__ = [
    "MatchResult",
    "match_listing",
    "match_pending_listings",
    "rematch_listing",
]
