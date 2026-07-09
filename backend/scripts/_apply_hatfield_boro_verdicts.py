"""Hatfield Borough (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in the Borough of Hatfield Zoning Ordinance, Chapter 27 (eCode360, fetched via
curl+browser-UA 2026-07-09). asyncpg human-UPSERT (catch #29), municipality='Hatfield Borough'
(matches parcels.city — mixed case; the join m.municipality=p.city is case-sensitive). Catch #38:
Borough of Hatfield, Montgomery County PA (DISTINCT from Hatfield Township — different ordinance,
different codes: boro uses I/C/CC, twp uses LI/LIRC). Idempotent.

Ordinance facts (verbatim-verified against source HTML): self-storage is EXPRESSLY NAMED — permitted
by-right in the Industrial district and specifically prohibited in Core Commercial.

  I  Industrial (Part 18 §27-1802) -> PERMITTED (0.95). §27-1802.1 permitted uses expressly include
     N "Self-storage developments" AND F "Warehouse, storage, or distribution center" AND G
     "Contractor's office and storage" by-right. Self-storage named-permitted. 60 parcels = armed pool.
  CC Core Commercial (Part 21 §27-2106) -> PROHIBITED (0.95). §27-2106.1 Specifically Prohibited Uses:
     "I. Self-storage units." (also E warehousing/distribution/truck-terminal, H outdoor truck storage).
     Silence clause present ("If a use is not listed as allowed ... shall be considered to be
     prohibited"). Self-storage expressly prohibited. 86 parcels.
  C  Commercial (Part 17 §27-1702) -> PROHIBITED (0.75). Permitted-use list omits self-storage (only
     fireworks-storage / accessory / outdoor-storage restrictions); borough interpretive rule (§27-2106
     "if a use is not listed as allowed ... prohibited") -> self-storage not listed -> prohibited. 33 parcels.

Armed pool = I (60 parcels, PERMITTED by-right — the only Montgomery-PA muni to date with self-storage
NAMED as a by-right use). CC/C prohibited. Residential (R-1/R-2/R-3/R-4/A) self-evidently prohibited,
not verdicted (not needle-relevant).

Run: python scripts/_apply_hatfield_boro_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Hatfield Borough"

VERDICTS = {
    "I": ("permitted", "permitted", 0.95, "Industrial District",
          "§27-1802.1 permitted uses expressly include N 'Self-storage developments' + F 'Warehouse, storage, or distribution center' + G 'Contractor's office and storage' by-right -> self-storage named-permitted"),
    "CC": ("prohibited", "unclear", 0.95, "Core Commercial District",
           "§27-2106.1 Specifically Prohibited Uses: 'I. Self-storage units.' (also E warehousing/distribution/truck-terminal); silence clause 'if a use is not listed as allowed ... prohibited' -> self-storage expressly prohibited"),
    "C": ("prohibited", "unclear", 0.75, "Commercial District",
          "§27-1702 permitted-use list omits self-storage (only fireworks-storage/accessory/outdoor-storage restrictions); borough rule §27-2106 'if a use is not listed as allowed ... prohibited' -> self-storage not listed -> prohibited"),
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
            cites = json.dumps([{"ordinance": "Borough of Hatfield Zoning Ordinance, Ch. 27",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Hatfield Boro {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Hatfield Borough rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
