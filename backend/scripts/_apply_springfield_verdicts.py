"""Springfield Township (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Township of Springfield Zoning Ordinance, Chapter 114 (eCode360, fetched via
curl+browser-UA 2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Springfield Township'
(matches parcels.city EXACTLY — mixed case; join m.municipality=p.city is case-sensitive). Catch #38:
Township of SPRINGFIELD, MONTGOMERY County PA (offices 1510 Paper Mill Rd, Wyndmoor 19038 — DISTINCT
from Springfield Twp in Delaware Co / Bucks Co). Idempotent.

Ordinance facts (verbatim-verified against source HTML; catch #37 — read the use list, not the code name):
self-storage is EXPLICITLY named permitted in the Industrial (I) district, and is NOT named in the
Limited Industrial (LI) district — the two industrial codes diverge, so both were read verbatim.

  I  Industrial District (Art XII §114-121) -> PERMITTED (0.95). Permitted-uses closed list ("any of the
     following ... and for no other") expressly includes O "Self storage facility" (also Q "Warehouse or
     yard for storage, sale and distribution of products") by-right. Self-storage named-permitted. 47 parcels.
  LI Limited Industrial District (Art XIIC §114-12C1) -> PROHIBITED (0.80). Permitted-uses CLOSED list
     ("any of the following purposes and for no other"): offices / accessory office / contractor's office+
     enclosed storage / manufacturing / printing / utility / research / trade school. Self-storage and
     warehouse NOT named (only contractor accessory storage, C); no conditional/SE catch-all. -> self-storage
     prohibited by closed-list silence (#58 sweep). 51 parcels. (Intent mentions "warehousing" but the use
     list does not grant it — verbatim controls, catch #37.)
  B-1 B1 Business (Art IX §114-91) -> PROHIBITED (0.82). Closed list; no storage/warehouse named -> silence.
  B-2 B2 Business (Art X §114-101) -> PROHIBITED (0.82). Closed list; no storage/warehouse named -> silence.
  S  Shopping Center (Art XI §114-113) -> PROHIBITED (0.82). Closed list; no storage/warehouse named -> silence.

Armed pool = I (47 parcels, PERMITTED by-right). LI + commercial prohibited. Residential (A/AA/B/C/D/
CRD/MU/MFA) + INST institutional self-evidently prohibited, not verdicted (not needle-relevant).

Run: python scripts/_apply_springfield_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Springfield Township"

VERDICTS = {
    "I": ("permitted", "permitted", 0.95, "Industrial District",
          "§114-121 permitted-uses closed list ('any of the following ... and for no other') expressly includes O 'Self storage facility' (+ Q 'Warehouse or yard for storage, sale and distribution') by-right -> self-storage named-permitted"),
    "LI": ("prohibited", "permitted", 0.80, "Limited Industrial District",
           "§114-12C1 permitted-uses CLOSED list ('any of the following purposes and for no other'): offices/contractor-office+enclosed-storage/manufacturing/printing/utility/research/trade-school; self-storage and warehouse NOT named (only contractor accessory storage), no conditional/SE catch-all -> prohibited by closed-list silence (#58; verbatim controls over intent, catch #37)"),
    "B-1": ("prohibited", "unclear", 0.82, "B1 Business District",
            "§114-91 closed list; no storage/warehouse/self-storage named -> silence rule"),
    "B-2": ("prohibited", "unclear", 0.82, "B2 Business District",
            "§114-101 closed list; no storage/warehouse/self-storage named -> silence rule"),
    "S": ("prohibited", "unclear", 0.82, "Shopping Center District",
          "§114-113 closed list; no storage/warehouse/self-storage named -> silence rule"),
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
            cites = json.dumps([{"ordinance": "Township of Springfield Zoning Ordinance, Ch. 114",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Springfield {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Springfield Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
