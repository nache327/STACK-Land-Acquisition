"""Municipality of Norristown (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Municipality of Norristown Zoning Ordinance, Chapter 320 (April 2016 codified PDF,
norristown.gov DocumentCenter/View/1690). asyncpg human-UPSERT (catch #29),
municipality='Municipality of Norristown' (matches parcels.city). Catch #38: Municipality of
Norristown, Montgomery County PA (§320; districts LIMU/HI/TC). Idempotent.

Ordinance facts (verbatim-verified against the PDF): every district USE REGULATION is a CLOSED list
("...used or occupied by any of the following uses and no other", catch #58). "Mini storage
facilities" and "Warehousing and storage" are NAMED only in LIMU (and HI via incorporation). No
commercial/mixed/institutional district names storage/warehouse/mini-storage anywhere (full-doc
verified). Self-Storage Facility carries an off-street-parking standard (Art XXVI) confirming the
code recognizes the use.

  LI-MU  Limited Industrial Mixed Use (Art XV) -> PERMITTED (0.95). §320-151.A Class I permitted uses
     (closed, 'and no other') expressly names #11 "Mini storage facilities" AND #19 "Warehousing and
     storage" by-right. Self-storage permitted by-right. 125 parcels = armed pool.
  HI  Heavy Industrial (Art XVI) -> PERMITTED (0.95). §320-161.A permitted uses = "any of the following
     uses OR those uses not expressly permitted elsewhere" and A(1) "All uses permitted in the LI-MU
     District except ... special exception" -> incorporates LIMU mini-storage/warehousing by-right +
     open catch-all. Self-storage permitted. 3 parcels = armed pool.
  IN  Institutional (Art XVII) -> PROHIBITED (0.85). §320-171.A closed list, institutional purposes;
     no storage/warehouse/self-storage named. Silence rule.
  MS-MU Main Street Mixed Use (Art VI) -> PROHIBITED (0.82). §320-56 closed list; no storage. Silence.
  N-C  Neighborhood Commercial (Art VIII) -> PROHIBITED (0.82). §320-76 closed list; no storage. Silence.
  C-R  Commercial Retail (Art IX) -> PROHIBITED (0.82). §320-86 closed list; no storage. Silence.
  OR  Office-Residential (Art X) -> PROHIBITED (0.82). closed list; no storage. Silence.
  OCR  Office-Commercial-Retail (Art XI) -> PROHIBITED (0.82). §320-106 closed list; no storage. Silence.
  DR  Downtown Riverfront (Art XII) -> PROHIBITED (0.80). §320-116 closed list; no storage. Silence.
  TC  Town Center (Art XIII) -> PROHIBITED (0.80). §320-129 closed list; no storage. Silence.
  TC-II Town Center II (Art XIV) -> PROHIBITED (0.80). §320-141 closed list; no storage. Silence.

Armed pool = LI-MU (125) + HI (3) = 128 parcels self-storage PERMITTED. Residential (R-1/R-2/MR/RE)
self-evidently prohibited, not verdicted (not needle-relevant).

Run: python scripts/_apply_norristown_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Municipality of Norristown"

VERDICTS = {
    "LI-MU": ("permitted", "permitted", 0.95, "Limited Industrial Mixed Use District",
              "§320-151.A Class I permitted uses (closed list 'any of the following uses and no other') expressly names #11 'Mini storage facilities' and #19 'Warehousing and storage' by-right"),
    "HI": ("permitted", "permitted", 0.95, "Heavy Industrial District",
           "§320-161.A permitted uses = 'any of the following uses or those uses not expressly permitted elsewhere'; A(1) incorporates all LI-MU uses (incl. mini storage + warehousing) except special-exception -> self-storage by-right"),
    "IN": ("prohibited", "unclear", 0.85, "Institutional District",
           "§320-171.A closed list ('and no other'), institutional purposes; no storage/warehouse/self-storage named -> silence rule"),
    "MS-MU": ("prohibited", "unclear", 0.82, "Main Street Mixed Use District",
              "§320-56 USE REGULATION closed list ('and no other'); no storage/warehouse/mini-storage named -> silence rule"),
    "N-C": ("prohibited", "unclear", 0.82, "Neighborhood Commercial District",
            "§320-76 USE REGULATION closed list ('and no other'); no storage named -> silence rule"),
    "C-R": ("prohibited", "unclear", 0.82, "Commercial Retail District",
            "§320-86 USE REGULATION closed list ('and no other'); no storage named -> silence rule"),
    "OR": ("prohibited", "unclear", 0.82, "Office-Residential District",
           "Art X USE REGULATION closed list ('and no other'); no storage named -> silence rule"),
    "OCR": ("prohibited", "unclear", 0.82, "Office-Commercial-Retail District",
            "§320-106 USE REGULATION closed list ('and no other'); no storage named -> silence rule"),
    "DR": ("prohibited", "unclear", 0.80, "Downtown Riverfront District",
           "§320-116 USE REGULATION closed list ('and no other'); no storage named -> silence rule"),
    "TC": ("prohibited", "unclear", 0.80, "Town Center District",
           "§320-129 USE REGULATION closed list ('and no other'); no storage named -> silence rule"),
    "TC-II": ("prohibited", "unclear", 0.80, "Town Center II District",
              "§320-141 USE REGULATION closed list ('and no other'); no storage named -> silence rule"),
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
            cites = json.dumps([{"ordinance": "Municipality of Norristown Zoning Ordinance, Ch. 320",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Norristown {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Municipality of Norristown rows:")
        for r in rows:
            print(f"  {r['zone_code']:7} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
