"""Village of Lincolnshire (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds Lincolnshire's manufacturing/industrial/office districts against Village
Code Title 6 (M1 §6-7A rev. 2006; I §6-8B and O §6-8A rewritten 12-12-2022).
Parcels rebound first via rebind_configs/lincolnshire.json off the
utility.arcgis.com usrsvcs proxy serving the token-gated GIS-Consortium VOL
zoning data (3,072 rebound; I=73, M1=7, O=43). Lincolnshire clears the wealth
gate at 100%.

Self-storage is NOT a discrete named use; it folds into the "warehouse/storage"
bucket. Applying the warehouse⇒conditional convention (catch #58):

  M1 — Restricted Manufacturing (§6-7A):
    §6-7A-2 (permitted by right): "Storage and warehousing establishments." + "Cold
      storage plants." (storing must be within completely enclosed buildings, §6-7-1A).
    §6-7A-3(A) (special use): "Any other light manufacturing or light industrial
      fabricating, assembling ... storing, cleaning, servicing or testing establishments".
    -> self_storage / mini_warehouse = CONDITIONAL (0.80); light_industrial = PERMITTED
       (0.88); luxury_garage_condo = CONDITIONAL (0.65).
  I — Industrial (§6-8B, 2022):
    §6-8B-4 (permitted, "P"): "Warehouse and storage uses" (completely enclosed; no
      freight terminals/cartage) AND "Light manufacturing; fabricating; processing;
      assembly; repairing; storing; serviced; or testing ...".
    -> self_storage / mini_warehouse = CONDITIONAL (0.82); light_industrial = PERMITTED
       (0.90); luxury_garage_condo = CONDITIONAL (0.65).
  O — Office (§6-8A, 2022):
    §6-8A-1: "The district shall not allow expansion or relocation of any industrial,
      warehousing, or distribution uses ..."; no warehouse/storage row in §6-8A-4.
    -> self_storage / mini_warehouse / light_industrial = PROHIBITED (0.85);
       luxury_garage_condo = PROHIBITED (0.80).

CAVEAT (flagged, not blocking): neither M1 nor I names "self-storage / mini-warehouse"
discretely — both fold it into "warehouse/storage uses" (permitted by right), and both
require storage to be within a COMPLETELY ENCLOSED structure (outdoor/drive-up rows would
not qualify by right). The controlling definition of "Warehouse and storage uses" lives in
Title 6 Ch. 2 (not pulled). Conditional is the conservative reading per the warehouse
convention; upgrade to permitted only if the Ch.2 definition explicitly includes
customer-access self-storage.

municipality='LINCOLNSHIRE' (catch #33). human-UPSERT (catch #29), human_reviewed=true.
Run: python scripts/_apply_lake_lincolnshire.py
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
MUNI = "LINCOLNSHIRE"
ORD = ("Village of Lincolnshire Village Code Title 6 Zoning "
       "(lincolnshireil.gov/.../village-code/title-6)")

VERDICTS = {
    "M1": ("M1 Restricted Manufacturing", "conditional", "conditional", "permitted",
           "conditional", 0.80, "§6-7A-2 / §6-7A-3(A)",
           '§6-7A-2 permits by right "Storage and warehousing establishments." and "Cold '
           'storage plants."; §6-7A-3(A) special use covers "Any other light manufacturing or '
           'light industrial ... storing ... establishments" (storage must be fully enclosed, '
           "§6-7-1A).",
           "self_storage/mini_warehouse CONDITIONAL: warehouse/storage permitted by right but "
           "self-storage not discretely named -> warehouse=>conditional convention; fully-"
           "enclosed only. light_industrial PERMITTED. luxury_garage_condo CONDITIONAL."),
    "I": ("I Industrial", "conditional", "conditional", "permitted", "conditional", 0.82,
          "§6-8B-4",
          '§6-8B-4 permits ("P") "Warehouse and storage uses" (conducted within a completely '
          'enclosed structure; no freight terminals or cartage) and "Light manufacturing; '
          'fabricating; processing; assembly; repairing; storing; serviced; or testing".',
          "self_storage/mini_warehouse CONDITIONAL: 'Warehouse and storage uses' P by right but "
          "self-storage not discretely named -> warehouse=>conditional convention; fully-"
          "enclosed only. light_industrial PERMITTED. luxury_garage_condo CONDITIONAL."),
    "O": ("O Office", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, "§6-8A-1",
          '§6-8A-1: "The district shall not allow expansion or relocation of any industrial, '
          'warehousing, or distribution uses ..."; no warehouse/storage row in the §6-8A-4 '
          "use table.",
          "self_storage/mini_warehouse/light_industrial PROHIBITED — warehousing/industrial "
          "absent from the use table and expressly barred from expansion/relocation "
          "(except lawful pre-existing per §6-8A-2(A)(4)). luxury_garage_condo PROHIBITED."),
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
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} LINCOLNSHIRE rows:")
        for r in rows:
            print(f"  {r['zone_code']:3} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} "
                  f"lgc={r['lgc']:11} conf={r['conf']}")
        j = await con.fetch(
            "SELECT p.zoning_code, count(*) n, count(*) FILTER (WHERE p.acres>=1.5) ge15, "
            "count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 "
            "  AND prm.median_hhi>=100000) needles "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') "
            "LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
            "WHERE p.jurisdiction_id=$1::uuid AND p.city=$2 GROUP BY 1 ORDER BY 1", JID, MUNI)
        print("catch #42 + wealth-gated needles (ss perm/cond):")
        for r in j:
            print(f"  {r['zoning_code']:3} parcels={r['n']:>4} >=1.5ac={r['ge15']:>3} needles={r['needles']:>3}")
    finally:
        await con.close()


asyncio.run(main())
