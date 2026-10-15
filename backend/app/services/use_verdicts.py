"""Per-asset "effective verdict" SQL expressions, keyed by use-case slug.

The buy-box scorer turns the four ``zone_use_matrix`` use columns into a single
permission string for a given product ("use case"). Self-storage reads its own
column directly. Luxury garage condo *derives* its verdict from the sibling
columns, because the stored ``luxury_garage_condo`` column is gate-suppressed
(post-ingest catch #58) in exactly the light-industrial / storage-dead zones
that are its best targets — so the stored column cannot be trusted for LGC
sourcing.

Each expression references the ``zum`` LATERAL alias in
``buybox_scoring._select_parcels_sql`` (which selects ``self_storage``,
``mini_warehouse`` and ``light_industrial``). The expression yields the
permission text, or NULL when no matrix row matched — NULL keeps the scorer's
``verdict_matched`` False (basis "ungrounded muni"), identical to how the
self_storage path treats a missing row.

SECURITY: these are code-owned constants selected by a validated slug. NEVER
interpolate user input into the returned SQL.

Keep the LGC tiers in lock-step with:
  * ``candidate_search._LGC_EFFECTIVE_LABEL`` (ORM twin, display/table path)
  * ``ordinance_parser._apply_luxury_garage_inference`` (the grounding rule)
"""
from __future__ import annotations

SELF_STORAGE_SLUG = "self_storage"
LGC_SLUG = "luxury_garage_condo"

# LGC-effective (Nache 2026-10-15): a garage condo is pitched as an industrial project in a
# light-industrial / warehouse / flex zone, or as a storage use where self-storage is
# allowed — so ANY of self-storage / mini-warehouse / light industrial allowed (by right OR
# by special/conditional use) makes the garage condo BY RIGHT. Order matters: NULL guard
# first so a missing matrix row yields NULL (not 'prohibited'); then permitted, then
# unclear, else prohibited. There is no 'conditional' LGC tier any more.
def lgc_verdict_sql(ss: str, mw: str, li: str, human_reviewed: str) -> str:
    """THE single LGC-viability definition, rendered over caller-supplied columns.

    Parameterised on the column expressions so every consumer generates from this one
    implementation instead of restating it (the needle metric once carried its own drifted
    copy). ``human_reviewed`` is kept in the signature for caller compatibility; it no longer
    affects the result — the Brink Rd QC veto (human storage-prohibited + LI not by right =>
    LGC prohibited) was retired 2026-10-15 by Nache's call to count every LI/storage zone.
    """
    del human_reviewed  # retired veto input; see docstring
    allowed = "('permitted', 'conditional')"
    return f"""CASE
    WHEN {ss} IS NULL AND {mw} IS NULL
         AND {li} IS NULL THEN NULL
    WHEN {ss} IN {allowed}
         OR {mw} IN {allowed}
         OR {li} IN {allowed} THEN 'permitted'
    WHEN 'unclear' IN ({ss}, {mw},
                       {li}) THEN 'unclear'
    ELSE 'prohibited'
END"""


LGC_VIABLE_VERDICTS = ("permitted", "conditional")

_LGC_VERDICT_SQL = lgc_verdict_sql(
    "zum.self_storage::text",
    "zum.mini_warehouse::text",
    "zum.light_industrial::text",
    "zum.human_reviewed",
)

# slug -> SQL expression yielding the effective permission text (or NULL).
VERDICT_SQL: dict[str, str] = {
    SELF_STORAGE_SLUG: "zum.self_storage::text",
    LGC_SLUG: _LGC_VERDICT_SQL,
}


def verdict_expr(slug: str | None) -> str:
    """SQL expression for a use-case slug; falls back to self_storage.

    An unknown slug is treated as self_storage so a mis-seeded use case can
    never silently score against nothing.
    """
    return VERDICT_SQL.get(slug or SELF_STORAGE_SLUG, VERDICT_SQL[SELF_STORAGE_SLUG])
