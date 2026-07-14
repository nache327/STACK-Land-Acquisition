"""Tarrytown (Village of Tarrytown, Westchester County NY) — self-storage verdicts (honest no-op).

Grounded in the Village of Tarrytown Zoning, Chapter 305 (eCode360, curl+browser-UA 2026-07-09).
asyncpg human-UPSERT (catch #29), municipality='Tarrytown' (matches parcels.city EXACTLY). Catch #38:
Village of Tarrytown, Westchester NY. Idempotent.

Ordinance facts (verbatim-verified across Ch. 305 — commercial Art VII, industrial Art VIII, WGBD, and
the whole chapter): self-storage / self-service storage / mini-warehouse / mini-storage is NAMED NOWHERE.
The ID Industrial District permits only generic "Warehousing, wholesaling and storage, provided that all
storage is in buildings" (§ Art VIII) — under the no-inference rule (named-use grounds a verdict; generic
warehousing/storage does NOT name the self-storage cohort), self-storage is not affirmatively provided.
-> PROHIBITED across all commercial/industrial districts. Catch #37: M-1/M-1.5/M-2/M-3/M-4 are
MULTIFAMILY RESIDENCE districts (§305-6), NOT manufacturing — not verdicted (residential).

  WGBD Waterfront General Business -> PROHIBITED (0.82). Self-storage not named -> silence.
  GB  General Business -> PROHIBITED (0.82). Self-storage not named -> silence.
  NS  Neighborhood Shopping -> PROHIBITED (0.82). Self-storage not named -> silence.
  OB  Office Building -> PROHIBITED (0.80). Self-storage not named -> silence.
  ID  Industrial -> PROHIBITED (0.80). Only generic "warehousing/storage in buildings" (no-inference);
      self-storage not named -> prohibited.
  MU  Mixed Use -> PROHIBITED (0.80). Self-storage not named -> silence.
  HC  -> PROHIBITED (0.78). Self-storage not named -> silence.
  LB  Limited Business -> PROHIBITED (0.78). Self-storage not named -> silence.

Tarrytown = honest prohibited no-op (0 self-storage needles; self-storage named nowhere in Ch. 305).
Multifamily (M-1..M-4) + residential (R-*/RR) not verdicted.

Run: python scripts/_apply_tarrytown_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Tarrytown"

_CITE = ("Ch. 305 names no self-storage/self-service-storage/mini-warehouse use; ID Industrial permits only "
         "generic 'warehousing, wholesaling and storage' (no-inference: generic storage does not name self-storage) -> self-storage not affirmatively provided -> prohibited")
VERDICTS = {
    "WGBD": ("prohibited", "unclear", 0.82, "Waterfront General Business District"),
    "GB": ("prohibited", "unclear", 0.82, "General Business District"),
    "NS": ("prohibited", "unclear", 0.82, "Neighborhood Shopping District"),
    "OB": ("prohibited", "unclear", 0.80, "Office Building District"),
    "ID": ("prohibited", "unclear", 0.80, "Industrial District"),
    "MU": ("prohibited", "unclear", 0.80, "Mixed Use District"),
    "HC": ("prohibited", "unclear", 0.78, "HC District"),
    "LB": ("prohibited", "unclear", 0.78, "Limited Business District"),
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
        for zc, (ss, li, conf, zname) in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Village of Tarrytown Zoning, Ch. 305",
                                 "section": "Art VII/VIII use regs", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"Tarrytown {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Tarrytown human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
