"""Backfill ``parcels.zoning_code`` on a county jurisdiction from its
sibling per-city jurisdictions.

Why this exists: a county-wide UGRC parcel ingest (e.g.
``Parcels_SaltLake/FeatureServer/0``) leaves ``zoning_code`` NULL on the
vast majority of rows — the county-wide pull doesn't carry the ZONING
attribute that the per-city pulls populate via spatial join to each
city's zoning polygons. With ``zoning_code`` NULL, the LATERAL join in
``buybox_scoring`` resolves every parcel to no ``zone_use_matrix`` row, so
even after the city→county crosswalk runs the per-city verdicts never
fire. This module copies each sibling city's ``zoning_code`` onto the
matching county parcels.

This logic was previously inline in the
``/jurisdictions/{id}/_backfill-zoning-from-siblings`` endpoint. It now
lives here so the endpoint AND the ingest pipeline call one function —
the pipeline runs it automatically as a county-only post-ingest stage so
operators no longer have to hit the endpoint by hand.

Idempotent and NULL-only: never overwrites a parcel that already has a
``zoning_code``. Safe to re-run after additional sibling ingests.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction, ParcelSource
from app.services.zone_matrix_crosswalk import _normalize_for_match

logger = logging.getLogger(__name__)

VALID_STRATEGIES = ("apn", "spatial", "both")


class NotACountyError(ValueError):
    """Raised when the target jurisdiction is not a county-as-jurisdiction."""


async def backfill_zoning_from_siblings(
    jurisdiction_id: uuid.UUID,
    db: AsyncSession,
    strategy: str = "both",
) -> dict:
    """Copy ``parcels.zoning_code`` from sibling per-city jurisdictions onto
    this county's parcels.

    Strategies:

    - ``apn``: join on ``parcels.apn``. Fast and unambiguous when both
      jurisdictions share an APN namespace (UGRC ↔ UGRC).
    - ``spatial``: spatial-join the county parcel's centroid to the sibling
      parcel's polygon. Needed across APN namespaces (e.g. Draper City via
      services2.arcgis.com).
    - ``both`` (default for the pipeline): APN match first, then a spatial
      pass over the remaining NULLs.

    Raises ``ValueError`` for an unknown strategy and ``NotACountyError`` when
    the jurisdiction is not a county. Callers in HTTP context translate these
    to 4xx; the pipeline treats them as non-fatal skips.
    """
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"strategy must be apn|spatial|both, got {strategy!r}")

    county = await db.get(Jurisdiction, jurisdiction_id)
    if county is None:
        raise ValueError(f"Jurisdiction {jurisdiction_id} not found")
    if county.parcel_source != ParcelSource.county_gis:
        raise NotACountyError(
            f"{county.name} is not a county (parcel_source={county.parcel_source})"
        )

    # Sibling discovery — parcels.city is the authoritative city list (the
    # strings the buybox LATERAL join keys on); look up jurisdictions in the
    # same state whose normalized name matches one of those values.
    parcel_cities = set((await db.execute(
        text(
            "SELECT DISTINCT city FROM parcels "
            "WHERE jurisdiction_id = :jid AND city IS NOT NULL"
        ).bindparams(jid=county.id)
    )).scalars().all())
    parcel_city_lookup = {_normalize_for_match(c): c for c in parcel_cities}

    all_state_jurs = (await db.execute(
        select(Jurisdiction).where(
            Jurisdiction.state == county.state,
            Jurisdiction.id != county.id,
            Jurisdiction.parcel_source.is_distinct_from(ParcelSource.county_gis),
        )
    )).scalars().all()
    siblings = [
        (j, parcel_city_lookup[_normalize_for_match(j.name)])
        for j in all_state_jurs
        if _normalize_for_match(j.name) in parcel_city_lookup
    ]

    per_city_apn: dict[str, int] = {}
    per_city_spatial: dict[str, int] = {}
    total = 0

    for sibling, parcel_city in siblings:
        # APN pass — fast, unambiguous, only fires when both jurisdictions
        # share an APN namespace (UGRC ↔ UGRC).
        if strategy in ("apn", "both"):
            result = await db.execute(
                text(
                    """
                    UPDATE parcels p
                       SET zoning_code = s.zoning_code,
                           zone_class  = COALESCE(s.zone_class, p.zone_class)
                      FROM parcels s
                     WHERE p.jurisdiction_id = :cid
                       AND p.zoning_code IS NULL
                       AND p.city = :city
                       AND p.apn IS NOT NULL
                       AND s.jurisdiction_id = :sid
                       AND s.apn = p.apn
                       AND s.zoning_code IS NOT NULL
                    """
                ).bindparams(cid=county.id, sid=sibling.id, city=parcel_city)
            )
            per_city_apn[parcel_city] = result.rowcount or 0
            total += per_city_apn[parcel_city]

        # Spatial pass — centroid-in-polygon. Slower but works across APN
        # namespaces. DISTINCT ON resolves the rare case where one centroid
        # falls inside multiple sibling polygons (overlap / boundary).
        if strategy in ("spatial", "both"):
            result = await db.execute(
                text(
                    """
                    WITH matches AS (
                      SELECT DISTINCT ON (p.id)
                             p.id AS pid, s.zoning_code, s.zone_class
                        FROM parcels p
                        JOIN parcels s
                          ON ST_Within(p.centroid, s.geom)
                       WHERE p.jurisdiction_id = :cid
                         AND p.zoning_code IS NULL
                         AND p.city = :city
                         AND p.centroid IS NOT NULL
                         AND s.jurisdiction_id = :sid
                         AND s.geom IS NOT NULL
                         AND s.zoning_code IS NOT NULL
                       ORDER BY p.id, s.id
                    )
                    UPDATE parcels p
                       SET zoning_code = m.zoning_code,
                           zone_class  = COALESCE(m.zone_class, p.zone_class)
                      FROM matches m
                     WHERE p.id = m.pid
                    """
                ).bindparams(cid=county.id, sid=sibling.id, city=parcel_city)
            )
            per_city_spatial[parcel_city] = result.rowcount or 0
            total += per_city_spatial[parcel_city]

    await db.flush()

    return {
        "county_jurisdiction_id": str(county.id),
        "siblings_seen": len(siblings),
        "strategy": strategy,
        "rows_updated": total,
        "per_city_apn": per_city_apn,
        "per_city_spatial": per_city_spatial,
    }
