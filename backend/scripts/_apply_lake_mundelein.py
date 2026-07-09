"""Village of Mundelein (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds Mundelein municipal commercial + manufacturing districts against the
Village of Mundelein Zoning Ordinance, Title 20 (amended 2021-06-09; town PDF
DocumentCenter/View/326), use tables **20.32-1** (Commercial, §20.32.020) and
**20.40-1** (Office Park & Manufacturing, §20.40.020). Column alignment
char-position-verified. Parcels rebound to real codes first via
rebind_configs/mundelein.json (11,986 rebound off GIS-Consortium VMD layer).

The ordinance defines: "Mini-Warehouse" means a facility used for the storage
of property where individual renters control individual storage spaces — i.e.
exactly a self-storage / self-service storage facility.

Verbatim cells (P=permitted / S=special use / blank=prohibited):
  "Mini-Warehouse"          Table 20.32-1: C-1 P, C-2 P, C-3 P, C-4 P
                            Table 20.40-1: O-R blank, M-1 P, M-MU P
                            (C-5 downtown Table 20.36-1: row ABSENT -> prohibited)
  "Warehouse/Distribution"  Table 20.40-1: O-R S, M-1 P, M-MU P

Verdicts (municipality='MUNDELEIN'; ground, don't inflate):
  C-1/C-2/C-3/C-4: self_storage + mini_warehouse PERMITTED (0.92) — "Mini-Warehouse" P.
    light_industrial PROHIBITED (0.85) — no Warehouse/industrial row in the commercial table.
    luxury_garage_condo CONDITIONAL (0.65) — unlisted, analog to permitted mini-warehouse.
  M-1 / M-MU: self_storage + mini_warehouse PERMITTED (0.93) — "Mini-Warehouse" P.
    light_industrial PERMITTED (0.93) — "Warehouse/Distribution" P.
    luxury_garage_condo CONDITIONAL (0.65) — unlisted.
  O-R: self_storage + mini_warehouse PROHIBITED (0.85) — "Mini-Warehouse" blank in O-R.
    light_industrial CONDITIONAL (0.80) — "Warehouse/Distribution" = S in O-R.
    luxury_garage_condo PROHIBITED (0.75) — unlisted + storage prohibited.
  (C5-VC/MU/R/C left UNGROUNDED — all storage uses absent from Table 20.36-1 = prohibited;
   no by-right/heuristic lead risk, so no false-positive to close.)

catch #58 closed-list sweep: Title 20 tables are permissive (absence = not allowed). Every
PERMITTED verdict rests on an explicit "P"; unlisted uses (luxury_garage_condo; storage in
O-R/C-5) are held at conditional/prohibited, never inferred permitted.

SOURCE CAVEAT (flagged, not blocking): Table 20.32-1 prints use-standard "Section 20.48.040(I)"
for Mini-Warehouse, but in the current amended §20.48.040 letter (I)=Banquet Facility and no
standalone Mini-Warehouse subsection exists — the table's parenthetical letters are stale
(pre-amendment lettering). Verdicts rest on the unambiguous P cells in the use tables, NOT on
the (I) pointer.

municipality='MUNDELEIN' (catch #33). human-UPSERT (catch #29), verbatim citations,
human_reviewed=true. Run: python scripts/_apply_lake_mundelein.py
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
MUNI = "MUNDELEIN"
ORD = ("Village of Mundelein Zoning Ordinance, Title 20 (amended 2021-06-09; "
       "https://www.mundelein.org/DocumentCenter/View/326)")

_COMM = ('Table 20.32-1 (Commercial, §20.32.020): "Mini-Warehouse" = "P" (permitted) in the '
         '{zc} column. No Warehouse/industrial use row appears in the commercial table.')
_MFG = ('Table 20.40-1 (Office Park & Manufacturing, §20.40.020): "Mini-Warehouse" = "P" and '
        '"Warehouse/Distribution" = "P" in the {zc} column.')
_OR = ('Table 20.40-1 (§20.40.020): "Mini-Warehouse" is absent (prohibited) in O-R; '
       '"Warehouse/Distribution" = "S" (special use) in O-R.')

# zone -> (zone_name, ss, mw, li, lgc, conf, section, quote, note)
VERDICTS = {
    "C-1": ("C-1 Neighborhood Commercial", "permitted", "permitted", "prohibited",
            "conditional", 0.92, "Table 20.32-1", _COMM,
            "Mini-Warehouse (=self-storage) P by right; light_industrial prohibited (no "
            "warehouse row in commercial table); luxury_garage_condo conditional (unlisted)."),
    "C-2": ("C-2 General Commercial", "permitted", "permitted", "prohibited",
            "conditional", 0.92, "Table 20.32-1", _COMM,
            "Mini-Warehouse P by right; light_industrial prohibited; garage_condo conditional."),
    "C-3": ("C-3 Heavy Commercial", "permitted", "permitted", "prohibited",
            "conditional", 0.92, "Table 20.32-1", _COMM,
            "Mini-Warehouse P by right; light_industrial prohibited; garage_condo conditional."),
    "C-4": ("C-4 Shopping Center", "permitted", "permitted", "prohibited",
            "conditional", 0.92, "Table 20.32-1", _COMM,
            "Mini-Warehouse P by right; light_industrial prohibited; garage_condo conditional."),
    "M-1": ("M-1 General Manufacturing", "permitted", "permitted", "permitted",
            "conditional", 0.93, "Table 20.40-1", _MFG,
            "Mini-Warehouse + Warehouse/Distribution P by right; garage_condo conditional."),
    "M-MU": ("M-MU Manufacturing Mixed-Use", "permitted", "permitted", "permitted",
             "conditional", 0.93, "Table 20.40-1", _MFG,
             "Mini-Warehouse + Warehouse/Distribution P by right; garage_condo conditional."),
    "O-R": ("O-R Office-Research", "prohibited", "prohibited", "conditional",
            "prohibited", 0.85, "Table 20.40-1", _OR,
            "Mini-Warehouse absent (prohibited) in O-R; light_industrial CONDITIONAL "
            "(Warehouse/Distribution = S); garage_condo prohibited (unlisted + storage barred)."),
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
        for zc, (zname, ss, mw, li, lgc, conf, sec, qtmpl, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": sec,
                                 "quote": qtmpl.format(zc=zc)}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, sec, conf,
                              f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf, "
            "human_reviewed hr FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"\napplied {len(rows)} MUNDELEIN rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} "
                  f"lgc={r['lgc']:11} conf={r['conf']} hr={r['hr']}")
        j = await con.fetch(
            "SELECT p.zoning_code, count(*) n, count(*) FILTER (WHERE p.acres>=1.5) ge15 "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 "
            "GROUP BY 1 ORDER BY 1", JID, MUNI)
        print("\ncatch #42 — rebound parcels joining a human MUNDELEIN verdict:")
        for r in j:
            print(f"  {r['zoning_code']:5} parcels={r['n']:>5}  >=1.5ac={r['ge15']:>4}")
    finally:
        await con.close()


asyncio.run(main())
