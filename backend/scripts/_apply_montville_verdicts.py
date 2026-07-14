"""Montville Township (Morris County NJ) — self-storage Stage-4 verdicts.

Grounded in the Township of Montville Land Use & Development, Chapter 230 Part 4 Zoning (eCode360,
curl+browser-UA 2026-07-09; §230-173 Self-storage facilities conditional-use section, DOM-anchor).
asyncpg human-UPSERT (catch #29), municipality='Montville township' (matches parcels.city EXACTLY —
mixed-case with suffix). Catch #38: Township of Montville, MORRIS County NJ. NJ parcels spatially bound
(100% coverage, no rebind). Idempotent.

Ordinance facts (verbatim-verified via DOM anchors): self-storage is a NAMED CONDITIONAL use, assigned
by §230-173 "Self-storage facilities" to specific zones ONLY:
  - §230-173A: "For self-storage facilities in the B-5 and I-1B Zones ..." (conditions).
  - §230-173B: "For self-storage facilities in the OB-2A and OB-4 Zones ..." (conditions).
  - §230-149 / §230-173.1: "Self-storage facilities in OB-5 Office Building District" (conditional use).
Self-storage is thus permitted (as a conditional use) ONLY in B-5, I-1B, OB-2A, OB-4, OB-5. It is NOT
listed for the other industrial districts (I-1A, I-2, I-2A) -> those are PROHIBITED (self-storage is a
specifically-assigned named use; affirmative-provision / catch #57 — not extended by generic warehouse).

  I-1B Industrial (§230-173A) -> CONDITIONAL (0.88). Self-storage facilities conditional use. 9 parcels.
  OB-2A Office Building (§230-173B) -> CONDITIONAL (0.88). Self-storage facilities conditional use. 27 parcels.
  B-5 Business (§230-173A) -> CONDITIONAL (0.85). Self-storage facilities conditional use. 2 parcels.
  OB-4 Office Building (§230-173B) -> CONDITIONAL (0.85). Conditional use (0 parcels; documentation).
  OB-5 Office Building (§230-149/§230-173.1) -> CONDITIONAL (0.85). Conditional use (0 parcels; documentation).
  I-1A Industrial -> PROHIBITED (0.85). Self-storage not assigned to I-1A (only B-5/I-1B/OB-2A/OB-4/OB-5). 60 parcels.
  I-2 Industrial -> PROHIBITED (0.85). Self-storage not assigned to I-2. 55 parcels.
  I-2A Industrial -> PROHIBITED (0.85). Self-storage not assigned to I-2A. 13 parcels.
  OB-1/OB-1A/OB-2B/OB-3 Office -> PROHIBITED (0.83). Self-storage not assigned to these.
  B-1/B-2/B-3/B-4/B-6 Business -> PROHIBITED (0.83). Self-storage not assigned (only B-5).
  TC1/TC2 Town Center -> PROHIBITED (0.82). Self-storage not assigned.

Armed pool = I-1B (9) + OB-2A (27) + B-5 (2) = 38 parcels (conditional). Residential (R-*/AH-*/PURD) not verdicted.

Run: python scripts/_apply_montville_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Montville township"

_COND_AB = "§230-173A self-storage facilities conditional use (B-5 and I-1B Zones)"
_COND_B = "§230-173B self-storage facilities conditional use (OB-2A and OB-4 Zones)"
_COND_OB5 = "§230-149 / §230-173.1 self-storage facilities conditional use in OB-5"
_PROHIB = "§230-173 assigns self-storage (conditional) ONLY to B-5/I-1B/OB-2A/OB-4/OB-5; not assigned to this district -> prohibited (affirmative-provision, catch #57)"
VERDICTS = {
    "I-1B": ("conditional", "permitted", 0.88, "Industrial District (I-1B)", _COND_AB),
    "OB-2A": ("conditional", "unclear", 0.88, "Office Building District (OB-2A)", _COND_B),
    "B-5": ("conditional", "unclear", 0.85, "Business District (B-5)", _COND_AB),
    "OB-4": ("conditional", "unclear", 0.85, "Office Building District (OB-4)", _COND_B),
    "OB-5": ("conditional", "unclear", 0.85, "Office Building District (OB-5)", _COND_OB5),
    "I-1A": ("prohibited", "permitted", 0.85, "Industrial District (I-1A)", _PROHIB),
    "I-2": ("prohibited", "permitted", 0.85, "Industrial District (I-2)", _PROHIB),
    "I-2A": ("prohibited", "permitted", 0.85, "Industrial District (I-2A)", _PROHIB),
    "OB-1": ("prohibited", "unclear", 0.83, "Office Building District (OB-1)", _PROHIB),
    "OB-1A": ("prohibited", "unclear", 0.83, "Office Building District (OB-1A)", _PROHIB),
    "OB-2B": ("prohibited", "unclear", 0.83, "Office Building District (OB-2B)", _PROHIB),
    "OB-3": ("prohibited", "unclear", 0.83, "Office Building District (OB-3)", _PROHIB),
    "B-1": ("prohibited", "unclear", 0.83, "Business District (B-1)", _PROHIB),
    "B-2": ("prohibited", "unclear", 0.83, "Business District (B-2)", _PROHIB),
    "B-3": ("prohibited", "unclear", 0.83, "Business District (B-3)", _PROHIB),
    "B-4": ("prohibited", "unclear", 0.83, "Business District (B-4)", _PROHIB),
    "B-6": ("prohibited", "unclear", 0.82, "Business District (B-6)", _PROHIB),
    "TC1": ("prohibited", "unclear", 0.82, "Town Center District (TC1)", _PROHIB),
    "TC2": ("prohibited", "unclear", 0.82, "Town Center District (TC2)", _PROHIB),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$8,$4::use_permission_enum,$4::use_permission_enum,
  $5::use_permission_enum,'unclear',$6::jsonb,$7,$9,true,'human',$10,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, citations=EXCLUDED.citations,
  cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = settings.database_url.replace(":6543/", ":5432/").replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='90s'")
        for zc, (ss, li, conf, zname, cite) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Township of Montville (Morris NJ), Ch. 230 Part 4 Zoning",
                                 "section": cite.split(";")[0].strip()[:80],
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Montville {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Montville township human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
