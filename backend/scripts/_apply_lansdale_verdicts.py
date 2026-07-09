"""Lansdale Borough (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Borough of Lansdale Zoning Ordinance, Chapter 405 (2018 codified PDF,
https://www.lansdale.org/DocumentCenter/View/89/Zoning-Code-2018-PDF). asyncpg human-UPSERT
(catch #29), municipality='Lansdale Borough' (matches parcels.city). Catch #38: Borough of
Lansdale, Montgomery County PA (§405 numbering, boro districts A/B/C/I). Idempotent.

Ordinance facts (verbatim-verified against the PDF):
  - "self-storage facility" appears ONLY inside the definition of DEAD STORAGE (§405-201, Added
    2002) and in two RESTRICTIVE clauses (basement dead-storage only; no dead storage in parking
    areas). It is NAMED AS A PERMITTED USE IN NO DISTRICT. "warehouse" is not a defined term and
    appears as a standalone permitted use in no district. → self-storage is never by-right.
  - Every district's permitted-use list is a CLOSED list ("...used for any of the following
    uses and for no other", catch #58 closed-list clause).

  I  Industrial (Art XV) -> CONDITIONAL (0.70). §405-1500 closed permitted list (mfg A-K, storage
     garage=motor-vehicles-only per §405-201 def, gas/auto, hotel, office, senior center, med-mj,
     forestry) does NOT name self-storage. §405-1501 conditional = day-care only. BUT §405-1503.D
     special-exception catch-all: "Any other trade, industry or use, excluding any residential use
     or child day-care facility, that will be no more injurious, hazardous, noxious or offensive
     than those listed herein." Self-storage is a low-impact 'use' clearly no more injurious than
     the listed freight yards / machine shops / gas stations / petroleum-SE -> admissible by
     special exception -> conditional (needle-eligible). Same basis as Whitemarsh LIM §116-144.A(21).
     light_industrial=permitted (mfg by-right). 196 parcels.
  COMM Commercial (Art XI) -> PROHIBITED (0.82). §405-1100 closed permitted list (Class C Res uses,
     apartments-over-commercial, retail/service); no storage/warehouse/self-storage named -> silence
     rule under closed list.
  BUSINESS Business (Art XII) -> PROHIBITED (0.82). §405-1200 closed permitted list (Commercial uses
     + wholesale stores, hotels, general merchandise, wholesale-jobbing office/display <25% making).
     Only 'storage' is "wholesale storage and sale of lumber/building supplies" (a special-exception
     use, elsewhere specifically prohibited) -> NOT self-storage. Silence rule.
  B-2 Business (B-2) (Art XIII) -> PROHIBITED (0.80). §405-1300 Main-Street mixed-use district built
     on the Business District uses; no self-storage/warehouse named. Silence rule. (4 parcels.)
  BPO Business Park Overlay (Art XIV) -> PROHIBITED (0.80). §405-1403.C: "Storage activities and
     warehouse facilities are permitted only as part of a primary activity, shall be located in the
     same building as the permitted primary use, and shall comprise less than 20% of the activity's
     floor spaces." -> storage is ACCESSORY-only (<20%), standalone self-storage not permitted.

Armed pool = I (196 parcels, conditional). Commercial/Business/BPO prohibited (self-storage never
named; closed lists). Residential (A/B/C/APT) + PO districts self-evidently prohibited, not verdicted
(not needle-relevant; matches Whitemarsh needle-focused scope).

Run: python scripts/_apply_lansdale_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Lansdale Borough"

VERDICTS = {
    "I": ("conditional", "permitted", 0.70, "Industrial District",
          "§405-1500 closed permitted list ('any of the following uses and for no other') does not name self-storage/warehouse (storage garage=motor vehicles only per §405-201); §405-1501 conditional=day-care only; §405-1503.D special-exception catch-all 'any other trade, industry or use ... no more injurious, hazardous, noxious or offensive than those listed herein' admits self-storage by special exception -> conditional"),
    "COMM": ("prohibited", "unclear", 0.82, "Commercial District",
             "§405-1100 closed permitted list ('for any of the following purposes and for no other'): Class C Residential uses + apartments-over-commercial + retail/service; no storage/warehouse/self-storage named -> silence rule"),
    "BUSINESS": ("prohibited", "unclear", 0.82, "Business District",
                 "§405-1200 closed permitted list ('for any of the following purposes and for no other'): Commercial uses + wholesale stores/hotels/general merchandise/wholesale-jobbing display; only 'storage' is wholesale-lumber-and-building-supplies (special exception, elsewhere prohibited) not self-storage -> silence rule"),
    "B-2": ("prohibited", "unclear", 0.80, "Business (B-2) District",
            "§405-1300 Main-Street mixed-use district built on the Business District use set; no self-storage/warehouse named -> silence rule"),
    "BPO": ("prohibited", "unclear", 0.80, "Business Park Overlay District",
            "§405-1403.C 'Storage activities and warehouse facilities are permitted only as part of a primary activity, ... same building as the permitted primary use, and shall comprise less than 20% of the activity's floor spaces' -> storage accessory-only, standalone self-storage not permitted"),
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
            cites = json.dumps([{"ordinance": "Borough of Lansdale Zoning Ordinance, Ch. 405",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Lansdale {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Lansdale Borough rows:")
        for r in rows:
            print(f"  {r['zone_code']:9} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
