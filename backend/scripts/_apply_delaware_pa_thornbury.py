"""Thornbury Township (Delaware County PA) — Stage-4 self-storage verdicts. eCode360
Ch. 27 Zoning, Article 9 (LI) + Article 10 (C) pasted 2026-07-07. catch #38: this is
Thornbury DELAWARE County (there is also a Thornbury Twp in Chester County).

LI (§ 27-902) — the narrowest LI in the county: a four-item closed list ("and no
  other") — offices, industrial research laboratories, manufacture of specified
  products, accessory. NO warehouse, NO storage, NO distribution, NO same-character
  SE catch-all anywhere in the article -> self_storage/mini_warehouse PROHIBITED by
  silence (0.92). light_industrial PERMITTED (0.95, the manufacturing list is the
  district core). Kills the 4-parcel LI pool — an honest kill: wealth geography
  without a storage pathway (Tewksbury-rule cousin at the zone level).

C (§ 27-1002) — closed list (retail <=10k sf, restaurant, personal service, office,
  bank, agriculture); (H) same-general-character SE reaches only uses of THAT
  character (retail/office/agricultural — not storage); accessory (G)(1) enclosed
  storage in conjunction with a permitted use only -> PROHIBITED (0.90).

HELD (not pasted): I, IR, MHP, PA, PRD-1..3, Q-1, Q-2, R-1..3.

Muni-specific municipality='Thornbury Township'; human-UPSERT (catch #29).
Run: python scripts/_apply_delaware_pa_thornbury.py
"""
import asyncio
import json

import asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Thornbury Township"
ORD = "Thornbury Township (Delaware Co) Code Ch. 27 Zoning (eCode360 https://www.ecode360.com/30948831)"

VERDICTS = {
    "LI": ("prohibited", "prohibited", "permitted", "prohibited", 0.92,
           "§ 27-902(1)",
           "A building may be erected, altered or used and a lot may be used or "
           "occupied for any of the following purposes, and no other: A. "
           "Administrative, executive or professional office. B. Industrial research "
           "laboratories. C. Manufacture, compounding, processing, assembly ...",
           "four-item closed list; no warehouse/storage/distribution use and no "
           "same-character SE catch-all in the article — silence = prohibited. "
           "Manufacturing by right -> light_industrial permitted."),
    "C": ("prohibited", "prohibited", "prohibited", "prohibited", 0.90,
          "§ 27-1002(1)",
          "A building, separate or unified, may be erected or used and a lot may be "
          "used or occupied for any one of the following uses and no other",
          "retail/office/agriculture closed list; (H) same-general-character SE "
          "reaches only uses of that character; accessory (G)(1) enclosed storage in "
          "conjunction with a permitted use only."),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
  $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, luxury_garage_condo=EXCLUDED.luxury_garage_condo,
  citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
  confidence=EXCLUDED.confidence, human_reviewed=true, classification_source='human',
  notes=EXCLUDED.notes, updated_at=now()
"""


async def main() -> None:
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=40, statement_cache_size=0)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1", JID)
        assert jn == "Delaware County, PA", jn
        await con.execute("SET statement_timeout='60s'")
        for zc, (ss, mw, li, lgc, conf, section, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": section, "quote": quote}])
            await con.execute(
                SQL, JID, zc, f"Thornbury Twp (Delco) {zc}", MUNI, ss, mw, li, lgc,
                cites, section, conf,
                f"{zc}: self_storage {ss} — {section}: \"{quote[:160]}\" — {note}",
            )
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf, human_reviewed hr, "
            "cited_subsection sec FROM zone_use_matrix WHERE jurisdiction_id=$1 "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Thornbury Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} ss={r['ss']:11} conf={r['conf']} hr={r['hr']} {r['sec']}")
    finally:
        await con.close()


asyncio.run(main())
