"""Fairfax County VA — I-3 self_storage verdict (verbatim-grounded from zMOD).

Fairfax County Zoning Ordinance (zMOD, adopted 2021), Use Table 4101.1 + §4102.6.C Self-Storage
use standards. Footnote 341 (verbatim): "Self-Storage carries forward 'mini-warehousing
establishment,' except the use is changed from SE to allowed, subject to conditions, in the I-3
District." → self_storage permitted (county-default, municipality=NULL) over the prior heuristic row.

This is the ONE verbatim-citable verdict from the zMOD use table; the remaining 25 needle-candidate
zones (I-4/I-5/I-6/C-*/PDC/...) are HELD in _fairfax_va_sprint_scope.md pending a visual confirm of
the diagonal-header use-table matrix (pdftotext flattens the per-district P/SE markers ambiguously;
pdftoppm unavailable to render). Reverse-direction discipline (#13): ON CONFLICT DO UPDATE.
Run: python scripts/_apply_fairfax_i3.py
"""
import asyncio
import json

import asyncpg

FX = "6421e666-f306-47d1-8656-c54af95599b5"  # Fairfax County, VA
CITE = ("zMOD Use Table 4101.1 + §4102.6.C (Self-Storage); Footnote 341: mini-warehousing "
        "changed from SE to allowed (subject to conditions) in I-3")

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,'I-3','Industrial District I-3',NULL,'permitted','permitted','permitted','unclear',
  $2::jsonb,$3,0.95,true,'human',$4,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage='permitted', mini_warehouse='permitted', light_industrial='permitted',
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection, confidence=0.95,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        cites = json.dumps([{"ordinance": "Fairfax County zMOD (2021)",
                             "section": "§4102.6.C / Table 4101.1",
                             "basis": "Self-Storage allowed (P, subject to conditions) in I-3 per FN341"}])
        note = ("Fairfax I-3: self_storage permitted (zMOD §4102.6.C, FN341 mini-warehousing "
                "SE->allowed in I-3). Verbatim-grounded.")
        await con.execute(SQL, FX, cites, CITE, note)
        r = await con.fetchrow(
            "SELECT self_storage::text ss, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND zone_code='I-3' AND municipality IS NULL AND deleted_at IS NULL", FX)
        print(f"Fairfax I-3: self_storage={r['ss']} human_reviewed={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
