"""Denville Township (Morris County NJ) — self-storage Stage-4 verdicts (honest no-op).

Grounded in the Township of Denville Land Use, Chapter 600 Part 4 Zoning (eCode360, curl+browser-UA
2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Denville township' (matches parcels.city
EXACTLY). Catch #38: Township of Denville, MORRIS County NJ. NJ parcels spatially bound (no rebind).
Idempotent.

Ordinance facts (verbatim-verified): self-storage / self-service storage / mini-warehouse is NAMED
NOWHERE in Part 4 (0 occurrences). The industrial districts use a "Primary intended use" model:
  - I-1 (§600-267): "offices ... scientific or research laboratories, industrial and manufacturing uses
    and indoor commercial recreation."
  - I-2 (§600-273): "offices ... scientific or research laboratories and industrial and manufacturing
    uses as well as anything permitted in the I-1 Zone."
Neither names WAREHOUSE/warehousing/distribution (manufacturing ≠ warehouse — no warehouse-by-right, so
the warehouse convention does NOT trigger) nor self-storage. Conditional uses (§600-279) = wireless
towers, hotels — not self-storage. -> self-storage not affirmatively provided -> PROHIBITED. Honest no-op.
0 wealth-gated needles.

  I-1 Industrial (§600-267) -> PROHIBITED (0.85). Manufacturing/office/lab; no warehouse or self-storage -> silence.
  I-2 Industrial (§600-273) -> PROHIBITED (0.85). Manufacturing/office/lab + I-1 uses; no warehouse/self-storage -> silence.
  B-1/B-2/B-2A/B-3/B-4 Business -> PROHIBITED (0.83). Self-storage not named -> silence.
  OB-1/OB-3/OB-4 Office Building -> PROHIBITED (0.83). Self-storage not named -> silence.
  C Commercial -> PROHIBITED (0.82). Self-storage not named -> silence.
  RC -> PROHIBITED (0.82). Self-storage not named -> silence.
  A-O-B -> PROHIBITED (0.82). Self-storage not named -> silence.

Residential (R-*/T-*/PARC/POS) not verdicted.

Run: python scripts/_apply_denville_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "Denville township"

_CITE = ("Ch. 600 Part 4 Zoning names no self-storage/self-service-storage/mini-warehouse; I-1/I-2 primary "
         "intended use = offices/labs/industrial-and-manufacturing (no warehouse -> no warehouse-by-right "
         "convention trigger); conditional uses = wireless/hotels. No-inference -> self-storage not "
         "affirmatively provided -> prohibited")
VERDICTS = {
    "I-1": ("prohibited", "permitted", 0.85, "I-1 Industrial District"),
    "I-2": ("prohibited", "permitted", 0.85, "I-2 Industrial District"),
    "B-1": ("prohibited", "unclear", 0.83, "B-1 Business District"),
    "B-2": ("prohibited", "unclear", 0.83, "B-2 Business District"),
    "B-2A": ("prohibited", "unclear", 0.83, "B-2A Business District"),
    "B-3": ("prohibited", "unclear", 0.83, "B-3 Business District"),
    "B-4": ("prohibited", "unclear", 0.82, "B-4 Business District"),
    "OB-1": ("prohibited", "unclear", 0.83, "OB-1 Office Building District"),
    "OB-3": ("prohibited", "unclear", 0.83, "OB-3 Office Building District"),
    "OB-4": ("prohibited", "unclear", 0.83, "OB-4 Office Building District"),
    "C": ("prohibited", "unclear", 0.82, "C Commercial District"),
    "RC": ("prohibited", "unclear", 0.82, "RC District"),
    "A-O-B": ("prohibited", "unclear", 0.82, "A-O-B District"),
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
            cites = json.dumps([{"ordinance": "Township of Denville (Morris NJ), Ch. 600 Part 4 Zoning",
                                 "section": "§600-267/§600-273 primary intended use", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"Denville {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Denville township human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
