"""City of Highland Park (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds Highland Park's industrial + relevant commercial districts against the
Highland Park Code of 1968, Chapter 150, **§150.490 "Table of Allowable Uses"**
(Municode, current thru Ord. O67-2025; extracted via the open Municode content
API since the SPA 403s). Parcels rebound first via rebind_configs/highlandpark.json
off the CORRECT City-of-Highland-Park zoning layer (CHP_Tyler_Energov_Viewing/3;
catch #38: codes AND lakefront geometry both verified — the prior "VHP" layer was
the wrong jurisdiction). 12,853 rebound.

§150.490 legend: P = permitted by right, C = conditional, blank = prohibited.
Verbatim storage/industrial rows:
  (M) STORAGE/PROCESSING/WHOLESALING:
    "Mini-warehouses"                              -> I = P  (blank everywhere else)
    "Warehouse and Distribution Facilities,        -> B3 = P, I = P
       Enclosed"
    "Wholesale Trade Offices & Storage Facilities" -> B3 = P, I = P
    "Open Storage Yards"                           -> B3 = C, I = C
  (N) INDUSTRIAL AND MANUFACTURING USES:
    manufacturing/processing/assembly rows         -> I only (mostly P)

Verdicts (municipality='HIGHLAND PARK'; ground, don't inflate):
  I (Light Industrial):
    self_storage / mini_warehouse = PERMITTED (0.92) — "Mini-warehouses" = P in I (the ONLY
      district permitting self-storage in Highland Park).
    light_industrial = PERMITTED (0.92) — manufacturing/processing/assembly (§150.490(N)) +
      enclosed warehouse/distribution (§150.490(M)) permitted by right in I.
    luxury_garage_condo = CONDITIONAL (0.65) — unlisted; analog to permitted mini-warehouse.
  B3 (Business — Highway/General Commercial):
    self_storage / mini_warehouse = PROHIBITED (0.88) — "Mini-warehouses" not permitted in B3
      (I only); closed-list Table of Allowable Uses.
    light_industrial = PERMITTED (0.82) — "Warehouse and Distribution Facilities, Enclosed" and
      "Wholesale Trade Offices & Storage Facilities" = P in B3 (manufacturing itself is I-only).
    luxury_garage_condo = PROHIBITED (0.75) — unlisted + self-storage barred in B3.

catch #58 closed-list sweep: §150.490 is a permissive matrix. self_storage PERMITTED only in I
(explicit P); B3 self-storage is an explicit prohibition. luxury_garage_condo (unlisted) held
below permitted everywhere. Highland Park clears the wealth gate (100%) so I-district >=1.5ac
parcels are true wealth-gated needles.

municipality='HIGHLAND PARK' (catch #33). human-UPSERT (catch #29), verbatim citations,
human_reviewed=true. Run: python scripts/_apply_lake_highlandpark.py
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
MUNI = "HIGHLAND PARK"
ORD = ("City of Highland Park Code of 1968, Ch. 150 Zoning, §150.490 Table of Allowable Uses "
       "(Municode, current thru Ord. O67-2025)")

VERDICTS = {
    "I": ("I Light Industrial", "permitted", "permitted", "permitted", "conditional", 0.92,
          '§150.490 Table of Allowable Uses: "Mini-warehouses" = "P" in the I district (the only '
          'district permitting it); manufacturing/processing/assembly (subsection N) and '
          '"Warehouse and Distribution Facilities, Enclosed" (subsection M) = "P" in I.',
          "self_storage/mini_warehouse PERMITTED by right (Mini-warehouses P in I — only such "
          "district in HP). light_industrial PERMITTED (manufacturing + enclosed warehouse P in "
          "I). luxury_garage_condo CONDITIONAL (unlisted; analog to permitted mini-warehouse)."),
    "B3": ("B3 Business", "prohibited", "prohibited", "permitted", "prohibited", 0.85,
           '§150.490: "Mini-warehouses" is NOT permitted in B3 (permitted in I only); "Warehouse '
           'and Distribution Facilities, Enclosed" and "Wholesale Trade Offices & Storage '
           'Facilities" = "P" in B3.',
           "self_storage/mini_warehouse PROHIBITED (Mini-warehouses I-only; closed-list). "
           "light_industrial PERMITTED (enclosed warehouse/distribution + wholesale storage P in "
           "B3; manufacturing itself is I-only). luxury_garage_condo PROHIBITED (unlisted + "
           "self-storage barred in B3)."),
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
            cites = json.dumps([{"ordinance": ORD, "section": "§150.490", "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, "§150.490",
                              conf, f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf, "
            "human_reviewed hr FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
            "AND municipality=$2 AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"\napplied {len(rows)} HIGHLAND PARK rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} "
                  f"lgc={r['lgc']:11} conf={r['conf']} hr={r['hr']}")
        j = await con.fetch(
            "SELECT p.zoning_code, count(*) n, count(*) FILTER (WHERE p.acres>=1.5) ge15, "
            "count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 "
            "  AND prm.median_hhi>=100000) needles "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') "
            "LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
            "WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 GROUP BY 1 ORDER BY 1", JID, MUNI)
        print("\ncatch #42 + wealth-gated needles (self_storage perm/cond):")
        for r in j:
            print(f"  {r['zoning_code']:4} parcels={r['n']:>4} >=1.5ac={r['ge15']:>3} "
                  f"wealth-gated-needles={r['needles']:>3}")
    finally:
        await con.close()


asyncio.run(main())
