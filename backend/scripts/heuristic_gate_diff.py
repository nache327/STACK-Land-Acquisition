"""
Before/after egress diff for the catch #49 heuristic-verdict gate (audit "D2").

READ-ONLY. Runs only SELECTs against the configured DB. For every parcel that
today shows a lead-visible storage verdict (self_storage in
permitted/conditional, resolved with the same municipality-preferred LATERAL
pick the real serving queries use), it reports how many WOULD be demoted by the
gate (heuristic source / low confidence / unclear) vs stay (grounded:
human_reviewed or human/llm/llm_rule/op5_factory), broken down per jurisdiction
x gate_reason x zone_class.

Flags any jurisdiction losing >50% of its lead-visible parcels — that usually
means a municipality needing a Stage-4 grounded verdict, not a scoring bug.

Usage (from backend/):  python scripts/heuristic_gate_diff.py
"""
from __future__ import annotations

import asyncio

import asyncpg

from app.config import settings
from app.services.verdict_gate import gate_reason_sql

_RO_DSN = settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
    ":6543/", ":5432/"
)

# Resolve each parcel's served verdict exactly like buybox_scoring._SELECT_PARCELS_SQL:
# municipality-preferred, NULL-municipality county fallback, newest non-deleted.
_DIFF_SQL = f"""
WITH served AS (
    SELECT
        p.id,
        p.jurisdiction_id,
        COALESCE(p.zone_class::text, 'unknown') AS zone_class,
        v.self_storage::text  AS self_storage,
        v.classification_source::text AS classification_source,
        v.confidence,
        v.human_reviewed,
        ({gate_reason_sql('v')}) AS gate_reason
    FROM parcels p
    JOIN LATERAL (
        SELECT self_storage, classification_source, confidence, human_reviewed
          FROM zone_use_matrix zum
         WHERE zum.jurisdiction_id = p.jurisdiction_id
           AND zum.zone_code = p.zoning_code
           AND (zum.municipality IS NULL OR zum.municipality = p.city)
           AND zum.deleted_at IS NULL
         ORDER BY (zum.municipality IS NULL) ASC
         LIMIT 1
    ) v ON true
    WHERE v.self_storage IN ('permitted', 'conditional')   -- lead-visible TODAY
)
SELECT
    j.name AS jurisdiction,
    served.gate_reason,
    served.zone_class,
    COUNT(*) AS lead_visible_before,
    COUNT(*) FILTER (WHERE served.gate_reason IS NOT NULL) AS gated_after
FROM served
JOIN jurisdictions j ON j.id = served.jurisdiction_id
GROUP BY j.name, served.gate_reason, served.zone_class
ORDER BY j.name, gated_after DESC
"""

_ROLLUP_SQL = f"""
WITH served AS (
    SELECT
        p.jurisdiction_id,
        ({gate_reason_sql('v')}) AS gate_reason
    FROM parcels p
    JOIN LATERAL (
        SELECT self_storage, classification_source, confidence, human_reviewed
          FROM zone_use_matrix zum
         WHERE zum.jurisdiction_id = p.jurisdiction_id
           AND zum.zone_code = p.zoning_code
           AND (zum.municipality IS NULL OR zum.municipality = p.city)
           AND zum.deleted_at IS NULL
         ORDER BY (zum.municipality IS NULL) ASC
         LIMIT 1
    ) v ON true
    WHERE v.self_storage IN ('permitted', 'conditional')
)
SELECT
    j.name AS jurisdiction,
    COUNT(*) AS lead_visible_before,
    COUNT(*) FILTER (WHERE served.gate_reason IS NOT NULL) AS gated_after,
    COUNT(*) FILTER (WHERE served.gate_reason IS NULL) AS grounded_kept
FROM served
JOIN jurisdictions j ON j.id = served.jurisdiction_id
GROUP BY j.name
HAVING COUNT(*) > 0
ORDER BY gated_after DESC
"""


async def main() -> None:
    conn = await asyncpg.connect(_RO_DSN, statement_cache_size=0, command_timeout=7200)
    try:
        await conn.execute("SET default_transaction_read_only = on")
        await conn.execute("SET statement_timeout = 0")
        rollup = await conn.fetch(_ROLLUP_SQL)
        breakdown = await conn.fetch(_DIFF_SQL)
    finally:
        await conn.close()

    tot_before = sum(r["lead_visible_before"] for r in rollup)
    tot_gated = sum(r["gated_after"] for r in rollup)
    tot_kept = sum(r["grounded_kept"] for r in rollup)
    print("=" * 78)
    print("HEURISTIC-VERDICT GATE — before/after (READ ONLY, no writes)")
    print("=" * 78)
    print(f"Lead-visible parcels today (permitted/conditional): {tot_before:,}")
    print(f"  grounded (KEPT, human/llm/factory or human_reviewed): {tot_kept:,}")
    print(f"  heuristic (WOULD BE DEMOTED to lead_eligible=false):  {tot_gated:,}")
    if tot_before:
        print(f"  demotion rate: {tot_gated / tot_before * 100:.1f}%")
    print()

    print("Per-jurisdiction (sorted by # demoted):")
    print(f"{'jurisdiction':<34}{'before':>8}{'gated':>8}{'kept':>8}{'%gated':>8}")
    print("-" * 66)
    for r in rollup:
        b, g = r["lead_visible_before"], r["gated_after"]
        pct = (g / b * 100) if b else 0
        flag = "  <-- >50% LOSS" if pct > 50 and b >= 10 else ""
        print(f"{r['jurisdiction'][:33]:<34}{b:>8,}{g:>8,}{r['grounded_kept']:>8,}{pct:>7.0f}%{flag}")

    print()
    print("Breakdown by gate_reason x zone_class (demoted only):")
    print(f"{'jurisdiction':<28}{'reason':<18}{'zone_class':<14}{'gated':>8}")
    print("-" * 68)
    for r in breakdown:
        if not r["gate_reason"]:
            continue
        print(f"{r['jurisdiction'][:27]:<28}{r['gate_reason']:<18}{r['zone_class'][:13]:<14}{r['gated_after']:>8,}")


if __name__ == "__main__":
    asyncio.run(main())
