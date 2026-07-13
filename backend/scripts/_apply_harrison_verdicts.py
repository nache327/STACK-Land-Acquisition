"""Harrison (Town/Village of Harrison, Westchester County NY) — self-storage verdicts (honest no-op).

Grounded in the Town/Village of Harrison Zoning, Chapter 235, Business Districts Table of Use
Regulations (§235 Attachment 3, eCode360 attachment PDF, fetched via curl+browser-UA 2026-07-09).
asyncpg human-UPSERT (catch #29), municipality='Harrison' (matches parcels.city EXACTLY). Catch #38:
Town/Village of Harrison, Westchester NY. Idempotent.

Ordinance facts (verbatim-verified against the Table of Use-Business attachment): self-storage /
self-service storage / mini-warehouse is NOT a listed use in any Harrison business district. The only
storage-type row is "Equipment storage building" (X in nearly all districts, P in one) — a distinct use,
not self-storage. Under the closed use table (unlisted use = prohibited), self-storage is prohibited
across Harrison's business districts. Ultra-wealthy residential town (Purchase) — expected self-storage
prohibition / honest no-op (catch #52). 0 wealth-gated needles.

  SB-0 Special Business (§235 Attach.3) -> PROHIBITED (0.82). Self-storage not a listed use -> silence.
  B  Business (§235 Attach.3) -> PROHIBITED (0.82). Self-storage not a listed use -> silence.
  PB Professional Business (§235 Attach.3) -> PROHIBITED (0.80). Self-storage not a listed use -> silence.

Residential (R-1/R-2/R-2.5/R-75/GA) self-evidently prohibited, not verdicted.

Run: python scripts/_apply_harrison_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Harrison"

VERDICTS = {
    "SB-0": ("prohibited", "unclear", 0.82, "Special Business District",
             "§235 Attachment 3 Business Districts Table of Use Regulations; self-storage/mini-warehouse not a listed use (only 'Equipment storage building', a distinct use) -> closed-table silence -> prohibited"),
    "B": ("prohibited", "unclear", 0.82, "Business District",
          "§235 Attachment 3 Table of Use Regulations; self-storage not a listed use -> closed-table silence -> prohibited"),
    "PB": ("prohibited", "unclear", 0.80, "Professional Business District",
           "§235 Attachment 3 Table of Use Regulations; self-storage not a listed use -> closed-table silence -> prohibited"),
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
            cites = json.dumps([{"ordinance": "Town/Village of Harrison Zoning, Ch. 235 Attach. 3 (Business Use Table)",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Harrison {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Harrison human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
