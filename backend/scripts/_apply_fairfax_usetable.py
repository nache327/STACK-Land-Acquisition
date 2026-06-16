"""Fairfax County VA — Self-storage verdicts from zMOD Table 4-101.3 (adopted).

Read from the adopted Use Table 4-101.3 (R/C/I districts), Self-storage row
(use std Sect 4-102.2.A). Markers: P=permitted, SE=special exception=conditional,
blank=prohibited (silence rule). Self-storage == mini-warehousing (footnote 15).

  C-8 = SE      -> conditional
  I-3 = SE      -> conditional   (CORRECTS the earlier I-3=permitted, which came
                                  from superseded PDF draft footnote 341; the
                                  ADOPTED table shows SE)
  I-4/I-5/I-6 = P -> permitted
  I-I, I-2, C-1..C-7, all R = blank -> prohibited

PD Use Table 4-101.4 (Self-storage row) now also read:
  PDC = P/SE  -> conditional   (1,672 large-lot parcels — the big unlock)
  PTC = P/SE  -> conditional
  PRM, PDH, PRC = blank -> prohibited
(P/SE = permitted-if-on-development-plan else special exception → conditional, needle-eligible.)

STILL HELD (no zMOD column): CO/CS/CP/CC/AE/AC/AW/M/RTC (legacy / non-zMOD codes).

self_storage + mini_warehouse set from the Self-storage row; light_industrial /
luxury_garage_condo left 'unclear' (this row doesn't speak to them — no fabrication).
County-default rows (municipality=NULL); ON CONFLICT DO UPDATE (reverse-direction #13).
Run: python scripts/_apply_fairfax_usetable.py
"""
import asyncio
import json

import asyncpg

FX = "6421e666-f306-47d1-8656-c54af95599b5"  # Fairfax County, VA
CITE = "Fairfax zMOD Use Table 4-101.3 (R/C/I), Self-storage row; use std Sect 4-102.2.A"

# zone_code -> self_storage verdict (mini_warehouse mirrors it)
VERDICTS = {
    "I-4": "permitted", "I-5": "permitted", "I-6": "permitted",
    "I-3": "conditional", "C-8": "conditional",
    "I-I": "prohibited", "I-2": "prohibited",
    "C-1": "prohibited", "C-2": "prohibited", "C-3": "prohibited", "C-4": "prohibited",
    "C-5": "prohibited", "C-6": "prohibited", "C-7": "prohibited",
    # Planned Development (Use Table 4-101.4, Self-storage row)
    "PDC": "conditional", "PTC": "conditional", "PRM": "prohibited",
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,NULL,$4::use_permission_enum,$4::use_permission_enum,'unclear','unclear',
  $5::jsonb,$6,0.95,true,'human',$7,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection, confidence=0.95,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='60s'")
        for zc, verdict in VERDICTS.items():
            cites = json.dumps([{"ordinance": "Fairfax County zMOD (2021)",
                                 "section": "Use Table 4-101.3 / Sect 4-102.2.A",
                                 "basis": f"Self-storage = {verdict} in {zc} per adopted use table"}])
            note = f"{zc}: self_storage {verdict} (zMOD Table 4-101.3 Self-storage row)."
            await con.execute(SQL, FX, zc, f"Fairfax {zc}", verdict, cites, CITE, note)
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, human_reviewed hr FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1 AND zone_code=ANY($2::text[]) AND municipality IS NULL "
            "AND deleted_at IS NULL ORDER BY zone_code", FX, list(VERDICTS))
        for r in rows:
            print(f"  {r['zone_code']:5} self_storage={r['ss']:11} human={r['hr']}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
