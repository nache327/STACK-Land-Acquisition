"""Alias normalization sprint -- PROPOSE step (no parcel writes).

Generates proposals for Howard MD + Loudoun:
  - Populates `alias_mappings` table with proposals (human_reviewed=FALSE)
  - Writes scripts/alias_proposals_for_review.json so user can eyeball
    and edit
  - DOES NOT touch parcels.zoning_code -- that's the BLOCKING reviewer
    gate per the brief's Step 4

After reviewer review, flip human_reviewed=TRUE on the approved
mappings (either via SQL or by editing the JSON and re-running the
proposer with --resync-from-json), then run scripts/apply_aliases.py
to do the Strategy A parcel rewrite.

Heuristic priority (highest-confidence first):
  1. Hyphen-restore where single canonical match exists  -> 0.97
  2. Space-to-hyphen replacement                          -> 0.95
  3. Hyphen-restore with multiple candidates              -> 0.80
  4. Space removal + hyphen-restore                       -> ~0.90
  5. Suffix-strip + recurse                               -> -0.15 per
  6. Unknown                                              -> 0.00
"""
from __future__ import annotations

import asyncio, json, sys
from pathlib import Path

import asyncpg

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
JURISDICTIONS = {
    "loudoun_va": "8ebaf814-11f9-4e18-89de-d8b947660174",
    "howard_md":  "dc2d9d42-aa78-45e3-8c85-970e69a30240",
}
REVIEW_JSON = Path(__file__).parent / "alias_proposals_for_review.json"


def _hyphen_restore_candidates(alias: str) -> list[str]:
    out: set[str] = set()
    n = len(alias)
    if "-" in alias:
        return []
    for i in range(1, n):
        out.add(alias[:i] + "-" + alias[i:])
    for i in range(1, n):
        for j in range(i + 1, n):
            out.add(alias[:i] + "-" + alias[i:j] + "-" + alias[j:])
    return sorted(out)


def _space_to_hyphen(alias: str) -> list[str]:
    if " " not in alias:
        return []
    return list(dict.fromkeys([alias.replace(" ", "-"), alias.replace(" ", "")]))


def _strip_suffix(alias: str) -> list[str]:
    return [alias[:-k] for k in (1, 2, 3) if len(alias) > k]


def propose(alias: str, canonicals: set[str]):
    """Returns (canonical_code | None, alias_type, confidence, reason)."""
    if alias in canonicals:
        return (alias, "already_canonical", 1.0, "matches a canonical")
    if "-" not in alias and " " not in alias:
        cands = [c for c in _hyphen_restore_candidates(alias) if c in canonicals]
        if len(cands) == 1:
            return (cands[0], "hyphen_stripped", 0.97, "single hyphen-restore candidate matches canonical")
        if len(cands) > 1:
            cands_sorted = sorted(cands, key=lambda c: c.count("-"))
            return (cands_sorted[0], "hyphen_stripped", 0.80,
                    f"multiple hyphen-restore candidates: {cands}; chose shortest")
    if " " in alias:
        cands = [c for c in _space_to_hyphen(alias) if c in canonicals]
        if cands:
            return (cands[0], "case_variant", 0.95, "space-to-hyphen matches canonical")
        sub = propose(alias.replace(" ", ""), canonicals)
        if sub[0]:
            return (sub[0], "case_variant", max(0.0, sub[2] - 0.05),
                    f"space removed then {sub[3]}")
    for stripped in _strip_suffix(alias):
        sub = propose(stripped, canonicals)
        if sub[0]:
            return (sub[0], "truncation", max(0.0, sub[2] - 0.15),
                    f"trailing-strip '{alias[len(stripped):]}' then {sub[3]}")
    return (None, "unknown", 0.0, "no heuristic match")


async def process(conn, name, jid):
    print(f"\n=== {name} ===")
    # Canonicals = any human-reviewed zone (whatever confidence). A
    # zone like Howard MD's NT (conf=0.65, tier=needs_direct_read) is
    # still the canonical target for aliases that point at it; the
    # alias normalization doesn't care about the underlying verdict's
    # confidence, just that the target code is recognized.
    canon_rows = await conn.fetch(
        "SELECT zone_code FROM zone_use_matrix "
        "WHERE jurisdiction_id=$1::uuid AND deleted_at IS NULL "
        "AND human_reviewed=TRUE",
        jid,
    )
    canonicals = set(r["zone_code"] for r in canon_rows)
    print(f"  canonical zones (human_reviewed=TRUE): {len(canonicals)}")

    rows = await conn.fetch(
        """
        SELECT zoning_code, COUNT(*) AS n
          FROM parcels
         WHERE jurisdiction_id=$1::uuid
           AND zoning_code IS NOT NULL
           AND zoning_code NOT LIKE 'TOWNS%'
         GROUP BY zoning_code ORDER BY n DESC
        """,
        jid,
    )
    gap = [(r["zoning_code"], r["n"]) for r in rows
           if r["zoning_code"] not in canonicals]
    print(f"  parcel zone_code values NOT canonical (excl. TOWNS): {len(gap)}")

    proposals = []
    for code, n_parcels in gap:
        canonical, alias_type, conf, reason = propose(code, canonicals)
        if canonical == code:
            continue  # already canonical
        proposals.append({
            "alias_code": code,
            "canonical_code": canonical,
            "alias_type": alias_type,
            "parcel_count": n_parcels,
            "confidence": round(conf, 2),
            "reason": reason,
            "human_reviewed": False,
        })

    high = [p for p in proposals if p["canonical_code"] is not None and p["confidence"] >= 0.95]
    mid  = [p for p in proposals if p["canonical_code"] is not None and 0.70 <= p["confidence"] < 0.95]
    low  = [p for p in proposals if p["canonical_code"] is not None and p["confidence"] < 0.70]
    unknown = [p for p in proposals if p["canonical_code"] is None]
    print(f"  proposals: {len(proposals)}")
    print(f"    HIGH conf >=0.95 (mechanical hyphen-restore): {len(high)}  parcels affected: {sum(p['parcel_count'] for p in high):,}")
    print(f"    MID  conf 0.70-0.95:                          {len(mid)}   parcels affected: {sum(p['parcel_count'] for p in mid):,}")
    print(f"    LOW  conf <0.70:                              {len(low)}   parcels affected: {sum(p['parcel_count'] for p in low):,}")
    print(f"    UNKNOWN (no heuristic match):                 {len(unknown)} parcels affected: {sum(p['parcel_count'] for p in unknown):,}")

    # Upsert into alias_mappings (human_reviewed=FALSE)
    for p in proposals:
        if p["canonical_code"] is None:
            continue
        await conn.execute(
            """
            INSERT INTO alias_mappings
              (jurisdiction_id, alias_code, canonical_code, alias_type,
               parcel_count, source, confidence, notes, human_reviewed)
            VALUES ($1::uuid, $2, $3, $4, $5, 'auto_heuristic', $6, $7, FALSE)
            ON CONFLICT (jurisdiction_id, alias_code) DO UPDATE
              SET canonical_code = EXCLUDED.canonical_code,
                  alias_type     = EXCLUDED.alias_type,
                  parcel_count   = EXCLUDED.parcel_count,
                  confidence     = EXCLUDED.confidence,
                  notes          = EXCLUDED.notes
            """,
            jid, p["alias_code"], p["canonical_code"], p["alias_type"],
            p["parcel_count"], p["confidence"], p["reason"],
        )

    return {"name": name, "jid": jid, "proposals": proposals}


async def main() -> int:
    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        all_results = {}
        for name, jid in JURISDICTIONS.items():
            all_results[name] = await process(conn, name, jid)

        REVIEW_JSON.write_text(
            json.dumps(all_results, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nWrote {REVIEW_JSON}")
        print("Reviewer: edit human_reviewed=true on each approved mapping,")
        print("then run scripts/apply_aliases.py to do the parcel rewrites.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
