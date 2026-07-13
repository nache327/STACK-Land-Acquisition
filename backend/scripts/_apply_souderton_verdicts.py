"""Souderton Borough (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Borough of Souderton Zoning Ordinance, Chapter 600 (updated 2024-01-05 codified PDF,
soudertonborough.org/media/2427). asyncpg human-UPSERT (catch #29),
municipality='Souderton Borough' (matches parcels.city). Catch #38: Borough of Souderton,
Montgomery County PA (Indian Valley; §600 numbering). Idempotent.

Ordinance facts (verbatim-verified against the PDF): the borough EXPRESSLY prohibits self-storage in
every commercial district it appears in — a clear legislative intent to keep warehouses out of the
commercial fabric and in the industrial district.
  - C-1 §801.D: "the following uses are expressly prohibited. 1. Storage facilities or warehouses."
  - C-2 §901.D(3): "Self-service storage facilities (mini-warehouse)" [prohibited].
  - C-3 §1901.D(4): "Self-service storage facilities (mini-warehouse)" [prohibited].

  LI  Limited Industrial (Art X) -> CONDITIONAL (0.65). §1001 open district: "used or occupied for any
     lawful industrial purposes as well as any commercial use permitted in the C-1 and C-2 Districts ...
     except that the following uses shall not be permitted:" [noxious-manufacturing exclusion list ONLY
     — abattoirs/acid/asphalt/etc]. Warehousing is a lawful industrial purpose and is NOT in the noxious
     exclusion, so warehouse is by-right; self-storage (literally "mini-warehouse" in this ordinance) is
     a warehouse type -> admissible -> conditional per the warehouse-by-right convention. The C-1/C-2/C-3
     express self-storage prohibitions push warehouses INTO LI (the industrial district), consistent with
     conditional-eligibility here. light_industrial=permitted. 6 parcels = armed pool.
  C-1 Commercial-Central Business (Art VIII) -> PROHIBITED (0.92). §801.D expressly prohibits "Storage
     facilities or warehouses."
  C-2 Limited Commercial/Residential (Art IX) -> PROHIBITED (0.95). §901.D(3) expressly prohibits
     "Self-service storage facilities (mini-warehouse)."
  C-3 Commercial-Downtown Core (Art XIX) -> PROHIBITED (0.95). §1901.D(4) expressly prohibits
     "Self-service storage facilities (mini-warehouse)."
  MUR Mixed-Use Redevelopment (Art XX) -> PROHIBITED (0.82). §2001 closed list ("for any of the following
     purposes and no other") — residential + retail/office/restaurant/hotel; no storage/warehouse named.
     Silence rule.

Armed pool = 0 (LI demoted conditional->prohibited 2026-07-09 per the inference hard gate; see VERDICTS
note + outputs/_exceptions_sessionD.md). Commercial/MUR prohibited (express + silence). Residential
(R-1/R-2/R-3) + GA garden-apartment self-evidently prohibited, not verdicted (not needle-relevant).

Run: python scripts/_apply_souderton_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Souderton Borough"

VERDICTS = {
    # DISCIPLINE CORRECTION 2026-07-09: demoted conditional->prohibited. Prior conditional rested on the
    # warehouse-by-right *inference* (convention), which cannot sit in human_reviewed. Grounded reading:
    # the ordinance NAMES self-storage ("Self-service storage facilities (mini-warehouse)") as a PROHIBITED
    # commercial use in C-1/C-2/C-3 -> it classifies self-storage as commercial. LI permits "any lawful
    # industrial purpose" + "commercial uses permitted in the C-1 and C-2 Districts" — self-storage is a
    # commercial use NOT permitted in C-1/C-2 (expressly prohibited there) and there is NO unlisted-use
    # special-exception catch-all in LI. -> self-storage not admissible in LI -> prohibited (grounded).
    # Residual "any lawful industrial purpose" ambiguity flagged in outputs/_exceptions_sessionD.md.
    "LI": ("prohibited", "permitted", 0.62, "Limited Industrial District",
           "§1001 permits 'any lawful industrial purposes as well as any commercial use permitted in the C-1 and C-2 Districts' (+ noxious-mfg exclusions); ordinance names self-storage as a PROHIBITED commercial use in C-1/C-2/C-3 -> self-storage is commercial, not permitted in C-1/C-2, and no unlisted-use SE catch-all in LI -> prohibited (named-use grounded, not warehouse-inference)"),
    "C-1": ("prohibited", "unclear", 0.92, "Commercial - Central Business District",
            "§801.D 'the following uses are expressly prohibited. 1. Storage facilities or warehouses.'"),
    "C-2": ("prohibited", "unclear", 0.95, "Limited Commercial/Residential District",
            "§901.D(3) prohibited uses expressly include 'Self-service storage facilities (mini-warehouse)'"),
    "C-3": ("prohibited", "unclear", 0.95, "Commercial - Downtown Core District",
            "§1901.D(4) prohibited uses expressly include 'Self-service storage facilities (mini-warehouse)'"),
    "MUR": ("prohibited", "unclear", 0.82, "Mixed-Use Redevelopment District",
            "§2001 closed list ('for any of the following purposes and no other'): residential + retail/office/restaurant/hotel; no storage/warehouse named -> silence rule"),
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
            cites = json.dumps([{"ordinance": "Borough of Souderton Zoning Ordinance, Ch. 600 (2024-01-05)",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Souderton {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Souderton Borough rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
