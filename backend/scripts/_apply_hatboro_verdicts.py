"""Hatboro Borough (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Borough of Hatboro Zoning Ordinance, Chapter 27 (eCode360, fetched via
curl+browser-UA 2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Hatboro Borough'
(matches parcels.city — mixed case; the join m.municipality=p.city is case-sensitive).
Catch #38: Borough of Hatboro, Montgomery County PA (§27 numbering). Idempotent.

Ordinance facts (verbatim-verified against source HTML): every district use section is a CLOSED list
("...for the following uses and no other", catch #58). Self-service storage / self-storage /
mini-warehouse is NAMED nowhere. LI expressly permits "Storage buildings and warehouses" by-right.
No commercial district (O/RC-1/RC-2/HB) names any storage/warehouse use.

  LI  Limited Industrial (Part 14 §27-1402) -> CONDITIONAL (0.75). Closed list; subsection J
     "Storage buildings and warehouses" by-right (also F office record storage). Self-storage
     unnamed but storage-buildings/warehouses by-right -> conditional (warehouse-by-right convention;
     confidence up for the explicit "Storage buildings" language). 86 parcels.
  HI  Heavy Industrial (Part 15 §27-1502) -> CONDITIONAL (0.75). Closed list; A(1) "All uses permitted
     in LI Limited Industrial Districts" + heavy manufacturing -> incorporates LI storage-buildings/
     warehouses by-right -> conditional (same basis as LI). 47 parcels.
  HI-MU Heavy Industrial - Mixed Use (Part 15 §27-1502) -> CONDITIONAL (0.75). Shares the HI use
     section (§27-1502 governs both HI and HI-MU) -> same basis. 17 parcels.
  O  Office (Part 10 §27-1002) -> PROHIBITED (0.82). Closed list; office uses; no storage/warehouse
     named -> silence rule.
  RC-1 Retail Commercial (Part 11 §27-1102) -> PROHIBITED (0.82). Closed list; retail; no storage
     named -> silence rule.
  RC-2 Retail Commercial (Part 12 §27-1202) -> PROHIBITED (0.82). Closed list; retail; no storage
     named -> silence rule.
  HB Highway Business (Part 13 §27-1302) -> PROHIBITED (0.82). Closed list; highway business; no
     storage named -> silence rule.

Armed pool = LI (86) + HI (47) + HI-MU (17) = 150 parcels (conditional). Commercial/office prohibited.
Residential (R-1/R-2/R-3/R-4) self-evidently prohibited, not verdicted (not needle-relevant).

Run: python scripts/_apply_hatboro_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Hatboro Borough"

VERDICTS = {
    "LI": ("conditional", "permitted", 0.75, "Limited Industrial District",
           "§27-1402.1 closed list ('following uses and no other'); subsection J 'Storage buildings and warehouses' by-right (also F office record storage); self-storage unnamed -> conditional (warehouse-by-right convention)"),
    "HI": ("conditional", "permitted", 0.75, "Heavy Industrial District",
           "§27-1502.1.A(1) 'All uses permitted in LI Limited Industrial Districts' + heavy manufacturing (closed list) -> incorporates LI 'Storage buildings and warehouses' by-right -> conditional"),
    "HI-MU": ("conditional", "permitted", 0.75, "Heavy Industrial - Mixed Use District",
              "§27-1502 governs both HI and HI-MU (closed list); incorporates all LI uses incl. 'Storage buildings and warehouses' -> conditional"),
    "O": ("prohibited", "unclear", 0.82, "Office District",
          "§27-1002 closed list ('following uses and no other'); office uses; no storage/warehouse named -> silence rule"),
    "RC-1": ("prohibited", "unclear", 0.82, "Retail Commercial District",
             "§27-1102 closed list; retail commercial; no storage/warehouse named -> silence rule"),
    "RC-2": ("prohibited", "unclear", 0.82, "Retail Commercial District",
             "§27-1202 closed list; retail commercial; no storage/warehouse named -> silence rule"),
    "HB": ("prohibited", "unclear", 0.82, "Highway Business District",
           "§27-1302 closed list; highway business; no storage/warehouse named -> silence rule"),
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
            cites = json.dumps([{"ordinance": "Borough of Hatboro Zoning Ordinance, Ch. 27",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Hatboro {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Hatboro Borough rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
