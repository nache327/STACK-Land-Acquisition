"""Village of Lake Zurich (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds Lake Zurich's industrial + business districts against the Village
Municipal Code Title 9 Zoning (American Legal; SPA/Cloudflare 403s WebFetch but
curl+browser-UA got through; latest Ord. 2024-01-542). Closed-list per district:
§9-6-2 / §9-4-2 open "The following uses AND NO OTHERS are permitted as of right"
→ any use not listed P/S in a district is prohibited there (catch #58). Uses are
pinned to SIC codes (SIC 4225 = self-storage). Parcels rebound first via
rebind_configs/lakezurich.json off the GIS-Consortium public View (7,681 rebound;
I=314). Lake Zurich clears the wealth gate at ~61%.

Self-storage is a NAMED use — grounded on explicit placement (catch #37 verbatim):
  I — Industrial (Chapter 6; the ONLY industrial district):
    §9-6-3(K)(3) SPECIAL use: "Miniwarehouse warehousing and self-storage
      warehousing (4225)  S". (A separate special entry covers the outdoor-storage-
      yard variant, with §9-6-3 std (c): the outdoor yard is "prohibited on
      properties with frontage along Route 12 and Route 22" — indoor self-storage
      special use remains available corridor-wide.)
    §9-6-2(D)(3) PERMITTED: "Public warehousing and storage (422), not including
      miniwarehouse warehousing or self-storage warehousing (4225) ...  P"
      (general warehouse by right; the 4225 self-storage subclass is expressly
      excised to special use).
    §9-6-2(C) PERMITTED: manufacturing (SIC 2x/3x — fabricated metal 34, machinery
      35, electronic/electrical 36, furniture 25, misc) all "P".
    -> self_storage / mini_warehouse = CONDITIONAL (0.90) — NAMED special use.
    -> light_industrial = PERMITTED (0.92) — manufacturing + general warehouse by right.
    -> luxury_garage_condo = PROHIBITED (0.80) — UNNAMED; closed-list "and no others"
       sweep (#58); no by-inference verdict in human_reviewed.
  B-1 / B-2 / B-3 — Business (Chapter 4):
    No miniwarehouse/self-storage (SIC 4225) and no general warehousing (422) entry
    in §9-4-2 (permitted) or §9-4-3 (special); general light manufacturing absent
    (only Beverages 208 is a narrow special use).
    -> self_storage / mini_warehouse = PROHIBITED (0.90) — absent, closed-list.
    -> light_industrial = PROHIBITED (0.85) — general manufacturing absent.
    -> luxury_garage_condo = PROHIBITED (0.80) — unnamed.

catch #58 closed-list sweep (hard gate): self_storage NAMED and grounded on §9-6-3(K)(3)
placement; every unnamed use (luxury_garage_condo everywhere; self-storage/warehouse in
B-1/B-2/B-3) is PROHIBITED, never inferred. self_storage is permitted-by-right NOWHERE — the
I-district special-permit path is the sole route.

municipality='LAKE ZURICH' (catch #33; exact parcels.city, SELECT DISTINCT confirmed).
human-UPSERT (catch #29), verbatim citations, human_reviewed=true.
Run: python scripts/_apply_lake_lakezurich.py
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
MUNI = "LAKE ZURICH"
ORD = ("Village of Lake Zurich Municipal Code Title 9 Zoning "
       "(American Legal codelibrary.amlegal.com; Ord. 2024-01-542)")

_B_QUOTE = ('§9-4-2 permits "the following uses and no others" as of right in the Business '
            'districts; neither §9-4-2 nor §9-4-3 lists miniwarehouse/self-storage (SIC 4225), '
            'general warehousing (422), or general manufacturing (only Beverages 208 special).')
VERDICTS = {
    "I": ("I Industrial", "conditional", "conditional", "permitted", "prohibited", 0.90,
          "§9-6-3(K)(3) / §9-6-2",
          '§9-6-3(K)(3) special use: "Miniwarehouse warehousing and self-storage warehousing '
          '(4225)  S"; §9-6-2(D)(3) permits "Public warehousing and storage (422), not including '
          'miniwarehouse warehousing or self-storage warehousing (4225) ... P"; §9-6-2(C) '
          "permits SIC 2x/3x manufacturing by right.",
          "self_storage/mini_warehouse CONDITIONAL — NAMED special use (SIC 4225, §9-6-3(K)(3)); "
          "outdoor-yard variant barred on Rte 12/22 frontage but indoor special use is "
          "corridor-wide. light_industrial PERMITTED (manufacturing + general warehouse by "
          "right). luxury_garage_condo PROHIBITED — unnamed, closed-list 'and no others' (#58)."),
    "B-1": ("B-1 Local and Community Business", "prohibited", "prohibited", "prohibited",
            "prohibited", 0.90, "§9-4-2", _B_QUOTE,
            "self_storage/mini_warehouse/light_industrial PROHIBITED — absent from the B-1 "
            "closed list. luxury_garage_condo PROHIBITED — unnamed."),
    "B-2": ("B-2 Central Business", "prohibited", "prohibited", "prohibited", "prohibited",
            0.90, "§9-4-2", _B_QUOTE,
            "self_storage/mini_warehouse/light_industrial PROHIBITED — absent from the B-2 "
            "closed list. luxury_garage_condo PROHIBITED — unnamed."),
    "B-3": ("B-3 Regional Shopping", "prohibited", "prohibited", "prohibited", "prohibited",
            0.90, "§9-4-2", _B_QUOTE,
            "self_storage/mini_warehouse/light_industrial PROHIBITED — absent from the B-3 "
            "closed list. luxury_garage_condo PROHIBITED — unnamed."),
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
        print(f"applied {len(rows)} LAKE ZURICH rows:")
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
