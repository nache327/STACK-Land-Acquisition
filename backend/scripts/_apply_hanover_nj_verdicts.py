"""Hanover Township (Morris County NJ) — self-storage Stage-4 verdicts.

Grounded in the Township of Hanover Land Development Ordinance, Part 5 Zoning (Ch. 166; eCode360,
curl+browser-UA 2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Hanover township'
(matches parcels.city EXACTLY — mixed-case with suffix; the m.municipality=p.city join is
case-sensitive). Catch #38: Township of Hanover, MORRIS County NJ (Cedar Knolls/Whippany). NJ parcels
spatially bound (100% zoning_code coverage; no rebind). Idempotent.

DECISIVE GENERAL PROVISION (§166-119.2, verbatim): "Notwithstanding any other provision of this chapter,
self-service storage facilities are prohibited in all zone districts of the Township unless specifically
permitted by the zone district regulations." -> self-storage is PROHIBITED everywhere EXCEPT the districts
that specifically permit it. Only the Industrial-Business districts do (verbatim-verified via DOM anchors):
  - I-B2 §166-203.2B (Permitted uses): "Self-service storage facility."
  - I-B3 §166-203.6K (Permitted principal uses): "Self-service storage facilities."
Catch #37/#57: this explicit town-wide prohibition OVERRIDES the warehouse-by-right convention — the base
I/I-P/I-5/I-P2 districts permit "warehouse/logistics uses" by-right but §166-119.2 still prohibits
self-service storage there (self-storage is NOT specifically permitted). Reading verbatim cut a false
126-parcel warehouse-convention needle (base I) to 0.

  I-B  Industrial-Business (parcel code; = the I-B2/I-B3 industrial-business district that specifically
       permits self-service storage) -> PERMITTED (0.90). §166-203.6K / §166-203.2B. 26 parcels = armed pool.
  I-B2 Industrial-Business (§166-203.2) -> PERMITTED (0.92). §166-203.2B "Self-service storage facility"
       is a Permitted use (the §166-119.2 exception). 2 parcels = armed pool.
  I  Industrial (§166-194) -> PROHIBITED (0.90). Warehouse/logistics by-right but self-service storage NOT
     specifically permitted -> §166-119.2 prohibits. 126 parcels.
  I-P Industrial Park (§166-204) -> PROHIBITED (0.90). §166-119.2 (not specifically permitted). 32 parcels.
  I-5 Industrial (§166-207.7) -> PROHIBITED (0.90). §166-119.2. 29 parcels.
  I-P2 Industrial Park (§166-207.10) -> PROHIBITED (0.90). §166-119.2. 16 parcels.
  I-2 Industrial (§166-198) -> PROHIBITED (0.88). §166-119.2. 1 parcel.
  I-4 Industrial (§166-... ) -> PROHIBITED (0.88). §166-119.2. 1 parcel.
  I-R Industrial-Recreation (§166-... ) -> PROHIBITED (0.88). §166-119.2. 1 parcel.
  B / B-1 / BP-2 / B-P Business, O-1 Office, OB-RL/OB-RL2/OB-RL3 Office, WC, TC, D-S -> PROHIBITED (0.85).
     §166-119.2 (self-service storage not specifically permitted in these districts).

Armed pool = I-B (26) + I-B2 (2) = 28 parcels self-storage PERMITTED. All other industrial/business
prohibited by §166-119.2. Residential (R-*/RM-*) not verdicted.

Run: python scripts/_apply_hanover_nj_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Hanover township"

_PROHIB = ("§166-119.2 'Notwithstanding any other provision ... self-service storage facilities are "
           "prohibited in all zone districts ... unless specifically permitted by the zone district "
           "regulations'; self-service storage not specifically permitted in this district -> prohibited "
           "(overrides warehouse-by-right convention, catch #37/#57)")
VERDICTS = {
    "I-B": ("permitted", "permitted", 0.90, "Industrial-Business District",
            "§166-203.6K (I-B3) / §166-203.2B (I-B2) list 'Self-service storage facilit(y/ies)' as a Permitted (principal) use -> the §166-119.2 exception -> self-storage permitted by-right"),
    "I-B2": ("permitted", "permitted", 0.92, "Industrial-Business District",
             "§166-203.2B 'Self-service storage facility' under §166-203.2 Permitted uses -> self-storage permitted by-right (§166-119.2 exception)"),
    "I": ("prohibited", "permitted", 0.90, "Industrial District", _PROHIB),
    "I-P": ("prohibited", "permitted", 0.90, "Industrial Park District", _PROHIB),
    "I-5": ("prohibited", "permitted", 0.90, "I-5 Industrial District", _PROHIB),
    "I-P2": ("prohibited", "permitted", 0.90, "Industrial Park District (I-P2)", _PROHIB),
    "I-2": ("prohibited", "permitted", 0.88, "I-2 Industrial District", _PROHIB),
    "I-4": ("prohibited", "permitted", 0.88, "I-4 Industrial District", _PROHIB),
    "I-R": ("prohibited", "unclear", 0.88, "Industrial-Recreation District", _PROHIB),
    "B": ("prohibited", "unclear", 0.85, "Business District", _PROHIB),
    "B-1": ("prohibited", "unclear", 0.85, "B-1 Business District", _PROHIB),
    "BP-2": ("prohibited", "unclear", 0.85, "BP-2 Business Park District", _PROHIB),
    "B-P": ("prohibited", "unclear", 0.85, "Business Park District", _PROHIB),
    "O-1": ("prohibited", "unclear", 0.83, "O-1 Office District", _PROHIB),
    "OB-RL": ("prohibited", "unclear", 0.83, "Office Building-Research Lab District", _PROHIB),
    "OB-RL2": ("prohibited", "unclear", 0.83, "Office Building-Research Lab District (OB-RL2)", _PROHIB),
    "OB-RL3": ("prohibited", "unclear", 0.83, "Office Building-Research Lab District (OB-RL3)", _PROHIB),
    "WC": ("prohibited", "unclear", 0.83, "WC District", _PROHIB),
    "TC": ("prohibited", "unclear", 0.83, "TC District", _PROHIB),
    "D-S": ("prohibited", "unclear", 0.83, "D-S District", _PROHIB),
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
            cites = json.dumps([{"ordinance": "Township of Hanover (Morris NJ) LDO, Ch. 166 (Zoning)",
                                 "section": cite.split(";")[0].strip()[:80],
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Hanover {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Hanover township human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
