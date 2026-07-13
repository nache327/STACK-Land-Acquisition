"""Village of Libertyville (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds Libertyville's industrial + office-park districts against Village
Municipal Code Ch. 26 (enumerated permitted-use §X.2 / special-permit-use §X.3
lists per district — a CLOSED list: a use not listed is prohibited). Sourced via
the open Municode content API (productId 12585, jobId 475302; SPA 403s). Parcels
rebound first via rebind_configs/libertyville.json off the utility.arcgis.com
usrsvcs proxy for the token-gated GIS-Consortium VLV data (8,769 rebound, 0
orphans). Libertyville clears the wealth gate at ~37%.

Self-storage is a NAMED use here (NAICS 53113 "lessors of mini-warehouses and
self-storage rental"), explicitly placed — so verdicts rest on the named
placement, NOT the warehouse⇒conditional inference (the ordinance overrides it):

  I-1 Limited Industrial (§26-7-2):
    §26-7-2.3(m)(1) SPECIAL use: "Real estate ... limited to lessors of
      mini-warehouses and self-storage rental (53113)."
    §26-7-2.2(o) PERMITTED: "warehousing and storage (493)."
    §26-7-2.2(h) PERMITTED: "Manufacturing, but limited to: [apparel, computer/
      electronic, food, furniture, machinery, plastics, printing ...]".
    -> self_storage / mini_warehouse = CONDITIONAL (0.90) — NAMED special use.
    -> light_industrial = PERMITTED (0.90) — manufacturing + warehousing by right.
    -> luxury_garage_condo = PROHIBITED (0.80) — UNNAMED; closed-list sweep (#58),
       no by-inference verdict in human_reviewed.
  I-3 General Industrial (§26-7-4):
    Self-storage/mini-warehouse ABSENT (NAICS 53113 not listed; the real-estate/
      rental entry §26-7-4.3(j)(1) is limited to 53212 truck/RV rental).
    §26-7-4.2(c) PERMITTED: "Manufacturing, but limited to: ...".
    §26-7-4.3(k)(4) SPECIAL: general/refrigerated warehousing (not self-storage).
    -> self_storage / mini_warehouse = PROHIBITED (0.88) — unnamed, closed-list.
    -> light_industrial = PERMITTED (0.90) — manufacturing by right.
    -> luxury_garage_condo = PROHIBITED (0.80) — unnamed.
  O-2 Office, Manufacturing and Distribution Park (§26-6-3):
    §26-6-3.2(u) EXPLICITLY EXCLUDES mini-warehouses ("Shared workspaces in
      nonresidential buildings, except mini-warehouses.").
    §26-6-3.2(l) PERMITTED: "Warehousing and storage (493)."
    §26-6-3.2(f) PERMITTED: "Manufacturing, but limited to: ...".
    -> self_storage / mini_warehouse = PROHIBITED (0.90) — expressly excluded.
    -> light_industrial = PERMITTED (0.90) — manufacturing + warehousing by right.
    -> luxury_garage_condo = PROHIBITED (0.80) — unnamed.

catch #58 closed-list sweep (hard gate): self_storage is NAMED and grounded on its
explicit placement (special in I-1, absent/excluded elsewhere); every unnamed use
(luxury_garage_condo everywhere; self-storage in I-3/O-2) is PROHIBITED, never
inferred permitted/conditional. Net: no by-right self-storage anywhere — the I-1
special-permit path is the sole self-storage route.

municipality='LIBERTYVILLE' (catch #33; matches parcels.city). human-UPSERT (catch #29),
verbatim citations, human_reviewed=true. Run: python scripts/_apply_lake_libertyville.py
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
MUNI = "LIBERTYVILLE"
ORD = ("Village of Libertyville Municipal Code Ch. 26 Zoning "
       "(Municode; api.municode.com/CodesContent productId 12585)")

VERDICTS = {
    "I-1": ("I-1 Limited Industrial", "conditional", "conditional", "permitted", "prohibited",
            0.90, "§26-7-2.3(m)(1)",
            '§26-7-2.3(m)(1) special permit use: "Real estate ... limited to lessors of '
            'mini-warehouses and self-storage rental (53113)"; §26-7-2.2(o) permits '
            '"warehousing and storage (493)" and §26-7-2.2(h) manufacturing by right.',
            "self_storage/mini_warehouse CONDITIONAL — NAMED special-permit use (NAICS 53113). "
            "light_industrial PERMITTED (manufacturing + warehousing by right). "
            "luxury_garage_condo PROHIBITED — unnamed, closed-list sweep (#58)."),
    "I-3": ("I-3 General Industrial", "prohibited", "prohibited", "permitted", "prohibited",
            0.88, "§26-7-4.2(c)",
            '§26-7-4.2(c) permits "Manufacturing, but limited to: ..." by right; the I-3 '
            "real-estate/rental entry (§26-7-4.3(j)(1)) is limited to 53212 truck/RV rental — "
            "NAICS 53113 self-storage appears NOWHERE in I-3.",
            "self_storage/mini_warehouse PROHIBITED — self-storage (53113) not listed (closed "
            "list); warehousing itself is only a special use (§26-7-4.3(k)(4)). light_industrial "
            "PERMITTED (manufacturing by right). luxury_garage_condo PROHIBITED — unnamed."),
    "O-2": ("O-2 Office, Manufacturing and Distribution Park", "prohibited", "prohibited",
            "permitted", "prohibited", 0.90, "§26-6-3.2(u) / §26-6-3.2(l)",
            '§26-6-3.2(u) expressly EXCLUDES mini-warehouses ("... except mini-warehouses."); '
            '§26-6-3.2(l) permits "Warehousing and storage (493)" and §26-6-3.2(f) manufacturing '
            "by right.",
            "self_storage/mini_warehouse PROHIBITED — expressly excluded (§26-6-3.2(u)). "
            "light_industrial PERMITTED (manufacturing + warehousing by right). "
            "luxury_garage_condo PROHIBITED — unnamed."),
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
        print(f"applied {len(rows)} LIBERTYVILLE rows:")
        for r in rows:
            print(f"  {r['zone_code']:4} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} "
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
            print(f"  {r['zoning_code']:4} parcels={r['n']:>4} >=1.5ac={r['ge15']:>3} needles={r['needles']:>3}")
    finally:
        await con.close()


asyncio.run(main())
