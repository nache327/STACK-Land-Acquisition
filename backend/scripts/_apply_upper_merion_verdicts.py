"""Upper Merion Township (Montgomery County PA) — self-storage Stage-4 verdicts.

Grounded in pasted Upper Merion Zoning Ch. 165: Commercial Districts Att.2 (Table CD.1),
LI §165-144, HI §165-153. Muni-specific municipality='Upper Merion Township' (catch #28).
asyncpg human-UPSERT (catch #29 — NOT factory_safe_write). Idempotent.

CODE RECONCILIATION (catch #34): the township ordinance labels Neighborhood/Limited/General
Commercial as NC/LC/GC, but the montcopa GIS layer — the source of parcels.zoning_code, which the
scoring join matches on — encodes them with reversed letters: CN (Commercial Neighborhood) = ord. NC,
CL (Commercial Limited) = ord. LC, CG (Commercial General) = ord. GC. Verdicts are therefore keyed to
the GIS codes CN/CL/CG (+ SC/LI/HI exact). Confirmed against the official district list 2026-06-29.

  HI  Heavy Industrial (§165-153) -> self_storage PERMITTED (0.90). Catch-all clause: "a lot may be
      used or occupied for any lawful purpose not elsewhere in this article prohibited." Self-storage
      not excluded in §165-153.A and not in the §165-153.C special-exception (noxious) list. catch #37:
      6th distinct verdict-basis = HI CATCH-ALL by-right (strongest basis — future use additions inherit).
  LI  Limited Industrial (§165-144) -> self_storage CONDITIONAL (0.92). §165-144.B permits wholesaling/
      warehousing/distributing/storage by-right; self-storage unnamed -> Cresskill convention; §165-144.F
      similar-use special-exception path. light_industrial permitted.
  SC  Shopping Center / CN (ord NC) / CL (ord LC) / CG (ord GC) -> self_storage PROHIBITED (0.88).
      Table CD.1 (165 Attachment 2) silence rule — no warehouse/warehousing/storage/self-storage/
      mini-warehouse anywhere in the commercial use table.

KPMU applied 2026-06-29 from the Table KPMU 1 paste (explicit "Mini storage NP" -> self_storage prohibited).
HELD (NOT in the paste — surfaced, not applied): SM/SM-1 (Suburban Metropolitan, KoP core), C-O
(Commercial Office), NMU (Neighborhood Mixed Use), AR/A-R (Admin & Research), CA (Court Approved).
HIR overlay (§165-153.E) + data-center conditional uses (§165-144.K /
§165-153.I) noted, not applied (overlay / tangential to thesis).

Run: python scripts/_apply_upper_merion_verdicts.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from app.config import settings

JID = "a59d956d-5f67-4c39-aef1-36140bd57c6f"  # Montgomery County, PA
MUNI = "Upper Merion Township"

# GIS zone_code -> (self_storage, light_industrial, confidence, zone_name, cite)
VERDICTS = {
    "HI": ("permitted", "permitted", 0.90, "HI Heavy Industrial",
           "§165-153 catch-all: 'any lawful purpose not elsewhere in this article prohibited'; self-storage not excluded (§165-153.A) and not in §165-153.C special-exception list"),
    "LI": ("conditional", "permitted", 0.92, "LI Limited Industrial",
           "§165-144.B wholesaling/warehousing/distributing/storage by-right; self-storage unnamed -> Cresskill convention; §165-144.F similar-use special exception"),
    "SC": ("prohibited", "unclear", 0.88, "SC Shopping Center",
           "Table CD.1 (165 Attachment 2) silence rule — no warehouse/storage/self-storage in commercial use table"),
    "CN": ("prohibited", "unclear", 0.88, "CN Commercial Neighborhood (ordinance NC)",
           "Table CD.1 (165 Attachment 2) silence rule; GIS code CN = ordinance NC Neighborhood Commercial (catch #34 reconciliation)"),
    "CL": ("prohibited", "unclear", 0.88, "CL Commercial Limited (ordinance LC)",
           "Table CD.1 (165 Attachment 2) silence rule; GIS code CL = ordinance LC Limited Commercial (catch #34 reconciliation)"),
    "CG": ("prohibited", "unclear", 0.88, "CG Commercial General (ordinance GC)",
           "Table CD.1 (165 Attachment 2) silence rule; GIS code CG = ordinance GC General Commercial (catch #34 reconciliation)"),
    "KPMU": ("prohibited", "permitted", 0.95, "KPMU King of Prussia Mixed-Use",
             "§165-160.2 Table KPMU 1 Warehousing: 'Mini storage NP' EXPLICIT not-permitted (ordinance distinguishes general warehousing P2,3 from mini-storage NP); light manufacturing/warehousing P2 -> light_industrial permitted. catch #37 7th basis = EXPLICIT mini-storage prohibition"),
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
            cites = json.dumps([{"ordinance": "Upper Merion Township Zoning Ch. 165",
                                 "section": cite.split(";")[0].strip(),
                                 "basis": f"self_storage={ss} in {zc} ({zname})"}])
            note = f"{zc} ({zname}): self_storage {ss}. {cite}"
            await con.execute(SQL, JID, zc, f"Upper Merion {zname}", ss, li, cites, cite, MUNI, conf, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, light_industrial::text li, confidence, human_reviewed hr "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL "
            "ORDER BY self_storage, zone_code", JID, MUNI)
        print(f"applied {len(rows)} Upper Merion Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} light_ind={r['li']:10} conf={r['confidence']} hr={r['hr']}")
    finally:
        await con.close()


asyncio.run(main())
