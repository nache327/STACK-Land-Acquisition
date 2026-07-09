"""City of Waukegan (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds Waukegan's two industrial districts against the Waukegan Unified
Development Ordinance (eff. 2024-07-01; town PDF DocumentCenter/View/10026),
**Table 9.02-1 "Principal Uses and Structures", Section 9.02.A**. Cell values
coordinate-verified (pdfplumber word-x vs header centers; R/LI and I columns
separated 17.4px — zero alignment ambiguity). Parcels rebound first via
rebind_configs/waukegan.json (23,698 rebound; New_Zoning_Code label prefix).

Legend: P = permitted by-right, C = conditional use (§4.08), blank = not allowed.

Verbatim cells (Table 9.02-1):
  "Self-Storage (Indoor)"               R/LI blank,  I C   (Use Standards: None)
  "Warehousing and Distribution         R/LI P,      I P
     Facility"
  "Light Manufacturing"                 R/LI P,      I P
Def. (Section 13): "Self-Storage (Indoor)" = a facility used for the storage of
personal property where individuals rent storage. No "mini-warehouse" row exists
(that IS this use). No self-storage cell anywhere except I.

Verdicts (municipality='WAUKEGAN'; ground, don't inflate):
  I (Light Industrial):
    self_storage / mini_warehouse = CONDITIONAL (0.90) — "Self-Storage (Indoor)" = C in I.
    light_industrial = PERMITTED (0.92) — "Light Manufacturing" & "Warehousing and
      Distribution Facility" both P in I.
    luxury_garage_condo = CONDITIONAL (0.65) — unlisted; analog to conditional self-storage.
  R/LI (Research/Light Industrial):
    self_storage / mini_warehouse = PROHIBITED (0.88) — "Self-Storage (Indoor)" is blank
      (not allowed) in R/LI; closed-list use table => prohibited.
    light_industrial = PERMITTED (0.92) — "Light Manufacturing" & "Warehousing..." P in R/LI.
    luxury_garage_condo = PROHIBITED (0.75) — unlisted + self-storage barred in R/LI.

catch #58 closed-list sweep: Table 9.02-1 is permissive (blank = not allowed). self_storage
permitted NOWHERE by-right in Waukegan (only conditional in I); R/LI self-storage is an
explicit prohibition, not an inference. light_industrial permitted only where an explicit P.
Narrow self-storage universe (I only, conditional) — matches recon.

municipality='WAUKEGAN' (catch #33). human-UPSERT (catch #29), verbatim citations,
human_reviewed=true. Run: python scripts/_apply_lake_waukegan.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "10d01284-829b-4b03-b416-54bc452b8e70"  # Lake County, IL
MUNI = "WAUKEGAN"
ORD = ("City of Waukegan Unified Development Ordinance (eff. 2024-07-01), Table 9.02-1 "
       "Principal Uses and Structures, Section 9.02.A "
       "(https://www.waukeganil.gov/DocumentCenter/View/10026)")

VERDICTS = {
    "I": ("I Light Industrial", "conditional", "conditional", "permitted", "conditional", 0.90,
          '"Self-Storage (Indoor)" = "C" (conditional use) in the I column; "Light '
          'Manufacturing" and "Warehousing and Distribution Facility" = "P" in I.',
          "self_storage/mini_warehouse CONDITIONAL (Self-Storage (Indoor) = C in I). "
          "light_industrial PERMITTED (Light Manufacturing + Warehousing P in I). "
          "luxury_garage_condo CONDITIONAL (unlisted; analog to conditional self-storage)."),
    "R/LI": ("R/LI Research/Light Industrial", "prohibited", "prohibited", "permitted",
             "prohibited", 0.88,
             '"Self-Storage (Indoor)" is blank (not allowed) in the R/LI column; "Light '
             'Manufacturing" and "Warehousing and Distribution Facility" = "P" in R/LI.',
             "self_storage/mini_warehouse PROHIBITED (Self-Storage (Indoor) blank in R/LI; "
             "closed-list). light_industrial PERMITTED (Light Manufacturing + Warehousing P). "
             "luxury_garage_condo PROHIBITED (unlisted + self-storage barred in R/LI)."),
}

SQL = """
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
  $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage,
  mini_warehouse=EXCLUDED.mini_warehouse, light_industrial=EXCLUDED.light_industrial,
  luxury_garage_condo=EXCLUDED.luxury_garage_condo, citations=EXCLUDED.citations,
  cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence,
  human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=60)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Lake" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}  municipality: {MUNI}")
        await con.execute("SET statement_timeout = '60s'")
        for zc, (zname, ss, mw, li, lgc, conf, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": "Table 9.02-1 / §9.02.A",
                                 "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites,
                              "Table 9.02-1", conf, f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf, "
            "human_reviewed hr FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"\napplied {len(rows)} WAUKEGAN rows:")
        for r in rows:
            print(f"  {r['zone_code']:6} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} "
                  f"lgc={r['lgc']:11} conf={r['conf']} hr={r['hr']}")
        j = await con.fetch(
            "SELECT p.zoning_code, count(*) n, count(*) FILTER (WHERE p.acres>=1.5) ge15 "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 "
            "GROUP BY 1 ORDER BY 1", JID, MUNI)
        print("\ncatch #42 — rebound parcels joining a human WAUKEGAN verdict:")
        for r in j:
            print(f"  {r['zoning_code']:6} parcels={r['n']:>5}  >=1.5ac={r['ge15']:>4}")
    finally:
        await con.close()


asyncio.run(main())
