"""Lincoln Park Borough (Morris County NJ) — self-storage Stage-4 verdicts.

Grounded in the Borough of Lincoln Park Zoning, Chapter 28 Article XVIII Industrial Zones (eCode360,
curl+browser-UA 2026-07-09; DOM-anchor). asyncpg human-UPSERT (catch #29), municipality='Lincoln Park
borough' (matches parcels.city EXACTLY). Catch #38: Borough of Lincoln Park, MORRIS County NJ. NJ
parcels spatially bound (no rebind). Idempotent.

NJ CATCH applied: self-storage / self-service storage / mini-warehouse is NAMED NOWHERE in Ch. 28 (0
occurrences in Art XVIII Industrial Zones); no global "self-storage prohibited unless permitted" clause;
no district-specific self-storage assignment. Warehouse-by-right convention applies.

  I Industrial (§28-18.4A(1)) -> CONDITIONAL (0.72). "All industrial uses are permitted" (incl.
     warehousing) by-right; self-storage unnamed -> warehouse-by-right convention -> conditional. 49 parcels.
  TI Transitional Industrial (§28-18.2A(6)) -> CONDITIONAL (0.72). "Warehouses" permitted by-right;
     self-storage unnamed -> conditional. 35 parcels.
  PI Planned Industrial (§28-18.3) -> CONDITIONAL (0.68). Planned industrial (industrial/warehouse uses);
     self-storage unnamed -> conditional. 3 parcels.
  CR / B-1 / B-2 / B-3 / O/R / LB -> PROHIBITED (0.80). Commercial/office; warehouse not by-right,
     self-storage unnamed -> prohibited.

Armed pool = I (49) + TI (35) + PI (3) = 87 parcels (conditional). Residential (R-*/TH/PRD) + GAR not verdicted.

Run: python scripts/_apply_lincoln_park_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Lincoln Park borough"

_PROHIB = "commercial/office district; warehouse not permitted by-right and self-storage unnamed -> prohibited"
VERDICTS = {
    "I": ("conditional", "permitted", 0.72, "I Industrial Zone",
          "§28-18.4A(1) 'All industrial uses are permitted' (incl. warehousing) by-right; self-storage named nowhere in Ch. 28 (no global prohibition, no district assignment) -> warehouse-by-right convention -> conditional"),
    "TI": ("conditional", "permitted", 0.72, "TI Transitional Industrial Zone",
           "§28-18.2A(6) 'Warehouses' permitted by-right; self-storage unnamed -> warehouse-by-right convention -> conditional"),
    "PI": ("conditional", "permitted", 0.68, "PI Planned Industrial Zone",
           "§28-18.3 Planned Industrial (industrial/warehouse uses); self-storage unnamed -> warehouse-by-right convention -> conditional"),
    "CR": ("prohibited", "unclear", 0.80, "CR Commercial District", _PROHIB),
    "B-1": ("prohibited", "unclear", 0.80, "B-1 Business District", _PROHIB),
    "B-2": ("prohibited", "unclear", 0.80, "B-2 Business District", _PROHIB),
    "B-3": ("prohibited", "unclear", 0.80, "B-3 Business District", _PROHIB),
    "O/R": ("prohibited", "unclear", 0.80, "O/R Office-Residential District", _PROHIB),
    "LB": ("prohibited", "unclear", 0.80, "LB Limited Business District", _PROHIB),
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
            cites = json.dumps([{"ordinance": "Borough of Lincoln Park (Morris NJ) Zoning, Ch. 28 Art XVIII",
                                 "section": cite.split(";")[0].strip()[:80],
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Lincoln Park {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Lincoln Park borough human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
