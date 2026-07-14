"""Dobbs Ferry (Village of Dobbs Ferry, Westchester County NY) — self-storage verdicts (no-op).

Grounded in the Village of Dobbs Ferry Zoning, Chapter 300, Article X District Regulations, Use and
Area Requirements (eCode360, curl+browser-UA 2026-07-09; embedded use tables). asyncpg human-UPSERT
(catch #29), municipality='Dobbs Ferry' (matches parcels.city EXACTLY). Catch #38: Village of Dobbs
Ferry, Westchester NY. Idempotent.

Ordinance facts (verbatim-verified across Article X use tables + Article XIII Use Standards +
Definitions): self-storage / self-service storage / mini-warehouse / warehouse / storage is NAMED
NOWHERE (0 occurrences). Dobbs Ferry is an office (OF) / downtown-business (DB/B/CP) / waterfront
(WFA/WFB) / educational-institutional (EI) village; self-storage is not affirmatively provided in any
district -> PROHIBITED. Honest no-op. 0 wealth-gated needles.

  OF1/OF2/OF3/OF4/OF5/OF6 Office -> PROHIBITED (0.80). Self-storage not named -> silence.
  DB Downtown Business -> PROHIBITED (0.82). Self-storage not named -> silence.
  B Business -> PROHIBITED (0.82). Self-storage not named -> silence.
  CP -> PROHIBITED (0.80). Self-storage not named -> silence.
  WFA/WFB Waterfront -> PROHIBITED (0.80). Self-storage not named -> silence.
  EI Educational/Institutional -> PROHIBITED (0.80). Self-storage not named -> silence.

Residential not verdicted.

Run: python scripts/_apply_dobbs_ferry_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Dobbs Ferry"

_CITE = ("Ch. 300 Art X District Regulations use tables + Art XIII Use Standards + Definitions name no "
         "self-storage/self-service-storage/mini-warehouse/warehouse/storage (0 occurrences); office/"
         "downtown-business/waterfront/institutional village -> self-storage not affirmatively provided -> prohibited")
VERDICTS = {
    "OF1": ("prohibited", "unclear", 0.80, "Office District OF1"),
    "OF2": ("prohibited", "unclear", 0.80, "Office District OF2"),
    "OF3": ("prohibited", "unclear", 0.80, "Office District OF3"),
    "OF4": ("prohibited", "unclear", 0.80, "Office District OF4"),
    "OF5": ("prohibited", "unclear", 0.80, "Office District OF5"),
    "OF6": ("prohibited", "unclear", 0.80, "Office District OF6"),
    "DB": ("prohibited", "unclear", 0.82, "Downtown Business District"),
    "B": ("prohibited", "unclear", 0.82, "Business District"),
    "CP": ("prohibited", "unclear", 0.80, "CP District"),
    "WFA": ("prohibited", "unclear", 0.80, "Waterfront District A"),
    "WFB": ("prohibited", "unclear", 0.80, "Waterfront District B"),
    "EI": ("prohibited", "unclear", 0.80, "Educational/Institutional District"),
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
            cites = json.dumps([{"ordinance": "Village of Dobbs Ferry Zoning, Ch. 300 Art X",
                                 "section": "Art X District Regulations use tables", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"Dobbs Ferry {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Dobbs Ferry human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
