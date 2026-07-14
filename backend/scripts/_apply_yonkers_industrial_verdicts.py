"""Yonkers (Westchester County NY) — self-storage verdicts, batch-2: industrial/commercial districts.

Resolves batch-1 escalation D-wc-1 (does Yonkers industrial permit self-storage?). Grounded in the
City of Yonkers Zoning Ordinance, Chapter 43 (eCode360, curl+browser-UA 2026-07-09). asyncpg
human-UPSERT (catch #29), municipality='Yonkers' (matches parcels.city EXACTLY). Idempotent.
Complements batch-1 (_apply_yonkers_verdicts.py: BR/B/BA conditional).

FINDING (verbatim-verified, catch #57 affirmative-provision): self-storage is affirmatively provided in
Yonkers ONLY via §43-36.M "Self-storage warehouse" [Added 6-12-2018], which names ONLY the BR, B and BA
Districts. The §43-27 Schedule of Use Regulations (Table 43-1) is a full use list (34 manufacturing uses)
that contains NO self-storage / self-service storage / mini-warehouse row (the only "warehousing/storage"
row is hazardous-materials warehousing); Article IV district use lists likewise name no self-storage.
=> the INDUSTRIAL and other non-BR/B/BA districts do NOT provide self-storage. Per the no-inference rule,
general manufacturing/warehousing permission in M/MG/I does NOT make self-storage conditional. -> PROHIBITED.
Catch #37: PMD = Planned Multi-Use (§43-45), not Manufacturing — also no self-storage -> prohibited.

  M   Manufacturing -> PROHIBITED (0.85). Self-storage not in §43-27 schedule; §43-36.M names only BR/B/BA.
  MG  Manufacturing General -> PROHIBITED (0.85). Same basis.
  I   Industry -> PROHIBITED (0.85). Same basis.
  PMD Planned Multi-Use (§43-45) -> PROHIBITED (0.82). Same basis (catch #37: Multi-Use, not Mfg).
  IP  Industrial -> PROHIBITED (0.82). Same basis.
  CBD Central Business -> PROHIBITED (0.82). Self-storage not provided (only BR/B/BA) -> silence.
  C   Commercial -> PROHIBITED (0.82). Same basis.
  CM  Commercial/Manufacturing -> PROHIBITED (0.82). Same basis.
  OL  Office -> PROHIBITED (0.80). Same basis.

Yonkers self-storage yield = BR/B/BA (batch-1, conditional) ONLY. Industrial/commercial here = honest
prohibited no-op. Residential (S-*/A/T) not verdicted.

Run: python scripts/_apply_yonkers_industrial_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "3e706886-919f-4ecf-b5aa-567040e295e8"  # Westchester County, NY
MUNI = "Yonkers"

_CITE = ("§43-27 Schedule of Use Regulations lists no self-storage use; §43-36.M 'Self-storage warehouse' "
         "[Added 2018] authorizes self-storage ONLY in BR/B/BA -> self-storage not affirmatively provided in this district -> prohibited (catch #57)")
VERDICTS = {
    "M": ("prohibited", "unclear", 0.85, "Manufacturing District"),
    "MG": ("prohibited", "unclear", 0.85, "Manufacturing General District"),
    "I": ("prohibited", "unclear", 0.85, "Industry District"),
    "PMD": ("prohibited", "unclear", 0.82, "Planned Multi-Use District"),
    "IP": ("prohibited", "unclear", 0.82, "Industrial District"),
    "CBD": ("prohibited", "unclear", 0.82, "Central Business District"),
    "C": ("prohibited", "unclear", 0.82, "Commercial District"),
    "CM": ("prohibited", "unclear", 0.82, "Commercial/Manufacturing District"),
    "OL": ("prohibited", "unclear", 0.80, "Office District"),
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
            cites = json.dumps([{"ordinance": "City of Yonkers Zoning Ordinance, Ch. 43",
                                 "section": "§43-27 / §43-36.M", "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {_CITE}"
            await con.execute(SQL, JID, zc, f"Yonkers {zname}", ss, li, cites, _CITE, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"Yonkers human_reviewed rows now ({len(rows)}):")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
