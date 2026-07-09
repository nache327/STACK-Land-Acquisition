"""Bridgeport Borough (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Borough of Bridgeport Zoning Ordinance, Chapter 560 (CURRENT post-rewrite text;
Ord. 2025-002 adopted 11-11-2025 + Ord. 2026-003 amend; eCode360, fetched via curl+browser-UA
2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Bridgeport Borough' (matches parcels.city
— mixed case; the join m.municipality=p.city is case-sensitive). Catch #38: Borough of Bridgeport,
Montgomery County PA (§560). Idempotent.

VERSION-MISMATCH CHECK (queue D5 caution — Hudson pattern) RESOLVED: the parcel zone codes
(OS/R1/R2/R3/INS/NC/GC/LIC/GIC/MUR/TO) MATCH the current Ch. 560 district scheme 1:1 (§560-402
enumeration: OS, R1, R2, R3, INS, NC, GC, LIC, GIC, MUR, TOD; parcel 'TO' = TOD). Parcels carry the
CURRENT (post-2025-rewrite) scheme, NOT a stale pre-rewrite one -> safe to ground.

Ordinance facts (verbatim-verified against source HTML): "Storage facility (self-service)" is an
EXPRESSLY NAMED use — by-right in LIC/GIC, special-exception/conditional in GC.

  LIC Light Industrial Commercial (Art XII §560-1202) -> PERMITTED (0.95). "Uses permitted by right"
     enumeration includes "(u) Storage facility (self-service)". Self-storage named by-right. 50 parcels.
  GIC General Industrial Commercial (Art XIII §560-1302) -> PERMITTED (0.95). "Uses permitted by right"
     includes "(u) Storage facility (self-service)". Self-storage named by-right. 1 parcel.
  GC General Commercial (Art XI §560-1102) -> CONDITIONAL (0.90). Under "special exception or conditional
     principal use", "(5) Storage facility (self-service)". Self-storage named as SE/conditional. 31 parcels.
  NC Neighborhood Commercial (Art X §560-1002) -> PROHIBITED (0.82). Permitted-use list names no
     storage/warehouse/self-storage -> silence rule. 358 parcels.
  MUR Mixed-Use Riverfront (Art XIV §560-1402) -> PROHIBITED (0.80). Only accessory outdoor storage;
     no self-storage principal use -> silence rule. 32 parcels.

Armed pool = LIC (50 permitted) + GIC (1 permitted) + GC (31 conditional) = 82 parcels. NC/MUR
prohibited. Residential (R1/R2/R3), INS, OS, TOD self-evidently non-storage, not verdicted.

Run: python scripts/_apply_bridgeport_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Bridgeport Borough"

VERDICTS = {
    "LIC": ("permitted", "permitted", 0.95, "Light Industrial Commercial District",
            "§560-1202 'Uses permitted by right' enumeration includes '(u) Storage facility (self-service)' -> self-storage named by-right"),
    "GIC": ("permitted", "permitted", 0.95, "General Industrial Commercial District",
            "§560-1302 'Uses permitted by right' enumeration includes '(u) Storage facility (self-service)' -> self-storage named by-right"),
    "GC": ("conditional", "unclear", 0.90, "General Commercial District",
           "§560-1102 'special exception or conditional principal use' list includes '(5) Storage facility (self-service)' -> self-storage named as conditional/special-exception"),
    "NC": ("prohibited", "unclear", 0.82, "Neighborhood Commercial District",
           "§560-1002 permitted-use list names no storage/warehouse/self-storage -> silence rule"),
    "MUR": ("prohibited", "unclear", 0.80, "Mixed-Use Riverfront District",
            "§560-1402 only accessory outdoor storage/waste disposal; no self-storage principal use named -> silence rule"),
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
            cites = json.dumps([{"ordinance": "Borough of Bridgeport Zoning Ordinance, Ch. 560 (Ord. 2025-002, current)",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Bridgeport {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Bridgeport Borough rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
