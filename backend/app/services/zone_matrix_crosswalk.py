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

from sqlalchemy import func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import Jurisdiction, ParcelSource
from app.models.zone_use_matrix import ClassificationSource, ZoneUseMatrix
from app.services.zoning_system import _strip_state_suffix

logger = logging.getLogger(__name__)


def _normalize_for_match(name: str) -> str:
    """Normalize a jurisdiction name or parcels.city value into the canonical
    form used for sibling matching.

    - strip a trailing ', XX' state suffix (e.g. 'Sandy, UT' → 'Sandy')
    - strip a trailing ' City' (e.g. 'Draper City' → 'Draper') because the
      UGRC PARCEL_CITY layer drops 'City' and county-jurisdiction parcels
      under it carry the bare form.
    - case-fold so 'Salt Lake City' and 'salt lake city' match.

    Note: keeps 'Salt Lake City' as 'Salt Lake' would be wrong — only the
    *trailing* ' City' is stripped, never an internal occurrence.
    """
    s = _strip_state_suffix(name).strip()
    # Don't strip 'City' from 'Salt Lake City' — only when ' City' is a true
    # trailing word and removing it leaves a non-empty stem distinct from
    # 'Salt Lake City'. We check: stripping leaves something AND the
    # something doesn't itself end in ' City' (so we don't recurse).
    if s.lower().endswith(" city") and s[:-5].strip().lower() != "salt lake":
        s = s[:-5].strip()
    return s.casefold()


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
    seed_stubs: bool = False,
) -> dict:
    """Copy sibling city zone matrices into the county jurisdiction.

    When ``seed_stubs=True``, also insert placeholder rows for every
    (city, zone_code) pair where the city has parcels under this county
    but no sibling jurisdiction with a real matrix to copy from. The
    stubs are tagged ``classification_source='inherited_pending'`` with
    all permissions=unclear, so analysts can find and hand-edit them in
    the verifier. A future crosswalk run will replace any
    inherited_pending row whose city later gets a real sibling matrix
    (the upsert WHERE clause excludes only human rows).

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

    # Sibling discovery is driven by parcels.city values under the county
    # (the authoritative city list — those are the strings the LATERAL join
    # in buybox_scoring keys on), not by the jurisdictions.county field
    # which is unreliable (NULL for most UT cities; mixed 'Salt Lake' vs
    # 'Salt Lake County' values for the rest). We pick up every UT
    # jurisdiction whose normalized name matches one of those cities.
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
    siblings = [j for j in all_state_jurs if _normalize_for_match(j.name) in parcel_city_lookup]

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
    # The municipality we write MUST equal parcels.city verbatim (that's
    # the join key in buybox_scoring's LATERAL). For each sibling we
    # already found the matching parcels.city via normalization — use
    # that exact value, NOT the jurisdiction's name.
    sibling_parcel_city_by_id = {
        s.id: parcel_city_lookup[_normalize_for_match(s.name)] for s in siblings
    }

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
            "city_name": sibling_parcel_city_by_id[r.jurisdiction_id],
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
            # The prod uq_zone_matrix index is partial:
            #   CREATE UNIQUE INDEX uq_zone_matrix
            #     ON zone_use_matrix
            #     (jurisdiction_id, zone_code, COALESCE(municipality, ''::text))
            #     WHERE (deleted_at IS NULL)
            # For ON CONFLICT to bind to a partial unique index Postgres
            # requires the index_elements AND a matching index_where predicate.
            # `literal_column("''::text")` renders the empty string as an
            # inline text literal (matching the indexed expression byte-for-
            # byte); a Python "" would get parametrized to $N::VARCHAR and
            # break the match.
            index_elements=[
                ZoneUseMatrix.jurisdiction_id,
                ZoneUseMatrix.zone_code,
                func.coalesce(ZoneUseMatrix.municipality, literal_column("''::text")),
            ],
            index_where=ZoneUseMatrix.deleted_at.is_(None),
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

    stubs_written = 0
    stub_cities_seeded: list[str] = []
    stub_city_diagnostics: dict[str, dict] = {}
    if seed_stubs and parcel_cities_without_zoning:
        # For each city without a sibling matrix, find the distinct
        # zoning_codes its parcels carry, and insert one stub per pair.
        # The municipality is the verbatim parcels.city value (same as
        # the real crosswalk), so the LATERAL join in buybox_scoring
        # picks the stub over the NULL county-default.
        #
        # Per-city loop instead of a single ANY(:cities) array bind:
        # asyncpg+SQLAlchemy text() with a Python list silently matched
        # nothing on the first try (no error, just stubs_written=0).
        # 9 small queries is fine and unambiguous.
        stub_rows: list[tuple[str, str]] = []
        for city in parcel_cities_without_zoning:
            codes = (await db.execute(
                text(
                    "SELECT DISTINCT zoning_code "
                    "FROM parcels "
                    "WHERE jurisdiction_id = :jid "
                    "  AND city = :c "
                    "  AND zoning_code IS NOT NULL"
                ).bindparams(jid=county.id, c=city)
            )).scalars().all()
            stub_city_diagnostics[city] = {"distinct_zoning_codes": len(codes)}
            for code in codes:
                stub_rows.append((city, code))
        for city, zone_code in stub_rows:
            existing = (await db.execute(
                select(ZoneUseMatrix).where(
                    ZoneUseMatrix.jurisdiction_id == county.id,
                    ZoneUseMatrix.zone_code == zone_code,
                    ZoneUseMatrix.municipality == city,
                    ZoneUseMatrix.deleted_at.is_(None),
                )
            )).scalar_one_or_none()
            if existing is not None and (
                existing.human_reviewed
                or existing.classification_source == ClassificationSource.human
                or existing.classification_source == ClassificationSource.crosswalk
            ):
                # Don't stub on top of a real crosswalk row or human edit.
                continue
            stmt = pg_insert(ZoneUseMatrix).values(
                jurisdiction_id=county.id,
                zone_code=zone_code,
                zone_name=None,
                municipality=city,
                self_storage="unclear",
                mini_warehouse="unclear",
                light_industrial="unclear",
                luxury_garage_condo="unclear",
                citations=None,
                confidence=None,
                notes="Stub seeded by _crosswalk-cities?seed_stubs=true — awaiting per-city sibling matrix or hand-edit in the verifier.",
                classification_source=ClassificationSource.inherited_pending,
            ).on_conflict_do_update(
                index_elements=[
                    ZoneUseMatrix.jurisdiction_id,
                    ZoneUseMatrix.zone_code,
                    func.coalesce(ZoneUseMatrix.municipality, literal_column("''::text")),
                ],
                index_where=ZoneUseMatrix.deleted_at.is_(None),
                set_=dict(
                    # Idempotent: re-running just refreshes the inherited_pending
                    # marker; crosswalk/human rows are excluded by the WHERE.
                    classification_source=ClassificationSource.inherited_pending,
                ),
                where=(
                    (ZoneUseMatrix.human_reviewed == False)  # noqa: E712
                    & (ZoneUseMatrix.classification_source != ClassificationSource.human)
                    & (ZoneUseMatrix.classification_source != ClassificationSource.crosswalk)
                ),
            )
            await db.execute(stmt)
            stubs_written += 1
        stub_cities_seeded = sorted({c for c, _ in stub_rows})

    await db.flush()

    logger.info(
        "Crosswalk: %s — %d siblings, %d rows written, %d stubs, %d human-protected, "
        "%d unmatched city names, %d parcel cities without a sibling matrix.",
        county.name, len(siblings), rows_written, stubs_written, rows_skipped_human,
        len(unmatched_cities), len(parcel_cities_without_zoning),
    )

    return {
        "county_jurisdiction_id": str(county.id),
        "siblings_seen": len(siblings),
        "rows_written": rows_written,
        "rows_skipped_human": rows_skipped_human,
        "stubs_written": stubs_written,
        "stub_cities_seeded": stub_cities_seeded,
        "stub_city_diagnostics": stub_city_diagnostics,
        "cities_seen": cities_seen,
        "unmatched_cities": unmatched_cities,
        "parcel_cities_without_zoning": parcel_cities_without_zoning,
    }
