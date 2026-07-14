"""Yorktown (Town of Yorktown, Westchester County NY) — self-storage Stage-4 verdicts.

Grounded in the Town of Yorktown Zoning, Chapter 300 (eCode360, curl+browser-UA 2026-07-09; §300-21
Schedule of Regulations parsed by DOM anchors + §300-79 self-storage-center regulation). asyncpg
human-UPSERT (catch #29), municipality='Yorktown' (matches parcels.city EXACTLY). Catch #38: Town of
Yorktown, Westchester NY. NY parcels spatially bound (no rebind). Idempotent.

Ordinance facts (verbatim-verified): §300-79 "Self-storage centers" — "The Planning Board may approve by
special permit the use of a site in an M-1, M-1A or M-2 District for the establishment of a self-storage
center" (dead-storage only, min 2 acres, FAR 0.6). The M-1/M-1A/M-2 names are LEGACY; the CURRENT §300-21
Schedule of Regulations places the "Self-storage center ... §300-79" use in the successor industrial
districts (DOM-verified via the schedule's district headers):
  - I-1 Light Industrial Park District -> Self-storage center by Planning Board special permit.
  - I-2 Planned Light Industrial District -> Self-storage center by Planning Board special permit.
The commercial districts (C-2 family) expressly EXCLUDE it: "Wholesale and storage uses conducted
entirely within a building, except that self-storage buildings are not permitted" (§300-21C(12)).

  I-1 Light Industrial Park (§300-21 + §300-79) -> CONDITIONAL (0.90). Self-storage center = special
      permit (Planning Board), dead-storage only, min 2ac. 22 parcels.
  I-2 Planned Light Industrial (§300-21 + §300-79) -> CONDITIONAL (0.90). Same. 33 parcels.
  C-1 -> PROHIBITED (0.82). Commercial; self-storage not permitted (schedule/silence).
  C-2 -> PROHIBITED (0.85). Wholesale/storage in-building allowed "except that self-storage buildings are
      not permitted" (§300-21C(12)) -> express exclusion.
  C-2R -> PROHIBITED (0.85). C-2 family (retail); same express exclusion basis.
  C-3 -> PROHIBITED (0.82). Commercial; self-storage not permitted.
  C-4 -> PROHIBITED (0.82). Commercial (references C-2 special uses); self-storage excluded.
  CC  -> PROHIBITED (0.82). Commercial; self-storage not permitted.
  O   -> PROHIBITED (0.80). Office; self-storage not permitted.
  OB  -> PROHIBITED (0.80). Office Building; self-storage not permitted.

Armed pool = I-1 (22) + I-2 (33) = 55 parcels (conditional, ≥2ac cap per §300-79). Commercial/office
prohibited. Residential (R1-*/RSP-*/R-2/R-3) not verdicted.

Run: python scripts/_apply_yorktown_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Yorktown"

VERDICTS = {
    "I-1": ("conditional", "permitted", 0.90, "Light Industrial Park District",
            "§300-21 schedule 'Self-storage center, to be approved by the Planning Board pursuant to §300-79'; §300-79 special permit (dead-storage only, min 2 acres) -> conditional"),
    "I-2": ("conditional", "permitted", 0.90, "Planned Light Industrial District",
            "§300-21 schedule 'Self-storage center to be approved by the Planning Board pursuant to §300-79'; §300-79 special permit (dead-storage only, min 2 acres) -> conditional"),
    "C-1": ("prohibited", "unclear", 0.82, "C-1 Commercial District",
            "§300-21 commercial; self-storage not a permitted use -> silence"),
    "C-2": ("prohibited", "unclear", 0.85, "C-2 Commercial District",
            "§300-21C(12): wholesale/storage in a building 'except that self-storage buildings are not permitted' -> express exclusion"),
    "C-2R": ("prohibited", "unclear", 0.85, "C-2R Commercial District",
             "C-2 family; §300-21 'self-storage buildings are not permitted' express exclusion"),
    "C-3": ("prohibited", "unclear", 0.82, "C-3 Commercial District",
            "§300-21 commercial; self-storage not a permitted use -> silence"),
    "C-4": ("prohibited", "unclear", 0.82, "C-4 Commercial District",
            "§300-21 commercial (references C-2 special uses); self-storage buildings not permitted"),
    "CC": ("prohibited", "unclear", 0.82, "CC Commercial District",
           "§300-21 commercial; self-storage not a permitted use -> silence"),
    "O": ("prohibited", "unclear", 0.80, "O Office District",
          "§300-21 office; self-storage not a permitted use -> silence"),
    "OB": ("prohibited", "unclear", 0.80, "OB Office Building District",
           "§300-21 office; self-storage not a permitted use -> silence"),
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
            cites = json.dumps([{"ordinance": "Town of Yorktown Zoning, Ch. 300",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Yorktown {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Yorktown human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
