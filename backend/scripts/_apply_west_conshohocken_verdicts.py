"""West Conshohocken Borough (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in pasted West Conshohocken Zoning Ch.113: LI §113-57, HI §113-68, LC §113-51, IB §113-54.
asyncpg human-UPSERT (catch #29), municipality='West Conshohocken Borough'. Idempotent.
Catch #38: West Conshohocken Borough (Ch.113), NOT Conshohocken Borough (Ch.27, east bank).

  LI Limited Industrial -> CONDITIONAL (0.88). §113-57.G "Storage buildings and warehouses" permitted
     by-right (all uses fully enclosed); self-service storage / mini-warehouse NOT explicitly named
     -> Cresskill convention (warehouse by-right + self-storage unnamed = conditional). ("Storage
     buildings" language could support a permitted reading; conditional is the conservative call.)
  HI Heavy Industrial -> CONDITIONAL (0.88). §113-68.A all LI uses (except adult) + J "Warehouses or
     storage, open or enclosed" by-right; self-storage unnamed -> Cresskill conditional.
  LC Limited Commercial -> PROHIBITED (0.85). §113-51 retail/office/restaurant/personal-service/parking/
     residential-mixed; I "same general character" SE; no warehouse/storage/self-storage; silence rule.
  IB Interchange Business -> PROHIBITED (0.85). §113-54 traveler services/commuter parking/bus terminal/
     banks(SE)/interchange housing; no storage/self-storage; silence rule.

Armed pool = LI(10) + HI(5) = 15 (both conditional -> needle-eligible). LC/IB 0 sized (matrix completeness).
O/O-1 (office), R-1/R-2/GA (residential) not pasted -> not verdicted (silence-prohibited, 0-needle anyway).

Run: python scripts/_apply_west_conshohocken_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "West Conshohocken Borough"

VERDICTS = {
    "LI": ("conditional", "permitted", 0.88, "LI Limited Industrial",
           "§113-57.G 'Storage buildings and warehouses' permitted by-right (fully enclosed); self-service storage/mini-warehouse not explicitly named -> Cresskill convention conditional"),
    "HI": ("conditional", "permitted", 0.88, "HI Heavy Industrial",
           "§113-68.A all LI uses (except adult) + J 'Warehouses or storage, open or enclosed' by-right; self-storage unnamed -> Cresskill convention conditional"),
    "LC": ("prohibited", "unclear", 0.85, "LC Limited Commercial",
           "§113-51 retail/office/restaurant/personal-service/parking/residential-mixed; I same-general-character SE; no warehouse/storage/self-storage; silence rule"),
    "IB": ("prohibited", "unclear", 0.85, "IB Interchange Business",
           "§113-54 traveler services/commuter parking/bus terminal/banks(SE)/interchange housing; no storage/self-storage; silence rule"),
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
            cites = json.dumps([{"ordinance": "West Conshohocken Borough Zoning Ch. 113",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"West Conshohocken {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} West Conshohocken Borough rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
