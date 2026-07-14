"""Boonton Town (Morris County NJ) — self-storage Stage-4 verdicts.

Grounded in the Town of Boonton Zoning and Land Use, Chapter 300 Article XXII District Regulations
(eCode360, curl+browser-UA 2026-07-09; DOM-anchor). asyncpg human-UPSERT (catch #29),
municipality='Boonton town' (matches parcels.city EXACTLY). Catch #38: TOWN of Boonton, MORRIS County NJ
(distinct from Boonton township). NJ parcels spatially bound (no rebind). Idempotent.

Ordinance facts (verbatim-verified via DOM anchors): "Self-storage facilities" is a NAMED use, listed as
a PERMITTED use in §300-110A(18)(d) — the "C-1 (Hybrid Commercial/Industrial) and C-2" district section.
It is NOT listed in the I-1 Industrial District (§300-111), which permits "Warehouses, trucking,
terminals and wholesale distribution" (§300-111A(4)) by-right. Because self-storage is a specifically
NAMED and ASSIGNED use (C-1/C-2), the warehouse-by-right convention does NOT apply to I-1 — self-storage
is prohibited where not named (affirmative-provision / expressio-unius, catch #57). No global self-storage
clause.

  C-1 Hybrid Commercial/Industrial (§300-110A(18)(d)) -> PERMITTED (0.90). "Self-storage facilities"
      permitted use. 18 parcels.
  C-2 (§300-110A(18)(d)) -> PERMITTED (0.90). §300-110 covers C-1 AND C-2 -> self-storage permitted. 49 parcels.
  I-1 Industrial (§300-111) -> PROHIBITED (0.85). Warehouse/wholesale-distribution by-right (§300-111A(4))
      but self-storage NOT listed (it is a named use assigned to C-1/C-2) -> affirmative-provision -> prohibited. 48 parcels.
  I-2 Industrial -> PROHIBITED (0.82). Self-storage not listed -> prohibited. 3 parcels.
  B-1/B-2/B-4/B-5 Business -> PROHIBITED (0.82). Self-storage not listed -> prohibited.
  ARU Adaptive Re-Use (§300-111.2) -> PROHIBITED (0.82). Self-storage not listed -> prohibited.

Armed pool = C-1 (18) + C-2 (49) = 67 parcels self-storage PERMITTED. Residential (R-*/RH) not verdicted.

Run: python scripts/_apply_boonton_town_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Boonton town"

_PROHIB = "self-storage is a NAMED use assigned to C-1/C-2 (§300-110A(18)(d)); not listed for this district -> affirmative-provision (catch #57) -> prohibited (warehouse-by-right convention does not apply when self-storage is named)"
VERDICTS = {
    "C-1": ("permitted", "permitted", 0.90, "C-1 Hybrid Commercial/Industrial District",
            "§300-110A(18)(d) 'Self-storage facilities' is a Permitted use in the C-1/C-2 district section -> self-storage permitted by-right"),
    "C-2": ("permitted", "permitted", 0.90, "C-2 District",
            "§300-110A(18)(d) 'Self-storage facilities' permitted (§300-110 covers C-1 and C-2) -> self-storage permitted by-right"),
    "I-1": ("prohibited", "permitted", 0.85, "I-1 Industrial District", _PROHIB),
    "I-2": ("prohibited", "permitted", 0.82, "I-2 Industrial District", _PROHIB),
    "B-1": ("prohibited", "unclear", 0.82, "B-1 Business District", _PROHIB),
    "B-2": ("prohibited", "unclear", 0.82, "B-2 Business District", _PROHIB),
    "B-4": ("prohibited", "unclear", 0.82, "B-4 Business District", _PROHIB),
    "B-5": ("prohibited", "unclear", 0.82, "B-5 Business District", _PROHIB),
    "C-1A": ("prohibited", "unclear", 0.80, "C-1A District", _PROHIB),
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
            cites = json.dumps([{"ordinance": "Town of Boonton (Morris NJ) Zoning & Land Use, Ch. 300",
                                 "section": cite.split(";")[0].strip()[:80],
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Boonton {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Boonton town human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
