"""Rye Brook (Village of Rye Brook, Westchester County NY) — self-storage verdicts (honest no-op).

Grounded in the Village of Rye Brook Zoning, Chapter 250 (eCode360, curl+browser-UA 2026-07-09;
§250 Schedule of Regulations use matrix — 18 tables — + definitions). asyncpg human-UPSERT (catch #29),
municipality='Rye Brook' (matches parcels.city EXACTLY). Catch #38: Village of Rye Brook, Westchester NY.
Idempotent.

Ordinance facts (verbatim-verified): the Schedule of Regulations use matrix names NO self-storage /
self-service storage / mini-warehouse / warehouse use (0 occurrences across 18 use tables). "Storage"
appears only in RESTRICTIONS/accessory contexts (utility buildings "not including material storage
yards"; "no parking or storage of commercial vehicles"; "no storage permitted on the premises of
non-office [uses]"). Rye Brook is an office-campus (OB) + PUD + residential village; self-storage is not
affirmatively provided in any district -> PROHIBITED. Honest no-op. 0 wealth-gated needles.

  OB-1 Office Building -> PROHIBITED (0.82). Self-storage not a listed use -> silence.
  OB-2 Office Building -> PROHIBITED (0.82). Same basis.
  OB-3 Office Building -> PROHIBITED (0.80). Same basis.
  OB-S Office Building -> PROHIBITED (0.80). Same basis.
  C1  Commercial -> PROHIBITED (0.82). Self-storage not a listed use -> silence.
  C1-P Commercial Planned -> PROHIBITED (0.80). Same basis.
  H-1 -> PROHIBITED (0.78). Self-storage not a listed use -> silence.

Residential + PUD not verdicted.

Run: python scripts/_apply_rye_brook_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Rye Brook"

_CITE = ("Ch. 250 Schedule of Regulations use matrix names no self-storage/self-service-storage/mini-"
         "warehouse/warehouse use (0 occurrences); 'storage' only in restrictions (no storage on non-office "
         "premises; no material storage yards). No-inference -> self-storage not affirmatively provided -> prohibited")
VERDICTS = {
    "OB-1": ("prohibited", "unclear", 0.82, "Office Building District"),
    "OB-2": ("prohibited", "unclear", 0.82, "Office Building District"),
    "OB-3": ("prohibited", "unclear", 0.80, "Office Building District"),
    "OB-S": ("prohibited", "unclear", 0.80, "Office Building District"),
    "C1": ("prohibited", "unclear", 0.82, "C1 Commercial District"),
    "C1-P": ("prohibited", "unclear", 0.80, "C1-P Commercial District"),
    "H-1": ("prohibited", "unclear", 0.78, "H-1 District"),
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
            cites = json.dumps([{"ordinance": "Village of Rye Brook Zoning, Ch. 250 (Schedule of Regulations)",
                                 "section": "Schedule of Regulations use matrix", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"Rye Brook {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Rye Brook human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
