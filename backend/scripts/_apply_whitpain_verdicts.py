"""Whitpain Township (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Township of Whitpain Zoning Ordinance, Chapter 160 (eCode360, fetched via
curl+browser-UA 2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Whitpain Township'
(matches parcels.city EXACTLY — mixed case; join m.municipality=p.city is case-sensitive). Catch #38:
Township of Whitpain, Montgomery County PA (Blue Bell 19422; Ch. 160). Idempotent.

Catch #34 GIS-vs-ordinance code note: parcels carry GIS codes S-C (ordinance "SC" Shopping Center),
AR/AR-1 (ordinance "A-R"/"A-R-1"). Verdicts key to the PARCEL codes.

Ordinance facts (verbatim-verified against source HTML): self-storage is EXPLICITLY named (as a special
exception) in the I Limited Industrial district; named nowhere else. All district use lists are CLOSED
("any of the following purposes and no other").

  I  Limited Industrial (Art XXII §160-142) -> CONDITIONAL (0.90). Closed list; A "Any industrial use not
     specifically excluded" by-right, BUT §160-142.G authorizes by SPECIAL EXCEPTION (Zoning Hearing
     Board): G(3) "Warehousing, miniwarehousing, storage and ministorage facilities ...". Self-storage
     (miniwarehousing/ministorage) is EXPLICITLY NAMED as a special-exception use -> conditional
     (needle-eligible; named use, grounded — not inference). 15 parcels.
  C  Commercial (Art XIX §160-119) -> PROHIBITED (0.82). Closed list; no storage/warehouse named -> silence.
  C-1 Commercial (Art XXI §160-135) -> PROHIBITED (0.82). Closed list; no storage named -> silence.
  VC Village Commercial (Art XX §160-127) -> PROHIBITED (0.82). Closed list; no storage named -> silence.
  S-C Shopping Center (Art XXIV) -> PROHIBITED (0.82). Closed list; no storage named -> silence.
  AR  Administrative and Research (Art XVII §160-102) -> PROHIBITED (0.82). Closed list; only an outdoor-
     storage-of-fuel regulation, no self-storage use -> silence.
  AR-1 Administrative and Research (Art XVII §160-102) -> PROHIBITED (0.82). Same article/basis as AR.
  R-E Research and Engineering (Art XVIII §160-111) -> PROHIBITED (0.82). Closed list; no storage -> silence.
  IN Institutional (Art XXIII §160-157) -> PROHIBITED (0.85). Closed list; institutional; no storage -> silence.

Armed pool = I (15 parcels, conditional). Commercial/research/institutional prohibited. Residential
(R-1..R-9) self-evidently prohibited, not verdicted (not needle-relevant).

Run: python scripts/_apply_whitpain_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Whitpain Township"

VERDICTS = {
    "I": ("conditional", "permitted", 0.90, "Limited Industrial District",
          "§160-142 closed list; A 'Any industrial use not specifically excluded' by-right; §160-142.G special exceptions (Zoning Hearing Board) G(3) 'Warehousing, miniwarehousing, storage and ministorage facilities ...' -> self-storage NAMED as special exception -> conditional"),
    "C": ("prohibited", "unclear", 0.82, "Commercial District",
          "§160-119 closed list ('and no other'); no storage/warehouse/self-storage named -> silence rule"),
    "C-1": ("prohibited", "unclear", 0.82, "Commercial District (C-1)",
            "§160-135 closed list; no storage/warehouse named -> silence rule"),
    "VC": ("prohibited", "unclear", 0.82, "Village Commercial District",
           "§160-127 closed list; no storage/warehouse named -> silence rule"),
    "S-C": ("prohibited", "unclear", 0.82, "Shopping Center District",
            "Art XXIV Shopping Center use regulations, closed list; no storage/warehouse named -> silence rule"),
    "AR": ("prohibited", "unclear", 0.82, "Administrative and Research District",
           "§160-102 closed list; only an outdoor-storage-of-fuel regulation, no self-storage use named -> silence rule"),
    "AR-1": ("prohibited", "unclear", 0.82, "Administrative and Research District (A-R-1)",
             "Art XVII §160-102 (A-R/A-R-1) closed list; no self-storage use named -> silence rule"),
    "R-E": ("prohibited", "unclear", 0.82, "Research and Engineering District",
            "§160-111 closed list; no storage/warehouse named -> silence rule"),
    "IN": ("prohibited", "unclear", 0.85, "Institutional District",
           "§160-157 closed list; institutional uses; no storage/warehouse named -> silence rule"),
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
            cites = json.dumps([{"ordinance": "Township of Whitpain Zoning Ordinance, Ch. 160",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Whitpain {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Whitpain Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
