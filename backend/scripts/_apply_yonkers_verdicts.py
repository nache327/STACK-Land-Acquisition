"""Yonkers (Westchester County NY) — self-storage Stage-4 verdicts (partial: BR/B/BA).

Grounded in the City of Yonkers Zoning Ordinance, Chapter 43 (eCode360, curl+browser-UA 2026-07-09).
asyncpg human-UPSERT (catch #29), municipality='Yonkers' (matches parcels.city EXACTLY; case-sensitive
join). Catch #38: City of Yonkers, Westchester NY. NY parcels spatially bound (no rebind). Idempotent.

Ordinance facts (verbatim-verified): §43-36.M "Self-storage warehouse" [Added 6-12-2018 by G.O. No.
8-2018] affirmatively regulates self-storage warehouse in the **BR, B or BA District** — mandatory
first-story street-frontage retail liner, storage-only above, no outdoor storage (§43-36.M(1)-(8),
§43-37.B). Self-storage warehouse is thus a NAMED, standards-regulated use in BR/B/BA -> conditional
(site-plan/review). The definitive permitted-vs-special-permit and whether the industrial districts
(M/MG/I/PMD) also allow self-storage requires Table 43-1 (Schedule of Use Regulations), which is not
cleanly fetchable (per-district lists, no single HTML table) -> those escalated to _exceptions_D.md;
NOT verdicted here (do not guess the large M:4316/MG:2364/I:914 pools).

  BR (self-storage warehouse per §43-36.M) -> CONDITIONAL (0.80).
  B  (self-storage warehouse per §43-36.M) -> CONDITIONAL (0.80).
  BA (self-storage warehouse per §43-36.M) -> CONDITIONAL (0.80).

Armed pool (this partial) = BR + B + BA (conditional). Industrial M/MG/I/PMD + other commercial
DEFERRED pending Table 43-1 (see _exceptions_D.md). Residential/other not verdicted.

Run: python scripts/_apply_yonkers_verdicts.py
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

VERDICTS = {
    "BR": ("conditional", "unclear", 0.80, "BR District",
           "§43-36.M 'Self-storage warehouse' [Added 6-12-2018 G.O. 8-2018] affirmatively regulated in the BR District (first-story retail-liner + storage-only + no outdoor storage standards) -> self-storage named/allowed with site standards -> conditional"),
    "B": ("conditional", "unclear", 0.80, "B District",
          "§43-36.M 'Self-storage warehouse' affirmatively regulated in the B District (retail-liner + storage-only standards) -> conditional"),
    "BA": ("conditional", "unclear", 0.80, "BA District",
           "§43-36.M 'Self-storage warehouse' affirmatively regulated in the BA District (retail-liner + storage-only standards; §43-36.M(5) no outdoor storage in BR/BA/B) -> conditional"),
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
            cites = json.dumps([{"ordinance": "City of Yonkers Zoning Ordinance, Ch. 43",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Yonkers {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Yonkers human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
