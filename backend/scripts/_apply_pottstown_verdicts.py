"""Pottstown Borough (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Borough of Pottstown Zoning Ordinance, Chapter 27 Part 3 (eCode360, fetched via
curl+browser-UA 2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Pottstown Borough'
(matches parcels.city — mixed case; the join m.municipality=p.city is case-sensitive). Catch #38:
Borough of Pottstown, Montgomery County PA (form-based hybrid code; Keystone Opportunity Zone).
Idempotent.

District-code decode (§300 chart): Conservation {NR Neighborhood Residential, TTN Traditional Town
Neighborhood, D Downtown}; Gateway {NB Neighborhood Business, DG Downtown Gateway, GE Gateway East,
GW Gateway West, P Park}; Contemporary {FO Flex-Office, HB Highway Business, HM Heavy Manufacturing}.

Ordinance facts (verbatim-verified against source HTML): storage/warehouse is a permitted use ONLY in
FO, HB, HM (mapped across all of Part 3). "Rental storage" (= self-storage) is expressly permitted in
HB. Districts carry a conditional catch-all "Uses of the same general character ... same or lesser
impact ... as determined by Borough Council" (not a self-storage grant for retail/office/residential
districts).

  HB Highway Business (§337) -> PERMITTED (0.85). Permitted Uses expressly include "Rental storage"
     (renting of storage units = self-storage) AND "Warehouse" by-right. Self-storage named-permitted.
     24 parcels = armed pool.
  HM Heavy Manufacturing (§338) -> CONDITIONAL (0.72). Permitted Uses A-H closed enumerated; H
     "Warehouse" by-right (+ G utility storage); self-storage unnamed -> conditional (warehouse-by-right
     convention). 48 parcels = armed pool.
  FO Flex-Office (§336) -> CONDITIONAL (0.72). Permitted Uses include "Warehouse" + "Outdoor storage"
     + light/medium manufacturing by-right; self-storage unnamed -> conditional (warehouse-by-right).
     122 parcels = armed pool.
  D  Downtown (§320) -> PROHIBITED (0.72). Retail/office/residential permitted uses; no storage/warehouse;
     conditional catch-all is "same general character" only (self-storage not same character) -> prohibited.
  DG Downtown Gateway (§333) -> PROHIBITED (0.72). Retail/office/apartment/light-mfg<20k; no storage.
  GE Gateway East (§334) -> PROHIBITED (0.72). No storage/warehouse permitted use.
  GW Gateway West (§334) -> PROHIBITED (0.72). No storage/warehouse permitted use.
  NB Neighborhood Business (§332) -> PROHIBITED (0.72). No storage/warehouse permitted use.
  P  Park (§335) -> PROHIBITED (0.80). Recreational; no storage.

Armed pool = HB (24 permitted) + HM (48 conditional) + FO (122 conditional) = 194 parcels. Downtown/
Gateway/Park prohibited. Residential (NR/TTN) self-evidently prohibited, not verdicted.

Run: python scripts/_apply_pottstown_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Pottstown Borough"

VERDICTS = {
    "HB": ("permitted", "unclear", 0.85, "Highway Business District",
           "§337 Permitted Uses expressly include 'Rental storage' (renting of storage units = self-storage) and 'Warehouse' by-right -> self-storage named-permitted"),
    "HM": ("conditional", "permitted", 0.72, "Heavy Manufacturing District",
           "§338 Permitted Uses A-H (closed enumerated); H 'Warehouse' by-right + G utility storage; self-storage unnamed -> conditional (warehouse-by-right convention)"),
    "FO": ("conditional", "permitted", 0.72, "Flex-Office District",
           "§336 Permitted Uses include 'Warehouse' + 'Outdoor storage' + light/medium manufacturing by-right; self-storage unnamed -> conditional (warehouse-by-right convention)"),
    "D": ("prohibited", "unclear", 0.72, "Downtown District",
          "§320 retail/office/residential permitted uses; no storage/warehouse; conditional catch-all limited to 'same general character' (self-storage not same character) -> prohibited"),
    "DG": ("prohibited", "unclear", 0.72, "Downtown Gateway District",
           "§333 retail/office/apartment/light-mfg<20k permitted; no storage/warehouse named -> prohibited"),
    "GE": ("prohibited", "unclear", 0.72, "Gateway East District",
           "§334 permitted uses; no storage/warehouse named -> prohibited"),
    "GW": ("prohibited", "unclear", 0.72, "Gateway West District",
           "§334 permitted uses; no storage/warehouse named -> prohibited"),
    "NB": ("prohibited", "unclear", 0.72, "Neighborhood Business District",
           "§332 permitted uses; no storage/warehouse named -> prohibited"),
    "P": ("prohibited", "unclear", 0.80, "Park District",
          "§335 recreational/park permitted uses; no storage/warehouse named -> prohibited"),
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
            cites = json.dumps([{"ordinance": "Borough of Pottstown Zoning Ordinance, Ch. 27 Part 3",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Pottstown {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Pottstown Borough rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
