"""Plymouth Township (Montgomery County PA) — self-storage Stage-4 verdict.

Grounded in pasted Plymouth Zoning Appendix B, Article XIV (Limited Industrial), Section 1400
Permitted Uses. asyncpg human-UPSERT (catch #29), municipality='Plymouth Township'. Idempotent.
Catch #38: Plymouth TOWNSHIP (Montgomery County), NOT Plymouth Borough (Luzerne, Ch.231).

  LI Limited Industrial -> self_storage PERMITTED (0.97).
     Section 1400.J explicitly lists "Self-service storage facility" as a PERMITTED use (by-right,
     with development standards: 7ac min, frontage on a limited-access highway, access from minor-
     arterial+, fully enclosed, parking 1/50 units). Explicit named self-storage permission — same
     basis as Horsham I-1 §230-151.K (recurring "explicit-permitted-named" basis, NOT a new one).
     (§1400.H general warehousing/distributing is by-right but EXCLUDES personal-household storage;
     J is the operative self-storage clause.) light_industrial permitted (§1400.A-H manufacturing/
     warehousing by-right). The 19 SN-pass LI parcels arm.

ONLY LI applied — the only meaningful needle pool (19 SN-pass). HI(31 sized)/CI(20)/IP(5)/ID(7) all
0 SN-pass (rings fail wealth gate -> 0 needles even if permitted) AND not in the paste -> not verdicted.
Commercial/residential not pasted -> not verdicted.

Run: python scripts/_apply_plymouth_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Plymouth Township"

VERDICTS = {
    "LI": ("permitted", "permitted", 0.97, "LI Limited Industrial",
           "Section 1400.J 'Self-service storage facility' = PERMITTED use by-right (7ac min, limited-access-hwy frontage, minor-arterial+ access, fully enclosed, parking 1/50 units); §1400.H warehousing/distributing by-right (excl personal-household); §1400.A-H light industrial by-right. Explicit named self-storage permission"),
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
            cites = json.dumps([{"ordinance": "Plymouth Township Zoning App. B Art. XIV",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Plymouth {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Plymouth Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
