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

# LGC-effective: warehouse/storage by right or conditional, OR light industrial
# => LGC-viable (claim that use, take it under contract, argue the garage-condo
# entitlement with the municipality). Order matters: NULL guard first so a
# missing matrix row yields NULL (not 'prohibited'); then permitted, then
# conditional (which includes light-industrial), then unclear, else prohibited.
def lgc_verdict_sql(ss: str, mw: str, li: str, human_reviewed: str) -> str:
    """THE single LGC-viability definition, rendered over caller-supplied columns.

    Parameterised on the column expressions so every consumer generates from this one
    implementation instead of restating it. That is not stylistic: the needle metric
    (``scripts/precompute_needles._LGC_VIABLE``) carried its OWN copy, whose comment
    read "Matches services/use_verdicts._LGC_VERDICT_SQL — keep in sync" while in fact
    OMITTING the QC veto below. The result was two definitions of LGC-viable, and the
    permissive one drove the metric: Montgomery County MD reported +7,229 LGC needles
    of which 6,702 came from AR (Agricultural Reserve) and RC (Rural Cluster) — zones a
    human had marked self_storage=prohibited AND mini_warehouse=prohibited, resurrected
    solely by a stray light_industrial='conditional'. The board rejected all of them;
    only the metric was wrong. A "keep in sync" comment is not a mechanism.

    ``human_reviewed`` is an expression, not a flag, so a caller whose join already
    restricts to human-reviewed rows passes ``"true"``.
    """
    return f"""CASE
    WHEN {ss} IS NULL AND {mw} IS NULL
         AND {li} IS NULL THEN NULL
    -- QC veto (Brink Rd): a HUMAN found storage-type uses prohibited AND the zone isn't
    -- genuinely industrial (light_industrial not 'permitted') → LGC prohibited. This stops a
    -- spurious light_industrial='conditional' on an agricultural/retail zone (Montgomery AR)
    -- from resurrecting LGC, WHILE keeping real industrial zones (light_industrial='permitted':
    -- Fairfax I-2, Somerset/Monmouth Manufacturing, Montgomery IH25) garage-viable — the LGC
    -- thesis. Un-human-reviewed rows still promote below and surface as Unverified.
    WHEN {ss} = 'prohibited' AND {human_reviewed}
         AND {li} IS DISTINCT FROM 'permitted' THEN 'prohibited'
    WHEN {ss} = 'permitted'
         OR {mw} = 'permitted' THEN 'permitted'
    WHEN {ss} = 'conditional'
         OR {mw} = 'conditional'
         OR {li} IN ('permitted', 'conditional') THEN 'conditional'
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
