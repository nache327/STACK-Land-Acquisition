"""Morris Township (Morris County NJ) — self-storage Stage-4 verdicts.

Grounded in the Township of Morris Zoning, Chapter 95 Use Regulations (eCode360, curl+browser-UA
2026-07-09; DOM-anchor). asyncpg human-UPSERT (catch #29), municipality='Morris township' (matches
parcels.city EXACTLY). Catch #38: Township of Morris, MORRIS County NJ (distinct from Morristown town /
Morris Plains borough). NJ parcels spatially bound (no rebind). Idempotent.

NJ CATCH applied: self-storage / self-service storage / mini-warehouse is NAMED NOWHERE in Ch. 95 (0
occurrences); no global "self-storage prohibited unless permitted" clause; no district-specific
self-storage assignment. Warehouse-by-right convention therefore applies.

  I-21 Industrial Zone (§95-25A(5)) -> CONDITIONAL (0.72). "Wholesale business storage and warehouses"
     is a permitted use; self-storage unnamed -> warehouse-by-right convention -> conditional. 148 parcels.
  OL-5/OL-15/OL-40 Office and Research Laboratory (§95-22) -> PROHIBITED (0.80). Office/lab; warehouse
     allowed ONLY as incidental accessory (§95-22A(2), warehouse <=10% of floor area, subordinate to
     office) -> NOT warehouse-by-right principal; self-storage unnamed -> prohibited.
  B-11 Business (§95-24ff) -> PROHIBITED (0.80). Business; warehouse/self-storage not by-right -> prohibited.
  PRC Planned Research Campus -> PROHIBITED (0.80). Research/office; self-storage unnamed -> prohibited.

Armed pool = I-21 (148 parcels, conditional). OL/B/PRC prohibited. Residential (RA-*/RH-*/RB/RG/TH) +
OS/GU open-space not verdicted.

Run: python scripts/_apply_morris_twp_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Morris township"

_OL = "§95-22 Office and Research Laboratory Zone; warehouse permitted ONLY as incidental accessory (§95-22A(2), <=10% floor area, subordinate to office), not by-right principal; self-storage unnamed -> prohibited"
VERDICTS = {
    "I-21": ("conditional", "permitted", 0.72, "I-21 Industrial Zone",
             "§95-25A(5) 'Wholesale business storage and warehouses' permitted by-right; self-storage unnamed in Ch. 95 (no global prohibition, no district assignment) -> warehouse-by-right convention -> conditional"),
    "OL-5": ("prohibited", "unclear", 0.80, "OL-5 Office and Research Laboratory Zone", _OL),
    "OL-15": ("prohibited", "unclear", 0.80, "OL-15 Office and Research Laboratory Zone", _OL),
    "OL-40": ("prohibited", "unclear", 0.80, "OL-40 Office and Research Laboratory Zone", _OL),
    "B-11": ("prohibited", "unclear", 0.80, "B-11 Business Zone",
             "§95-24 Business Zone; warehouse/self-storage not permitted by-right; self-storage unnamed -> prohibited"),
    "PRC": ("prohibited", "unclear", 0.80, "Planned Research Campus Zone",
            "research/office campus; self-storage/warehouse not permitted by-right; self-storage unnamed -> prohibited"),
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
            cites = json.dumps([{"ordinance": "Township of Morris (Morris NJ) Zoning, Ch. 95",
                                 "section": cite.split(";")[0].strip()[:80],
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Morris Twp {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Morris township human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
