"""Croton-on-Hudson (Village, Westchester County NY) — self-storage verdicts (honest no-op).

Grounded in the Village of Croton-on-Hudson Zoning, Chapter 230 (eCode360; Schedule of Uses =
Attachment B, Special Permit Schedule = Attachment D, both fetched as attachment PDFs via curl+browser-UA
2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Croton-on-Hudson' (matches parcels.city
EXACTLY). Catch #38: Village of Croton-on-Hudson, Westchester NY. Idempotent.

Ordinance facts (verbatim-verified against Attachment B Schedule of Uses + Attachment D Special Permit
Schedule PDFs): self-storage / self-service storage / mini-warehouse is NAMED NOWHERE. The only
storage-type use is generic "Warehousing and wholesaling; freight distribution centers and terminals"
(§230-18). Under the no-inference rule (generic warehousing does NOT name the self-storage cohort),
self-storage is not affirmatively provided in any district -> PROHIBITED. Honest no-op.

  WDD Waterfront Development District -> PROHIBITED (0.82). Self-storage not named -> silence.
  LI  Light Industrial District -> PROHIBITED (0.80). Only generic warehousing/wholesaling/freight named
      (§230-18); self-storage not named (no-inference) -> prohibited.
  C-1 Commercial -> PROHIBITED (0.82). Self-storage not named -> silence.
  C-2 Commercial -> PROHIBITED (0.82). Self-storage not named -> silence.
  WC  Waterfront Commercial -> PROHIBITED (0.80). Self-storage not named -> silence.
  O-1 Office -> PROHIBITED (0.80). Self-storage not named -> silence.

Croton = honest prohibited no-op (0 self-storage needles). Residential (RA/PRE-*) not verdicted.

Run: python scripts/_apply_croton_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Croton-on-Hudson"

_CITE = ("Ch. 230 Schedule of Uses (Attachment B) + Special Permit Schedule (Attachment D) name no "
         "self-storage/self-service-storage/mini-warehouse; only generic 'Warehousing, wholesaling, freight "
         "distribution' (§230-18); no-inference -> self-storage not affirmatively provided -> prohibited")
VERDICTS = {
    "WDD": ("prohibited", "unclear", 0.82, "Waterfront Development District"),
    "LI": ("prohibited", "permitted", 0.80, "Light Industrial District"),
    "C-1": ("prohibited", "unclear", 0.82, "C-1 Commercial District"),
    "C-2": ("prohibited", "unclear", 0.82, "C-2 Commercial District"),
    "WC": ("prohibited", "unclear", 0.80, "Waterfront Commercial District"),
    "O-1": ("prohibited", "unclear", 0.80, "O-1 Office District"),
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
            cites = json.dumps([{"ordinance": "Village of Croton-on-Hudson Zoning, Ch. 230 (Attach. B/D)",
                                 "section": "§230-18 Schedule of Uses", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"Croton {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Croton-on-Hudson human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
