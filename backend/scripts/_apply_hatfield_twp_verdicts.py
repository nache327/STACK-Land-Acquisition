"""Hatfield Township (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Township of Hatfield Zoning Ordinance, Chapter 282 (eCode360, fetched via
curl+browser-UA 2026-07-09; §§ amended 10-23-2024 by Ord. No. 706). asyncpg human-UPSERT
(catch #29), municipality='Hatfield Township' (matches parcels.city — mixed case; the join
m.municipality=p.city is case-sensitive, so UPPERCASE would break scoring). Catch #38:
"Township of Hatfield, PA, Montgomery County" (distinct from Hatfield Borough). Idempotent.

Ordinance facts (verbatim-verified against the source HTML): every district use section is a CLOSED
list ("...used or occupied for any of the following purposes, and no other", catch #58). Self-service
storage / self-storage / mini-warehouse is NAMED nowhere. "Warehousing" is a by-right use in LI (and
LIRC via incorporation). Commercial "storage" mentions are all either the wholesale-lumber use or
outdoor-storage/trash restrictions — never a self-storage use grant.

  LI  Light Industrial (Art XX §282-145) -> CONDITIONAL (0.72). Closed list; B "Warehousing, including
     wholesale business" by-right; F "Contractor's office and storage" + M "Yard and office for the
     storage of coal, fuel, oil, including the erection of storage facilities" by-right; O "Any use
     similar to those enumerated above ... special exception"; U "Any use not listed as a permitted use
     in any other district ... allowed in the LI ... as a special exception". Self-storage unnamed but
     warehouse by-right + SE catch-alls -> conditional (warehouse-by-right convention). 404 parcels.
  LIRC Light Industrial Restricted Commercial (Art XXI §282-154) -> CONDITIONAL (0.72). Closed list;
     A "Any use permitted in the LI Light Industrial District"; E "Flex space consisting of mix of
     office and warehousing uses" -> warehouse by-right -> self-storage conditional (same basis as LI).
     4 parcels.
  C  Commercial (Art XVII §282-121) -> PROHIBITED (0.82). Closed list; retail/office; only 'storage' is
     "(5) Wholesaling, storage and sale of lumber, plumbing and other building material" (a distinct
     wholesale-lumber use) + an outdoor-storage prohibition; no self-storage -> silence rule.
  LC Limited Commercial (Art XVIII §282-129) -> PROHIBITED (0.82). Closed list; retail; only outdoor-
     storage prohibition; no self-storage -> silence rule.
  SC Shopping Center (Art XIX §282-137) -> PROHIBITED (0.82). Closed list; retail; only outdoor-storage
     prohibition; no self-storage -> silence rule.
  LPO Limited Professional Office (Art XV §282-105) -> PROHIBITED (0.82). Closed list; dwelling/office;
     only outdoor-storage prohibition; no self-storage -> silence rule.
  IN Institutional (Art XVI §282-113) -> PROHIBITED (0.85). Closed list; hospital/religious/educational/
     municipal only; no storage -> silence rule.
  TD Transportation (Art XXXI §282-24x) -> PROHIBITED (0.80). Transit-oriented residential; no storage
     use named -> silence rule.

Armed pool = LI (404) + LIRC (4) = 408 parcels (conditional). Commercial/office/institutional/transit
prohibited. Residential (ER/RA-1/RA-2/RA-3/B/BA/BB/TH/MHD/MF-E/GA) self-evidently prohibited, not
verdicted (not needle-relevant). NB: in this ordinance B/BA/BB are RESIDENTIAL districts, not business.

Run: python scripts/_apply_hatfield_twp_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Hatfield Township"

VERDICTS = {
    "LI": ("conditional", "permitted", 0.72, "Light Industrial District",
           "§282-145 closed list ('any of the following purposes, and no other'); B 'Warehousing, including wholesale business' + F 'Contractor's office and storage' + M coal/fuel/oil storage yard by-right; O 'Any use similar ... special exception' + U 'Any use not listed as a permitted use in any other district ... allowed in the LI ... as a special exception'; self-storage unnamed -> conditional (warehouse-by-right convention)"),
    "LIRC": ("conditional", "permitted", 0.72, "Light Industrial Restricted Commercial District",
             "§282-154 closed list; A 'Any use permitted in the LI Light Industrial District'; E 'Flex space consisting of mix of office and warehousing uses' -> warehouse by-right -> self-storage conditional (same basis as LI)"),
    "C": ("prohibited", "unclear", 0.82, "Commercial District",
          "§282-121 closed list ('any of the following purposes and no other'); retail/office; only 'storage' is '(5) Wholesaling, storage and sale of lumber ... building material' + outdoor-storage prohibition; no self-storage -> silence rule"),
    "LC": ("prohibited", "unclear", 0.82, "Limited Commercial District",
           "§282-129 closed list; retail; only outdoor-storage prohibition; no self-storage -> silence rule"),
    "SC": ("prohibited", "unclear", 0.82, "Shopping Center District",
           "§282-137 closed list; retail; only outdoor-storage prohibition; no self-storage -> silence rule"),
    "LPO": ("prohibited", "unclear", 0.82, "Limited Professional Office District",
            "§282-105 closed list; single-family dwelling/professional office; only outdoor-storage prohibition; no self-storage -> silence rule"),
    "IN": ("prohibited", "unclear", 0.85, "Institutional District",
           "§282-113 closed list; hospital/religious/educational/elderly-housing/municipal only; no storage -> silence rule"),
    "TD": ("prohibited", "unclear", 0.80, "Transportation District",
           "§282-241ff transit-oriented residential district; no storage/warehouse/self-storage use named -> silence rule"),
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
            cites = json.dumps([{"ordinance": "Township of Hatfield Zoning Ordinance, Ch. 282 (Ord. 706, 2024-10-23)",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Hatfield Twp {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Hatfield Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
