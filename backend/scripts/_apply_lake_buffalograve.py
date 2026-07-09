"""Village of Buffalo Grove (Lake County, IL) — Stage-4 self-storage verdicts.

Grounds Buffalo Grove's Office/Industrial districts against Village Municipal
Code Title 17, Ch. 17.48 (Office & Industrial). Parcels rebound first via
rebind_configs/buffalograve.json off the utility.arcgis.com usrsvcs proxy that
serves the token-gated GIS-Consortium VBG zoning data anonymously (10,611
rebound; I=316, O&R=49). Buffalo Grove clears the wealth gate at 100%.

Self-storage is NOT a discrete named principal use in Ch. 17.48. Applying the
warehouse⇒conditional convention (warehouse/"storing" permitted by right ⇒
self_storage/mini_warehouse CONDITIONAL, not inferred permitted; catch #58):

  I — INDUSTRIAL (§17.48.020):
    §17.48.020.B.6 (permitted by right): "Any manufacturing, fabricating,
      processing, assembly, repairing, storing, cleaning, servicing or testing of
      materials, goods or products, and related office uses." ("storing" = by right)
    §17.48.020.C.20 (special use): "A dwelling unit for a full-time resident manager
      ... as an accessory use in a self-storage facility ..." (the code's only
      explicit reference to a self-storage facility — a special-use hook, confirming
      self-storage operates in I).
    -> self_storage / mini_warehouse = CONDITIONAL (0.78) — storage by right but
       self-storage not a discrete by-right principal use (only the manager dwelling
       is a named special use); conservative conditional per convention.
    -> light_industrial = PERMITTED (0.90) — manufacturing/fabricating by right (B.6).
    -> luxury_garage_condo = CONDITIONAL (0.65) — unlisted; analog to self-storage.
  O&R — OFFICE AND RESEARCH (§17.48.010):
    Self-storage/mini-warehouse ABSENT from permitted (B) and special (C) lists.
    §17.48.010.C.2 (special): "Limited industrial and warehousing uses which are
      directly incidental and accessory to one or more of the principal permitted
      uses ..." (standalone warehousing absent).
    -> self_storage / mini_warehouse = PROHIBITED (0.85) — not listed; closed-list.
    -> light_industrial = CONDITIONAL (0.78) — only as incidental/accessory special use.
    -> luxury_garage_condo = PROHIBITED (0.75).

CAVEAT (flagged, not blocking): self-storage isn't a discrete listed use; a real
BG self-storage was approved via B-3 Commercial PUD (PUD/special path). The Title 17
verbatim above is from the Zoneomics mirror (Municode SPA + content API both 403 the
fetcher); confirm exact §17.48.020.B/C wording + any 17.12 "self-storage facility"
definition against Municode in a browser before upgrading conditional->permitted.

municipality='BUFFALO GROVE' (catch #33). human-UPSERT (catch #29), human_reviewed=true.
Run: python scripts/_apply_lake_buffalograve.py
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
MUNI = "BUFFALO GROVE"
ORD = ("Village of Buffalo Grove Municipal Code Title 17, Ch. 17.48 (Office & Industrial) "
       "(Municode library.municode.com/il/buffalo_grove)")

VERDICTS = {
    "I": ("I Industrial", "conditional", "conditional", "permitted", "conditional", 0.78,
          "§17.48.020.B.6 / .C.20",
          '§17.48.020.B.6 permits by right "Any manufacturing, fabricating, processing, '
          'assembly, repairing, storing, cleaning, servicing or testing of materials, goods or '
          'products"; §17.48.020.C.20 references "an accessory use in a self-storage facility".',
          "self_storage/mini_warehouse CONDITIONAL: storage permitted by right (B.6 'storing') "
          "but self-storage is not a discrete by-right principal use (only the resident-manager "
          "dwelling is a named special use, C.20) -> warehouse=>conditional convention (catch "
          "#58). light_industrial PERMITTED (manufacturing by right, B.6). luxury_garage_condo "
          "CONDITIONAL (unlisted)."),
    "O&R": ("O&R Office and Research", "prohibited", "prohibited", "conditional", "prohibited",
            0.82, "§17.48.010.C.2",
            '§17.48.010.C.2 (special use): "Limited industrial and warehousing uses which are '
            'directly incidental and accessory to one or more of the principal permitted uses"; '
            "self-storage/mini-warehouse appear in neither the permitted (B) nor special (C) list.",
            "self_storage/mini_warehouse PROHIBITED (not listed; closed-list). light_industrial "
            "CONDITIONAL (only incidental/accessory to a principal permitted use, C.2). "
            "luxury_garage_condo PROHIBITED (unlisted)."),
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
        print(f"applied {len(rows)} BUFFALO GROVE rows:")
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
