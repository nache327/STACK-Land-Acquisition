"""One authoritative municipality-name normalizer + alias resolution.

Background
----------
Municipality is not a first-class entity in this app — it lives as free
text in ``parcels.city`` and ``zone_use_matrix.municipality``. Three
divergent helpers historically normalized names ad hoc:

- ``zone_matrix_crosswalk._normalize_for_match`` (strips ", XX" + trailing
  " City", with a "Salt Lake City" guard, casefolds)
- ``zoning_system._strip_state_suffix`` (strips ", XX")
- ``jurisdiction_match.strip_state_suffix_lower`` (strips ", XX", lowercases)

Divergence means a parcel city string can match in one code path and not
another, producing silent pairing gaps for county jurisdictions. This
module provides the single ``canonical_city`` used everywhere for matching,
plus ``resolve_municipality`` which consults the per-jurisdiction
``municipality_aliases`` table (migration 0038) before falling back to
canonicalization.

IMPORTANT — display vs match: ``canonical_city`` returns a casefolded
*matching key*, NOT a display value. The string stored in
``zone_use_matrix.municipality`` must remain the verbatim ``parcels.city``
value (that is the exact-string join key in buybox_scoring). Use this
module only to decide whether two city strings refer to the same place.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.zoning_system import _strip_state_suffix


def canonical_city(name: str | None) -> str:
    """Normalize a jurisdiction name or ``parcels.city`` value into the
    canonical matching key.

    - strip a trailing ", XX" state suffix ("Sandy, UT" -> "Sandy")
    - strip a trailing " City" ("Draper City" -> "Draper"), because the
      UGRC PARCEL_CITY layer drops "City" and county parcels carry the bare
      form — EXCEPT "Salt Lake City", where the trailing word is part of the
      name (guarded so "Salt Lake City" never collapses to "Salt Lake").
    - casefold so "Salt Lake City" and "salt lake city" match.

    Returns "" for falsy input. This is the consolidation of the three
    historical helpers; ``_normalize_for_match`` delegates here.
    """
    if not name:
        return ""
    s = _strip_state_suffix(name).strip()
    if s.lower().endswith(" city") and s[:-5].strip().lower() != "salt lake":
        s = s[:-5].strip()
    return s.casefold()


async def load_alias_map(
    jurisdiction_id: uuid.UUID, db: AsyncSession
) -> dict[str, str]:
    """Return ``{canonical(alias_city) -> canonical_city}`` for one
    jurisdiction. Empty dict when the table has no rows for it (the common
    case until aliases are seeded), so callers behave exactly as pre-0038.
    """
    rows = (await db.execute(
        text(
            "SELECT alias_city, canonical_city FROM municipality_aliases "
            "WHERE jurisdiction_id = :jid"
        ).bindparams(jid=jurisdiction_id)
    )).all()
    return {canonical_city(alias): canon for alias, canon in rows}


def resolve_with_alias_map(raw_city: str | None, alias_map: dict[str, str]) -> str:
    """Resolve a raw city string to its canonical matching key, applying an
    alias map first. ``alias_map`` is keyed by ``canonical_city(alias)`` and
    its values are the canonical city strings (as stored on the matrix side);
    we re-canonicalize the mapped value so the result is comparable.
    """
    key = canonical_city(raw_city)
    if key in alias_map:
        return canonical_city(alias_map[key])
    return key


async def resolve_municipality(
    jurisdiction_id: uuid.UUID, raw_city: str | None, db: AsyncSession
) -> str:
    """Convenience single-shot resolver. Prefer ``load_alias_map`` once +
    ``resolve_with_alias_map`` in loops to avoid a query per row.
    """
    alias_map = await load_alias_map(jurisdiction_id, db)
    return resolve_with_alias_map(raw_city, alias_map)
