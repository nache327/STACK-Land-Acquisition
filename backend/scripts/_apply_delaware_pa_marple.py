"""Marple Township (Delaware County PA) — Stage-4 self-storage verdicts. eCode360
Ch. 300 Zoning, permitted-use attachment tables pasted 2026-07-07:
300 Attachment 5 (§ 300-37 Commercial: O/O-1/N/B/B-1), Attachment 7 (§ 300-45
Industrial: I), Attachment 9 (§ 300-49 Institutional: INS/NS/C).

I (§ 300-45) — "Warehousing and distributing, including storage for personal
  household use — P". STORAGE FOR PERSONAL HOUSEHOLD USE = self-storage in plain
  words, PERMITTED BY RIGHT -> self_storage/mini_warehouse PERMITTED (0.95).
  Manufacturing/fabrication P -> light_industrial PERMITTED. luxury_garage_condo:
  personal vehicle storage arguably within "storage for personal household use" but
  not explicit -> conditional (0.75). 29 pool parcels >=1.5ac.

O / O-1 / N / B / B-1 (§ 300-37 table) — no storage/warehouse classification in the
  commercial permitted-use table; silence = prohibited -> PROHIBITED (0.90).
INS / NS / C (§ 300-49 table) — institutional uses only -> PROHIBITED (0.90).

HELD (not in pasted tables): HID (2 pool parcels), CCRC, OS, PRD, R-*.

Muni-specific municipality='Marple Township' (catch #33 family); human-UPSERT
(catch #29). Run: python scripts/_apply_delaware_pa_marple.py
"""
import asyncio
import json

import asyncpg

JID = "de8945f7-9ad8-4441-a207-83ea372e1f48"  # Delaware County, PA
MUNI = "Marple Township"
ORD = "Marple Township Code Ch. 300 Zoning (eCode360 https://ecode360.com/10776506)"

_COMM = ("§ 300-37 (300 Attachment 5)",
         "Permitted Uses — Commercial: retail commerce, offices, hotels, museums, "
         "transit, animal hospital, public garage, mixed-use residences, municipal",
         "no storage/warehouse use classification in the commercial table; silence = prohibited")
_INST = ("§ 300-49 (300 Attachment 9)",
         "Permitted Uses — Institutional: educational/cultural/religious uses, "
         "institutional residence/care, schools, cemeteries, municipal",
         "institutional table only; no storage/warehouse classification; silence = prohibited")

# zone -> (ss, mw, li, lgc, conf, section, verbatim_quote, note)
VERDICTS = {
    "I": ("permitted", "permitted", "permitted", "conditional", 0.95,
          "§ 300-45 (300 Attachment 7)",
          "Warehousing and distributing, including storage for personal household use — P",
          "'storage for personal household use' = self-storage in plain words, PERMITTED "
          "by right; manufacturing/fabrication also P -> light_industrial permitted. "
          "garage_condo: personal vehicle storage arguably within the classification but "
          "not explicit -> conditional."),
}
for z in ("O", "O-1", "N", "B", "B-1"):
    VERDICTS[z] = ("prohibited", "prohibited", "prohibited", "prohibited", 0.90, *_COMM)
for z in ("INS", "NS", "C"):
    VERDICTS[z] = ("prohibited", "prohibited", "prohibited", "prohibited", 0.90, *_INST)

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
                SQL, JID, zc, f"Marple Twp {zc}", MUNI, ss, mw, li, lgc,
                cites, section, conf,
                f"{zc}: self_storage {ss} — {section}: \"{quote}\" — {note}",
            )
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, confidence conf, human_reviewed hr, "
            "cited_subsection sec FROM zone_use_matrix WHERE jurisdiction_id=$1 "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Marple Township rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} conf={r['conf']} hr={r['hr']} {r['sec'][:40]}")
    finally:
        await con.close()


asyncio.run(main())
