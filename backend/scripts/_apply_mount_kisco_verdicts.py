"""Mount Kisco (Town/Village of Mount Kisco, Westchester County NY) — self-storage verdicts (no-op).

Grounded in the Town/Village of Mount Kisco Zoning, Chapter 110, Article III District Regulations
(eCode360, curl+browser-UA 2026-07-09; 71-table use regs). asyncpg human-UPSERT (catch #29),
municipality='Mount Kisco' (matches parcels.city EXACTLY). Catch #38: Town/Village of Mount Kisco,
Westchester NY. Idempotent.

Ordinance facts (verbatim-verified across Article III District Regulations): self-storage / self-service
storage / mini-warehouse is NAMED NOWHERE (0 occurrences). "Warehouse" appears only generically —
"Wholesale, indoor storage and warehousing establishments" (a general warehousing use in a service/
light-industrial district) and "Indoor storage facilities incidental to the principal use" (accessory).
Under the no-inference rule, generic warehousing/indoor-storage does NOT name the self-storage cohort ->
self-storage not affirmatively provided -> PROHIBITED. Honest no-op. 0 wealth-gated needles.

  GC General Commercial -> PROHIBITED (0.82). Self-storage not named -> silence.
  CD Commercial -> PROHIBITED (0.82). Self-storage not named -> silence.
  CD-2 Commercial -> PROHIBITED (0.80). Self-storage not named -> silence.
  CL Commercial Limited -> PROHIBITED (0.82). Self-storage not named -> silence.
  CB-1 Central Business -> PROHIBITED (0.82). Self-storage not named -> silence.
  OG Office -> PROHIBITED (0.80). Self-storage not named -> silence.
  SC Shopping Center -> PROHIBITED (0.80). Self-storage not named -> silence.

Residential (GR etc.) not verdicted.

Run: python scripts/_apply_mount_kisco_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Mount Kisco"

_CITE = ("Ch. 110 Art III District Regulations name no self-storage/self-service-storage/mini-warehouse; "
         "'warehouse' only generic ('Wholesale, indoor storage and warehousing establishments'; accessory "
         "'indoor storage facilities'). No-inference -> self-storage not affirmatively provided -> prohibited")
VERDICTS = {
    "GC": ("prohibited", "unclear", 0.82, "General Commercial District"),
    "CD": ("prohibited", "unclear", 0.82, "Commercial District"),
    "CD-2": ("prohibited", "unclear", 0.80, "Commercial District (CD-2)"),
    "CL": ("prohibited", "unclear", 0.82, "Commercial Limited District"),
    "CB-1": ("prohibited", "unclear", 0.82, "Central Business District"),
    "OG": ("prohibited", "unclear", 0.80, "Office District"),
    "SC": ("prohibited", "unclear", 0.80, "Shopping Center District"),
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
            cites = json.dumps([{"ordinance": "Town/Village of Mount Kisco Zoning, Ch. 110 Art III",
                                 "section": "Art III District Regulations", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"Mount Kisco {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Mount Kisco human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
