"""Horsham Township (Montgomery County PA) — self-storage Stage-4 verdicts (PROHIBITED set).

Grounded in pasted Horsham Zoning Ch. 230 residential + commercial articles (MR-1 §230-97, MR-2
§230-100, C-1 §230-103, SC-1 §230-107/121, C-2 §230-126, GC-2 §230-130). asyncpg human-UPSERT
(catch #29), municipality='Horsham Township'. Idempotent.

ALL PROHIBITED (silence rule) — none permit principal self-storage / mini-warehouse:
  MR-1 / MR-2 : residential (dwellings only) — silence.
  C-1 / SC-1 / C-2 : shopping-center / general-commercial retail+office use lists — no storage; silence.
  GC-2 : §230-130.B(6) warehouse permitted ONLY ancillary to retail/wholesale in same building; B(11)
         materials storage yard; A(7) wholesale establishment; NO principal self-storage/warehouse-by-right.
         Ancillary-only warehouse does NOT trigger the Cresskill convention (memory: not for ancillary/
         building-type mentions). B(15) "same general character" similar-use is a weak SE argument only.
         -> prohibited (silence), conf 0.83.

INDUSTRIAL (Articles XXIV-XXVII) — the catch #37 8th basis (4 treatments in one muni):
  I-1 permitted (§230-151.K explicit "Mini storage facility" by-right) — the needle zone (13 SN-pass).
  PI  conditional (§230-155.F warehouse by-right + mini-storage unnamed -> Cresskill) — (8 SN-pass).
  I-2 prohibited (§230-161.A explicit "mini storage ... shall not be permitted") — (18 SN-pass, excluded).
  I-3 prohibited (§230-165.A inherits I-2 exclusion) — (19 SN-pass, excluded).
  => real armed pool = I-1(13 permitted) + PI(8 conditional) = 21, NOT 58 (I-2+I-3 explicitly exclude self-storage).

SKIPPED: C-3 Highway Commercial — 0 parcels carry this code in Horsham (would orphan).
HELD: C-5 Limited Commercial — use list truncated in the paste (9 parcels exist; needs the §230-147 list).

Run: python scripts/_apply_horsham_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Horsham Township"

# zone -> (self_storage, light_industrial, confidence, zone_name, cite)
VERDICTS = {
    "MR-1": ("prohibited", "unclear", 0.90, "MR-1 Mixed Residential-1",
             "§230-97 permitted uses = dwellings/accessory/open-space/municipal/home-business only; no storage; residential silence rule"),
    "MR-2": ("prohibited", "unclear", 0.90, "MR-2 Mixed Residential-2",
             "§230-100 permitted uses = dwellings/townhouse/garden-apt/accessory/open-space/municipal only; no storage; residential silence rule"),
    "C-1": ("prohibited", "unclear", 0.88, "C-1 Shopping Center",
            "§230-103 retail/restaurant/personal-service/office/bank/parking; no warehouse/storage/self-storage; silence rule"),
    "SC-1": ("prohibited", "unclear", 0.88, "SC-1 Shopping Center",
             "§230-107 neighborhood-center retail/service/office; §230-121 all uses enclosed, no outdoor storage; no self-storage use; silence rule"),
    "C-2": ("prohibited", "unclear", 0.88, "C-2 General Commercial",
            "§230-126 retail(<=10k sf)/restaurant/personal-service/office/bank/parking; intent mentions wholesale but use-list omits it; no storage/self-storage; silence rule"),
    "GC-2": ("prohibited", "unclear", 0.83, "GC-2 General Commercial and Highway Commercial",
             "§230-130.B(6) warehouse ONLY ancillary to retail/wholesale in same building; B(11) materials yard; A(7) wholesale; NO principal self-storage/warehouse by-right; ancillary != Cresskill (silence rule); B(15) similar-use SE weak only"),
    # ── Industrial needle zones (Articles XXIV-XXVII) — catch #37 8th basis:
    #    same muni, four different self-storage treatments. ──
    "I-1": ("permitted", "permitted", 0.97, "I-1 Industrial",
            "§230-151.K EXPLICITLY permits 'Mini storage facility' by-right (5ac min, 500ft arterial frontage, 40ft ht, enclosed, leasing-only); §230-151.F warehouse/storage/distribution by-right. Explicit named permission = strongest basis"),
    "PI": ("conditional", "permitted", 0.85, "PI Planned Industrial",
           "§230-155.F wholesale/warehouse/storage/distribution by-right; mini-storage NOT named (I-1 lists it separately in K, so the general F 'storage center' clause does not cover mini-storage per the ordinance's own structure) -> Cresskill convention conditional"),
    "I-2": ("prohibited", "permitted", 0.95, "I-2 Industrial",
            "§230-161.A inherits I-1 uses EXCEPT 'the mini storage facility use shall not be permitted in the I-2 Industrial District' — EXPLICIT exclusion; general warehouse still by-right but self-storage explicitly prohibited"),
    "I-3": ("prohibited", "permitted", 0.92, "I-3 Industrial",
            "§230-165.A 'All uses permitted in I-2 Industrial Districts' -> inherits I-2's explicit mini-storage exclusion; self-storage prohibited"),
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
            cites = json.dumps([{"ordinance": "Horsham Township Zoning Ch. 230",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Horsham {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Horsham Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
