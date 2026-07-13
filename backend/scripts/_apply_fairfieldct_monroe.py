"""Town of Monroe (Fairfield County, CT — county_gis jid) — Stage-4 verdicts.

Grounds Monroe's industrial + Stevenson-Business districts against the Town
Zoning Regulations (amended through 7/2/2026, town PDF), Article 10 "Schedule of
Permitted Land Uses". Parcels rebound via rebind_configs/monroe_ct.json off the
MetroCOG layer (6,824 rebound). Monroe clears the wealth gate (~100% ring cov).
Closed-list §1.9.12 ("Uses which are not specifically permitted ... are hereby
declared to be prohibited uses"). Legend: P=permitted, SEP=special exception,
x=not permitted.

Self-storage is a NAMED use — row "Self-Storage Warehousing for Rental of Fully
Interior Enclosed Building Space" (Art. 10 §10.1): SB-2 SEP, I-2 SEP; B-1/B-2/
LOR/I-1/I-3 = x (prohibited). Manufacturing (row "Manufacturing, Processing
and/or Assembly ... Fully Enclosed Buildings") = SEP in SB-2/I-1/I-2/I-3 (NO
by-right anywhere). Warehouse row = SEP in SB-2/I-1/I-2/I-3.

Verdicts (municipality='Monroe'):
  SB-2 / I-2: self_storage / mini_warehouse = CONDITIONAL (0.90, NAMED SEP);
    light_industrial = CONDITIONAL (0.88, manufacturing SEP — not by-right);
    luxury_garage_condo = PROHIBITED (0.85, unnamed -> #58).
  I-1 / I-3: self_storage / mini_warehouse = PROHIBITED (0.88, "x" in the schedule);
    light_industrial = CONDITIONAL (0.88, manufacturing SEP); luxury_garage_condo = PROHIBITED.

catch #58: self_storage NAMED, grounded on the Art. 10 schedule cell; unnamed uses swept to
prohibited. catch #57: affirmative schedule cell beats silence. No by-right storage/industrial
anywhere in Monroe (SEP-gated). B-1/B-2/LOR not grounded (self-storage = x; no industrial).

municipality='Monroe' (exact parcels.city). human_reviewed=true.
Run: python scripts/_apply_fairfieldct_monroe.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "66230887-aabe-4d62-aebb-856939ba77bb"
MUNI = "Monroe"
ORD = ("Town of Monroe CT Zoning Regulations (amended thru 7/2/2026), Article 10 Schedule of "
       "Permitted Land Uses (monroect.gov)")
_SEP_Q = ('Art. 10 §10.1 schedule: "Self-Storage Warehousing for Rental of Fully Interior '
          'Enclosed Building Space" = SEP in {zc}; "Manufacturing, Processing and/or Assembly '
          '... Fully Enclosed Buildings" = SEP in {zc}.')
_X_Q = ('Art. 10 §10.1 schedule: "Self-Storage Warehousing ..." = "x" (not permitted) in {zc}; '
        'manufacturing = SEP in {zc}.')
VERDICTS = {
    "SB-2": ("SB-2 Stevenson Business", "conditional", "conditional", "conditional",
             "prohibited", 0.90, _SEP_Q,
             "self_storage/mini_warehouse CONDITIONAL (NAMED special exception). "
             "light_industrial CONDITIONAL (manufacturing SEP, not by-right). "
             "luxury_garage_condo PROHIBITED (unnamed, #58)."),
    "I-2": ("I-2 Industrial 2", "conditional", "conditional", "conditional", "prohibited",
            0.90, _SEP_Q,
            "self_storage/mini_warehouse CONDITIONAL (NAMED special exception). "
            "light_industrial CONDITIONAL (manufacturing SEP). luxury_garage_condo PROHIBITED."),
    "I-1": ("I-1 Industrial 1", "prohibited", "prohibited", "conditional", "prohibited",
            0.88, _X_Q,
            "self_storage/mini_warehouse PROHIBITED (schedule 'x'). light_industrial CONDITIONAL "
            "(manufacturing SEP). luxury_garage_condo PROHIBITED."),
    "I-3": ("I-3 Industrial 3", "prohibited", "prohibited", "conditional", "prohibited",
            0.88, _X_Q,
            "self_storage/mini_warehouse PROHIBITED (schedule 'x'). light_industrial CONDITIONAL "
            "(manufacturing SEP). luxury_garage_condo PROHIBITED."),
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
        assert jn and "Fairfield County" in jn, f"unexpected jurisdiction: {jn!r}"
        print(f"jurisdiction: {jn}  municipality: {MUNI}")
        await con.execute("SET statement_timeout = '60s'")
        for zc, (zname, ss, mw, li, lgc, conf, qt, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": "Art. 10 §10.1",
                                 "quote": qt.format(zc=zc)}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, "Art. 10 §10.1",
                              conf, f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Monroe rows:")
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} mw={r['mw']:11} li={r['li']:11} "
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
            print(f"  {r['zoning_code']:5} parcels={r['n']:>4} >=1.5ac={r['ge15']:>3} needles={r['needles']:>3}")
    finally:
        await con.close()


asyncio.run(main())
