"""East Hanover Township (Morris County NJ) — self-storage Stage-4 verdicts.

Grounded in the Township of East Hanover Zoning, Chapter 95 Article VII (eCode360, curl+browser-UA
2026-07-09; DOM-anchor). asyncpg human-UPSERT (catch #29), municipality='East Hanover township'
(matches parcels.city EXACTLY — mixed-case with suffix). Catch #38: Township of East Hanover, MORRIS
County NJ. NJ parcels spatially bound (100% coverage, no rebind). Idempotent.

Ordinance facts (verbatim-verified via DOM anchors): "Self-storage facilities" is NAMED exactly once —
§95-59A(1)(j), under the PERMITTED USES of the "Light Industry I-3 Zone" (§95-59). Self-storage is
affirmatively provided ONLY in I-3; it is not listed for any other district (catch #57
affirmative-provision) -> prohibited elsewhere.

  I-3 Light Industry (§95-59A(1)(j)) -> PERMITTED (0.92). "Self-storage facilities" is a permitted
      principal use. 128 parcels = the armed pool.
  I-1 Light Industry -> PROHIBITED (0.83). Self-storage not listed for I-1 (only I-3) -> affirmative-
      provision -> prohibited. 21 parcels.
  B-1 Business -> PROHIBITED (0.83). Self-storage not listed -> prohibited.
  B-2 Business -> PROHIBITED (0.83). Self-storage not listed -> prohibited.
  B-2B Business -> PROHIBITED (0.82). Self-storage not listed -> prohibited.
  PB-1/PB-2/PB-3 Planned Business -> PROHIBITED (0.82). Self-storage not listed -> prohibited.
  SED -> PROHIBITED (0.82). Self-storage not listed -> prohibited.
  HD-OCI -> PROHIBITED (0.80). Self-storage not listed -> prohibited.

Armed pool = I-3 (128 parcels, PERMITTED by-right). Residential (R-*/RAH/SFA) not verdicted.

Run: python scripts/_apply_east_hanover_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "746b7604-f362-470f-aa42-70dc8973b4ee"  # Morris County, NJ
MUNI = "East Hanover township"

_PROHIB = "self-storage is a specifically-listed I-3 permitted use (§95-59A(1)(j)); not listed for this district -> affirmative-provision (catch #57) -> prohibited"
VERDICTS = {
    "I-3": ("permitted", "permitted", 0.92, "Light Industry I-3 Zone",
            "§95-59A(1)(j) 'Self-storage facilities' is a Permitted (principal) use in the Light Industry I-3 Zone -> self-storage permitted by-right"),
    "I-1": ("prohibited", "permitted", 0.83, "Light Industry I-1 Zone", _PROHIB),
    "B-1": ("prohibited", "unclear", 0.83, "B-1 Business Zone", _PROHIB),
    "B-2": ("prohibited", "unclear", 0.83, "B-2 Business Zone", _PROHIB),
    "B-2B": ("prohibited", "unclear", 0.82, "B-2B Business Zone", _PROHIB),
    "PB-1": ("prohibited", "unclear", 0.82, "PB-1 Planned Business Zone", _PROHIB),
    "PB-2": ("prohibited", "unclear", 0.82, "PB-2 Planned Business Zone", _PROHIB),
    "PB-3": ("prohibited", "unclear", 0.82, "PB-3 Planned Business Zone", _PROHIB),
    "SED": ("prohibited", "unclear", 0.82, "SED Zone", _PROHIB),
    "HD-OCI": ("prohibited", "unclear", 0.80, "HD-OCI Zone", _PROHIB),
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
            cites = json.dumps([{"ordinance": "Township of East Hanover (Morris NJ) Zoning, Ch. 95 Art VII",
                                 "section": cite.split(";")[0].strip()[:80],
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"East Hanover {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL AND human_reviewed ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} East Hanover township human_reviewed rows:")
        for r in rows:
            print(f"  {r['zone_code']:7} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
