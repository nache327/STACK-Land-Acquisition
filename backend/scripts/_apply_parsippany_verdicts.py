"""Parsippany-Troy Hills Township (Morris County NJ) — self-storage Stage-4 verdicts.

Grounded in the Township of Parsippany-Troy Hills Zoning, Chapter 430 (eCode360, curl+browser-UA
2026-07-09; DOM-anchor). asyncpg human-UPSERT (catch #29), municipality='Parsippany-Troy Hills township'
(matches parcels.city EXACTLY — mixed-case with suffix). Catch #38: Township of Parsippany-Troy Hills,
MORRIS County NJ. NJ parcels spatially bound (no rebind). Idempotent.

NJ CATCH applied (batch-1 lesson): checked for (a) a global "self-storage prohibited unless specifically
permitted" clause and (b) a district-specific self-storage assignment. NEITHER exists — self-storage /
self-service storage / mini-warehouse is NAMED NOWHERE in Ch. 430 (0 occurrences across LIW-2, SED,
general district regs, chapter root, and the Zoneomics mirror). Therefore the warehouse-by-right
convention applies (warehouse permitted by-right + self-storage unnamed => self_storage conditional):

  LIW-2 Limited Industrial Wholesale (§430-162D/E) -> CONDITIONAL. "Processing, jobbing, warehousing and
     transportation facilities" + "Wholesale distribution warehouses" permitted by-right; self-storage
     unnamed -> conditional. Parcel code LIW2 (27) + LIW2/R-3 split (40).
  LIW-5 Limited Industrial Wholesale (§430-166ff) -> CONDITIONAL. Wholesale-industrial family; warehouse
     by-right, self-storage unnamed -> conditional. Parcel code LIW5 (10).
  SED-3/3A/5/5A/10 Specialized Economic Development (§430-141D/E) -> CONDITIONAL. "Processing and
     warehousing facilities for finished products" + "Digital data storage warehouses" are permitted
     principal uses; self-storage unnamed -> conditional.
  B-1/B-2/B-2A/B-3/B-3A/B-4/B-5 Business, O-1/O-3/O-S/O-T Office, ROL Research-Office-Lab -> PROHIBITED.
     Business/office districts; warehouse not permitted by-right, self-storage unnamed -> prohibited.

Armed pool = LIW2 (27) + LIW2/R-3 (40) + LIW5 (10) + SED-3 (48) + SED-3A (9) + SED-5 (50) + SED-5A (45)
+ SED-10 (21) = ~250 parcels (conditional). Residential (R-*/AHD/PRD) not verdicted.

Run: python scripts/_apply_parsippany_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Parsippany-Troy Hills township"

_LIW = "§430-162D/E warehousing + wholesale distribution warehouses permitted by-right; self-storage named nowhere in Ch. 430 (no global prohibition, no district assignment) -> warehouse-by-right convention -> conditional"
_SED = "§430-141D/E 'Processing and warehousing facilities' + 'Digital data storage warehouses' permitted principal uses; self-storage unnamed -> warehouse-by-right convention -> conditional"
_PROHIB = "business/office district; warehouse not permitted by-right and self-storage unnamed -> prohibited"
VERDICTS = {
    "LIW2": ("conditional", "permitted", 0.72, "Limited Industrial Wholesale District (LIW-2)", _LIW),
    "LIW2/R-3": ("conditional", "permitted", 0.70, "LIW-2 / R-3 split", _LIW),
    "LIW5": ("conditional", "permitted", 0.72, "Limited Industrial Wholesale District (LIW-5)", _LIW),
    "SED-3": ("conditional", "permitted", 0.72, "Specialized Economic Development District (SED-3)", _SED),
    "SED-3A": ("conditional", "permitted", 0.72, "Specialized Economic Development District (SED-3A)", _SED),
    "SED-5": ("conditional", "permitted", 0.72, "Specialized Economic Development District (SED-5)", _SED),
    "SED-5A": ("conditional", "permitted", 0.72, "Specialized Economic Development District (SED-5A)", _SED),
    "SED-10": ("conditional", "permitted", 0.72, "Specialized Economic Development District (SED-10)", _SED),
    "B-1": ("prohibited", "unclear", 0.80, "B-1 Business District", _PROHIB),
    "B-2": ("prohibited", "unclear", 0.80, "B-2 Highway Development District", _PROHIB),
    "B-2A": ("prohibited", "unclear", 0.80, "B-2A Business District", _PROHIB),
    "B-3": ("prohibited", "unclear", 0.80, "B-3 Business District", _PROHIB),
    "B-3A": ("prohibited", "unclear", 0.80, "B-3A Business District", _PROHIB),
    "B-4": ("prohibited", "unclear", 0.80, "B-4 Business District", _PROHIB),
    "B-5": ("prohibited", "unclear", 0.80, "B-5 Business District", _PROHIB),
    "O-1": ("prohibited", "unclear", 0.80, "O-1 Office District", _PROHIB),
    "O-3": ("prohibited", "unclear", 0.80, "O-3 Office District", _PROHIB),
    "O-S": ("prohibited", "unclear", 0.80, "O-S Office District", _PROHIB),
    "O-T": ("prohibited", "unclear", 0.80, "O-T Office District", _PROHIB),
    "ROL": ("prohibited", "unclear", 0.80, "Research-Office-Laboratory District", _PROHIB),
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
            cites = json.dumps([{"ordinance": "Township of Parsippany-Troy Hills (Morris NJ) Zoning, Ch. 430",
                                 "section": cite.split(";")[0].strip()[:80],
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Parsippany {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Parsippany-Troy Hills township human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:9} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
