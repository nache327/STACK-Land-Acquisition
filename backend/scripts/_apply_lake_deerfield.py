"""Village of Deerfield (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds Deerfield's two industrial districts against the CURRENT ADOPTED Village
Zoning Ordinance, Article 6 Industrial Districts (official Village PDF
DocumentCenter/View/2663 — the codified article, NOT the 2023 draft View/3703).
Parcels rebound first via rebind_configs/deerfield.json (7,008 rebound off
GIS-Consortium VDF layer; Lake-side parcels).

I-1 "Office, Research, Restricted Industrial District" (Sec. 6.01):
  By-right industrial = Research & Testing Laboratories only (6.01-B,3). Manufacturing/
  warehouse reach I-1 ONLY as a special use via 6.01-C(3) "Any industrial use permitted in
  the I-2 ... developed as part of a Planned Industrial Development." Self-service storage is
  an I-2 *special* use (not an I-2 *permitted* use), so it is NOT borrowable through
  6.01-C(3) -> self-storage absent/prohibited in I-1 (uncertainty flagged in note).

I-2 "Limited Industrial District" (Sec. 6.02):
  6.02-B(1) production/processing/assembly by right; 6.02-B(4) "Warehouse and distribution
  facilities ..." by right (indoor; outside storage barred 6.02-G,4,c). 6.02-C(13)
  "Self-Service Storage Facilities ... when located within an I-2 Industrial Planned Unit
  Development." 6.02-C(8) "Indoor Storage Facility for boats, campers, vehicles ...".
  NOTE: I-2 imposes a 5-acre min lot (2-acre if within an Industrial PUD) — 6.02-F,1.

Verdicts (municipality='DEERFIELD'; ground, don't inflate — thin needle):
  I-1: self_storage / mini_warehouse = PROHIBITED (0.80) — no self-storage provision; the
    6.01-C(3) gateway borrows only I-2 *permitted* uses, and self-storage is an I-2 *special*
    use -> not reachable (conservative reading; a Village interpretation could differ).
    light_industrial = CONDITIONAL (0.75) — manufacturing/warehouse only via special-use
    Planned Industrial Development (6.01-C(3)); by-right industrial is R&D labs only.
    luxury_garage_condo = PROHIBITED (0.75) — unlisted, not reachable.
  I-2: self_storage / mini_warehouse = CONDITIONAL (0.85) — special use, only within an I-2
    Industrial PUD (6.02-C(13)); the sole self-storage pathway in the Village.
    light_industrial = PERMITTED (0.92) — production/assembly (6.02-B(1)) + warehouse
    (6.02-B(4)) by right.
    luxury_garage_condo = CONDITIONAL (0.70) — "Indoor Storage Facility for boats, campers,
    vehicles" special use (6.02-C(8)); garage-condo is the closest analog.

catch #58 closed-list sweep: self-storage permitted NOWHERE by-right in Deerfield (I-2 special
+ PUD only; I-1 prohibited). No PERMITTED verdict for self-storage; every non-prohibited
value rests on a named special use. light_industrial PERMITTED only in I-2 (explicit by-right).

municipality='DEERFIELD' (catch #33). human-UPSERT (catch #29), verbatim citations,
human_reviewed=true. Run: python scripts/_apply_lake_deerfield.py
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
MUNI = "DEERFIELD"
ORD = ("Village of Deerfield Zoning Ordinance, Article 6 Industrial Districts "
       "(adopted; https://www.deerfield.il.us/DocumentCenter/View/2663)")

VERDICTS = {
    "I-1": ("I-1 Office, Research, Restricted Industrial", "prohibited", "prohibited",
            "conditional", "prohibited", 0.80, "Sec. 6.01-B / 6.01-C(3)",
            "6.01-B by-right industrial = 'Research and Testing Laboratories' only; 6.01-C(3) "
            "special use = 'Any industrial use permitted in the I-2 ... developed as part of a "
            "Planned Industrial Development.'",
            "self_storage/mini_warehouse PROHIBITED: no self-storage provision in I-1; the "
            "6.01-C(3) gateway borrows only I-2 PERMITTED uses and self-storage is an I-2 "
            "SPECIAL use -> not reachable (conservative; Village interpretation could differ). "
            "light_industrial CONDITIONAL: manufacturing/warehouse only via special-use Planned "
            "Industrial Development. luxury_garage_condo PROHIBITED (unlisted)."),
    "I-2": ("I-2 Limited Industrial", "conditional", "conditional", "permitted",
            "conditional", 0.85, "Sec. 6.02",
            "6.02-C(13) 'Self-Service Storage Facilities ... when located within an I-2 "
            "Industrial Planned Unit Development'; 6.02-B(1) production/processing/assembly and "
            "6.02-B(4) 'Warehouse and distribution facilities' by right; 6.02-C(8) 'Indoor "
            "Storage Facility for boats, campers, vehicles'.",
            "self_storage/mini_warehouse CONDITIONAL: special use, only within an I-2 Industrial "
            "PUD (6.02-C(13)) — sole self-storage pathway in the Village; 5-acre min lot "
            "(2-acre in PUD) per 6.02-F,1. light_industrial PERMITTED: production/assembly + "
            "warehouse by right. luxury_garage_condo CONDITIONAL: Indoor Storage Facility for "
            "vehicles special use (6.02-C(8))."),
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
        for zc, (zname, ss, mw, li, lgc, conf, sec, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": sec, "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, sec, conf,
                              f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf, "
            "human_reviewed hr FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"\napplied {len(rows)} DEERFIELD rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} "
                  f"lgc={r['lgc']:11} conf={r['conf']} hr={r['hr']}")
        j = await con.fetch(
            "SELECT p.zoning_code, count(*) n, count(*) FILTER (WHERE p.acres>=1.5) ge15 "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 "
            "GROUP BY 1 ORDER BY 1", JID, MUNI)
        print("\ncatch #42 — rebound parcels joining a human DEERFIELD verdict:")
        for r in j:
            print(f"  {r['zoning_code']:5} parcels={r['n']:>5}  >=1.5ac={r['ge15']:>4}")
    finally:
        await con.close()


asyncio.run(main())
