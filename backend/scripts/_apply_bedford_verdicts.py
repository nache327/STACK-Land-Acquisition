"""Bedford (Town of Bedford, Westchester County NY) — self-storage verdicts (honest no-op).

Grounded in the Town of Bedford Zoning, Chapter 125 (eCode360; Schedule of Use Regulations - Principal
Uses = attachment 125b, Special Permit Uses = 125d, both fetched as PDFs via curl+browser-UA 2026-07-09).
asyncpg human-UPSERT (catch #29), municipality='Bedford' (matches parcels.city EXACTLY). Catch #38: Town
of Bedford, Westchester NY. Idempotent. Ch.125 closed-list rule: "only those uses listed for each
district as being permitted shall be permitted."

Ordinance facts (verbatim-verified against the Principal Uses + Special Permit Uses schedule PDFs):
self-storage / self-service storage / mini-warehouse is NAMED NOWHERE. The LI district's only storage-
type principal use is generic "Wholesale business, storage or warehouse" (P) + "Outdoor storage of
commercial and industrial vehicles..." — under the no-inference rule (generic storage/warehouse does NOT
name the self-storage cohort), self-storage is not affirmatively provided. Special Permit Uses schedule
names no self-storage either. -> PROHIBITED across all non-residential districts. Very-high-wealth town
(Bedford/Katonah) but self-storage narrowly-not-zoned -> honest no-op (catch #52). 0 wealth-gated needles.

  LI Light Industrial -> PROHIBITED (0.80). Only generic "Wholesale business, storage or warehouse" (P);
     self-storage not named (no-inference) -> prohibited.
  CB Central Business -> PROHIBITED (0.82). Self-storage not named -> silence.
  NB Neighborhood Business -> PROHIBITED (0.82). Self-storage not named -> silence.
  PB-O Planned Business-Office -> PROHIBITED (0.80). Self-storage not named -> silence.
  PB-R Planned Business -> PROHIBITED (0.80). Self-storage not named -> silence.
  PB-O(K) Planned Business-Office (Katonah) -> PROHIBITED (0.80). Self-storage not named -> silence.

Residential (acre-based districts) not verdicted.

Run: python scripts/_apply_bedford_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Bedford"

_CITE = ("Ch. 125 Schedule of Use Regulations (Principal Uses 125b + Special Permit Uses 125d) names no "
         "self-storage/self-service-storage/mini-warehouse; LI only lists generic 'Wholesale business, "
         "storage or warehouse'. No-inference -> self-storage not affirmatively provided -> prohibited")
VERDICTS = {
    "LI": ("prohibited", "permitted", 0.80, "Light Industrial District"),
    "CB": ("prohibited", "unclear", 0.82, "Central Business District"),
    "NB": ("prohibited", "unclear", 0.82, "Neighborhood Business District"),
    "PB-O": ("prohibited", "unclear", 0.80, "Planned Business-Office District"),
    "PB-R": ("prohibited", "unclear", 0.80, "Planned Business District"),
    "PB-O(K)": ("prohibited", "unclear", 0.80, "Planned Business-Office (Katonah) District"),
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
            cites = json.dumps([{"ordinance": "Town of Bedford Zoning, Ch. 125 (Attach. 125b/125d Use Schedules)",
                                 "section": "Schedule of Use Regulations", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"Bedford {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Bedford human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:8} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
