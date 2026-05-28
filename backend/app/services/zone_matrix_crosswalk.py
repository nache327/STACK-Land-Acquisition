"""Crosswalk per-city zone_use_matrix rows into a county jurisdiction.

Background
----------
A county-as-jurisdiction (e.g. Salt Lake County, UT — parcel_source='county_gis')
holds parcels spanning many cities. Each parcel carries its real city in
`parcels.city`. Each city *also* exists as its own jurisdiction with its own
zone_use_matrix (Sandy, SLC, Draper, …). The same `zone_code` means different
things across cities, so a single county-default matrix is wrong.

The query-time LATERAL join in buybox_scoring.py already picks the most specific
matrix row (`municipality = p.city` wins over `municipality IS NULL`). This
service is what FEEDS that join for a county: it copies each sibling city
jurisdiction's active NULL-municipality rows into the county jurisdiction as
`municipality`-tagged rows.

Identity & sibling discovery
----------------------------
Jurisdictions relate only through the string fields `state` + `county`
(jurisdiction.py — no parent FK). A sibling city of the county is any
jurisdiction with the same `(state, county)`, a different `id`, and
`parcel_source IS DISTINCT FROM 'county_gis'`.

The crosswalk's `municipality` must match `parcels.city` for the join to fire.
We normalize the city jurisdiction's name with the same `_strip_state_suffix`
helper used elsewhere ("Sandy, UT" → "Sandy"). Any mismatch against the
authoritative `parcels.city` set is surfaced in the summary's `unmatched_cities`
list rather than silently dropped.

Human-edit protection
---------------------
The upsert mirrors the pipeline's guard (pipeline.py:2100): the
`on_conflict_do_update` skips rows where `human_reviewed=True` OR
`classification_source='human'`. So a human edit on a county row survives both
re-ingest and a crosswalk re-run.

Rows are tagged `classification_source='crosswalk'` (enum value added in
migration 0032) so the audit trail records that the verdict came from a
sibling city's matrix, not a direct ordinance read.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction, ParcelSource
from app.models.zone_use_matrix import ClassificationSource, ZoneUseMatrix
from app.services.zoning_system import _strip_state_suffix

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrosswalkRowPlan:
    """One planned upsert into the county jurisdiction."""
    municipality: str
    zone_code: str
    zone_name: str | None
    self_storage: Any
    mini_warehouse: Any
    light_industrial: Any
    luxury_garage_condo: Any
    citations: list | None
    confidence: float | None
    notes: str | None


def plan_crosswalk_rows(
    city_rows: list[dict],
) -> tuple[list[CrosswalkRowPlan], list[str]]:
    """Pure planner: turn a list of source city-matrix rows into upsert plans.

    Each input row is a dict shaped like:
        {
            "city_name": str,        # jurisdiction.name from the sibling city
            "zone_code": str,
            "zone_name": str | None,
            "self_storage": UsePermission,
            "mini_warehouse": UsePermission,
            "light_industrial": UsePermission,
            "luxury_garage_condo": UsePermission,
            "citations": list | None,
            "confidence": float | None,
            "notes": str | None,
        }

    Returns (plans, normalized_cities_seen). Cities are normalized via
    `_strip_state_suffix` so they line up with parcels.city.
    """
    plans: list[CrosswalkRowPlan] = []
    cities_seen: set[str] = set()
    for row in city_rows:
        municipality = _strip_state_suffix(row["city_name"])
        if not municipality:
            continue
        cities_seen.add(municipality)
        plans.append(
            CrosswalkRowPlan(
                municipality=municipality,
                zone_code=row["zone_code"],
                zone_name=row.get("zone_name"),
                self_storage=row["self_storage"],
                mini_warehouse=row["mini_warehouse"],
                light_industrial=row["light_industrial"],
                luxury_garage_condo=row["luxury_garage_condo"],
                citations=row.get("citations"),
                confidence=row.get("confidence"),
                notes=row.get("notes"),
            )
        )
    return plans, sorted(cities_seen)


async def crosswalk_county_from_cities(
    county_jurisdiction_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Copy sibling city zone matrices into the county jurisdiction.

    Idempotent. Safe to re-run — refreshes crosswalked rows but never
    overwrites a human edit on the county.
    """
    county = await db.get(Jurisdiction, county_jurisdiction_id)
    if county is None:
        raise ValueError(f"Jurisdiction {county_jurisdiction_id} not found")
    if county.parcel_source != ParcelSource.county_gis:
        raise ValueError(
            f"Jurisdiction {county.name} is not a county "
            f"(parcel_source={county.parcel_source}); crosswalk only applies "
            f"to county-as-jurisdiction setups."
        )

    siblings = (await db.execute(
        select(Jurisdiction).where(
            Jurisdiction.state == county.state,
            Jurisdiction.county == county.county,
            Jurisdiction.id != county.id,
            Jurisdiction.parcel_source.is_distinct_from(ParcelSource.county_gis),
        )
    )).scalars().all()

    if not siblings:
        logger.warning(
            "Crosswalk: no sibling city jurisdictions for %s (%s/%s); "
            "nothing to copy.",
            county.name, county.state, county.county,
        )
        return {
            "county_jurisdiction_id": str(county.id),
            "siblings_seen": 0,
            "rows_written": 0,
            "rows_skipped_human": 0,
            "cities_seen": [],
            "unmatched_cities": [],
        }

    sibling_ids = [s.id for s in siblings]
    sibling_name_by_id = {s.id: s.name for s in siblings}

    src_rows = (await db.execute(
        select(ZoneUseMatrix).where(
            ZoneUseMatrix.jurisdiction_id.in_(sibling_ids),
            ZoneUseMatrix.municipality.is_(None),
            ZoneUseMatrix.deleted_at.is_(None),
        )
    )).scalars().all()

    city_rows: list[dict] = []
    for r in src_rows:
        city_rows.append({
            "city_name": sibling_name_by_id[r.jurisdiction_id],
            "zone_code": r.zone_code,
            "zone_name": r.zone_name,
            "self_storage": r.self_storage,
            "mini_warehouse": r.mini_warehouse,
            "light_industrial": r.light_industrial,
            "luxury_garage_condo": r.luxury_garage_condo,
            "citations": r.citations,
            "confidence": float(r.confidence) if r.confidence is not None else None,
            "notes": r.notes,
        })

    plans, cities_seen = plan_crosswalk_rows(city_rows)

    rows_written = 0
    rows_skipped_human = 0
    for plan in plans:
        existing = (await db.execute(
            select(ZoneUseMatrix).where(
                ZoneUseMatrix.jurisdiction_id == county.id,
                ZoneUseMatrix.zone_code == plan.zone_code,
                ZoneUseMatrix.municipality == plan.municipality,
                ZoneUseMatrix.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing is not None and (
            existing.human_reviewed
            or existing.classification_source == ClassificationSource.human
        ):
            rows_skipped_human += 1
            continue

        stmt = pg_insert(ZoneUseMatrix).values(
            jurisdiction_id=county.id,
            zone_code=plan.zone_code,
            zone_name=plan.zone_name,
            municipality=plan.municipality,
            self_storage=plan.self_storage,
            mini_warehouse=plan.mini_warehouse,
            light_industrial=plan.light_industrial,
            luxury_garage_condo=plan.luxury_garage_condo,
            citations=plan.citations,
            confidence=plan.confidence,
            notes=plan.notes,
            classification_source=ClassificationSource.crosswalk,
        ).on_conflict_do_update(
            constraint="uq_zone_matrix",
            set_=dict(
                zone_name=plan.zone_name,
                self_storage=plan.self_storage,
                mini_warehouse=plan.mini_warehouse,
                light_industrial=plan.light_industrial,
                luxury_garage_condo=plan.luxury_garage_condo,
                citations=plan.citations,
                confidence=plan.confidence,
                notes=plan.notes,
                classification_source=ClassificationSource.crosswalk,
            ),
            where=(
                (ZoneUseMatrix.human_reviewed == False)  # noqa: E712
                & (ZoneUseMatrix.classification_source != ClassificationSource.human)
            ),
        )
        await db.execute(stmt)
        rows_written += 1

    parcel_cities = set((await db.execute(
        text(
            "SELECT DISTINCT city FROM parcels "
            "WHERE jurisdiction_id = :jid AND city IS NOT NULL"
        ).bindparams(jid=county.id)
    )).scalars().all())

    crosswalked_cities = set(cities_seen)
    unmatched_cities = sorted(crosswalked_cities - parcel_cities)
    parcel_cities_without_zoning = sorted(parcel_cities - crosswalked_cities)

    await db.flush()

    logger.info(
        "Crosswalk: %s — %d siblings, %d rows written, %d human-protected, "
        "%d unmatched city names, %d parcel cities without a sibling matrix.",
        county.name, len(siblings), rows_written, rows_skipped_human,
        len(unmatched_cities), len(parcel_cities_without_zoning),
    )

    return {
        "county_jurisdiction_id": str(county.id),
        "siblings_seen": len(siblings),
        "rows_written": rows_written,
        "rows_skipped_human": rows_skipped_human,
        "cities_seen": cities_seen,
        "unmatched_cities": unmatched_cities,
        "parcel_cities_without_zoning": parcel_cities_without_zoning,
    }
