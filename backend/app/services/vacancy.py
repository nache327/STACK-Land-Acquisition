"""
Vacancy detection service.

Determines whether a parcel has an existing structure using (in priority order):
  1. Assessor improvement value (improvement_value > 0  →  has_structure = True)
  2. Microsoft Building Footprints or OSM buildings in PostGIS
     (ST_Intersects with parcel geometry)
  3. Land-use code keywords (VACANT LAND, VACANT RES, VACANT COMM …)
  4. NULL → caveat surfaced in UI

Phase 1: constants and interface defined.
Phase 4: full PostGIS intersection logic.
"""
from __future__ import annotations

# Land-use code values that indicate a vacant parcel (case-insensitive)
VACANT_LANDUSE_CODES: frozenset[str] = frozenset({
    "vacant land",
    "vacant res",
    "vacant residential",
    "vacant comm",
    "vacant commercial",
    "vacant industrial",
    "unimproved land",
    "bare land",
    "undeveloped",
    "vac land",
    "vac res",
    "vac comm",
    "vacnt",
})


def is_vacant_by_landuse(land_use_code: str | None) -> bool | None:
    """
    Returns True if the land-use code clearly indicates vacancy,
    False if it clearly indicates a structure, None if indeterminate.
    """
    if land_use_code is None:
        return None
    return land_use_code.lower().strip() in VACANT_LANDUSE_CODES


def is_vacant_by_improvement_value(improvement_value: float | None) -> bool | None:
    """
    Returns True if improvement_value == 0, False if > 0, None if unknown.
    """
    if improvement_value is None:
        return None
    return improvement_value == 0


async def compute_vacancy_batch(
    parcel_ids: list[int],
    db: object,  # AsyncSession — typed as object to avoid circular import
) -> dict[int, bool | None]:
    """
    Compute has_structure for a batch of parcels using PostGIS building-footprint
    intersection. Returns {parcel_id: has_structure | None}.

    Phase 4 implementation.
    """
    raise NotImplementedError("Building-footprint intersection implemented in Phase 4.")
