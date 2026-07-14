"""New Castle (Town of New Castle / Chappaqua, Westchester County NY) — self-storage verdicts (no-op).

Grounded in the Town of New Castle Zoning, Chapter 60 (eCode360; Business and Industrial Use schedule =
attachment NE0395-060d, fetched as PDF via curl+browser-UA 2026-07-09). asyncpg human-UPSERT (catch #29),
municipality='New Castle' (matches parcels.city EXACTLY). Catch #38: Town of New Castle (Chappaqua),
Westchester NY. Idempotent.

Ordinance facts (verbatim-verified against the Business and Industrial-Use schedule PDF): self-storage /
self-service storage / mini-warehouse / warehouse is NAMED NOWHERE (0 occurrences). All "storage"
references are accessory/incidental (utility structures for water/sewage storage; equipment/storage
sheds; I-P light-industry "including the storage of books, periodicals and like printed material"
incidental to manufacturing). Self-storage is not affirmatively provided in any business/industrial
district -> PROHIBITED. Ultra-wealthy Chappaqua — expected self-storage prohibition / honest no-op
(catch #52). 0 wealth-gated needles.

  B-R Retail Business -> PROHIBITED (0.82). Self-storage not named -> silence.
  I-G General Industrial -> PROHIBITED (0.80). Only incidental/utility storage; self-storage not named -> silence.
  B-RP Retail Business Planned -> PROHIBITED (0.80). Self-storage not named -> silence.
  B-RO-20 -> PROHIBITED (0.80). Self-storage not named -> silence.
  I-P Planned Industrial -> PROHIBITED (0.80). Light industry + incidental storage of printed material only;
      self-storage not named (no-inference) -> prohibited.
  B-D Business -> PROHIBITED (0.80). Self-storage not named -> silence.

Residential not verdicted.

Run: python scripts/_apply_new_castle_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "New Castle"

_CITE = ("Ch. 60 Business and Industrial Use schedule (Attachment NE0395-060d) names no self-storage/"
         "self-service-storage/mini-warehouse/warehouse (0 occurrences); only accessory/incidental storage "
         "(utility water/sewage, equipment/storage sheds, I-P incidental storage of printed material). "
         "No-inference -> self-storage not affirmatively provided -> prohibited")
VERDICTS = {
    "B-R": ("prohibited", "unclear", 0.82, "Retail Business District"),
    "I-G": ("prohibited", "permitted", 0.80, "General Industrial District"),
    "B-RP": ("prohibited", "unclear", 0.80, "Retail Business Planned District"),
    "B-RO-20": ("prohibited", "unclear", 0.80, "B-RO-20 Business District"),
    "I-P": ("prohibited", "permitted", 0.80, "Planned Industrial District"),
    "B-D": ("prohibited", "unclear", 0.80, "Business District"),
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
            cites = json.dumps([{"ordinance": "Town of New Castle Zoning, Ch. 60 (Attachment 060d Business/Industrial Use)",
                                 "section": "Business and Industrial Use schedule", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"New Castle {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} New Castle human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:8} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
