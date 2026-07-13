"""Town of Newtown (Fairfield County, CT — county_gis jid) — Stage-4 verdicts.

Grounds Newtown's five industrial (M) districts against the Town Zoning
Regulations (Feb 2024, town PDF), Article V. Parcels rebound first via
rebind_configs/newtown.json off the MapXpress layer (10,993 rebound). Newtown
clears the wealth gate (~77% ring coverage). Closed-list per-zone (§5.0x.210:
"Uses that are not listed ... shall not be permitted by variance").

Self-storage is a NAMED use — grounded on explicit placement (catch #37):
  M-2A (§5.03): §5.03.330 "Self Storage Facility" = Special Exception use.
  M-4  (§5.05): §5.05.360 "Self-Storage Facility" = Special Exception use.
  M-5  (§5.06): §5.06.420 "Self-service storage facility ..." = Special Exception use.
  M-1  (§5.02) / M-3 (§5.04): self-storage ABSENT (not a listed use).
Light manufacturing is by-right in every M-zone (§5.0x.230 "Light industrial use
including manufacturing ... conducted solely within an enclosed building").
Warehouse is by-right in M-1/M-3/M-4/M-5 (SE in M-2A) — not self-storage.

Verdicts (municipality='Newtown'):
  M-2A / M-4 / M-5: self_storage / mini_warehouse = CONDITIONAL (0.90, NAMED special
    exception); light_industrial = PERMITTED (0.90, by right §5.0x.230);
    luxury_garage_condo = PROHIBITED (0.85, unnamed -> closed-list sweep #58).
  M-1 / M-3: self_storage / mini_warehouse = PROHIBITED (0.88, absent -> closed list);
    light_industrial = PERMITTED (0.90); luxury_garage_condo = PROHIBITED (0.85).

catch #58: self_storage NAMED and grounded on placement; unnamed uses (luxury_garage_condo)
swept to prohibited, never inferred. catch #57: affirmative special-exception listing beats
silence. (I-2 and the B/BPO districts not grounded here — I-2 not in the Art. V M-series use
analysis; business districts have no self-storage.)

municipality='Newtown' (exact parcels.city). human-UPSERT, verbatim citations,
human_reviewed=true. Run: python scripts/_apply_fairfieldct_newtown.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "66230887-aabe-4d62-aebb-856939ba77bb"  # Fairfield County, CT (county_gis)
MUNI = "Newtown"
ORD = ("Town of Newtown CT Zoning Regulations (Feb 2024), Article V Industrial Districts "
       "(newtown-ct.gov/.../pz_regulations_feb_2024.pdf)")

_SE = ("conditional", "conditional", "permitted", "prohibited", 0.90)
_ABS = ("prohibited", "prohibited", "permitted", "prohibited", 0.88)
VERDICTS = {
    "M-2A": ("M-2A Industrial", *_SE, "§5.03.330",
             '§5.03.330 "Self Storage Facility" listed under §5.03.300 Special Exception Uses; '
             'light industrial by right §5.03.230.',
             "self_storage/mini_warehouse CONDITIONAL (NAMED special exception §5.03.330). "
             "light_industrial PERMITTED by right (§5.03.230). luxury_garage_condo PROHIBITED "
             "(unnamed, closed-list #58)."),
    "M-4": ("M-4 Industrial", *_SE, "§5.05.360",
            '§5.05.360 "Self-Storage Facility" under §5.05.300 Special Exception Uses; light '
            'industrial by right §5.05.230; warehouse by right §5.05.280.',
            "self_storage/mini_warehouse CONDITIONAL (NAMED special exception §5.05.360). "
            "light_industrial PERMITTED (§5.05.230). luxury_garage_condo PROHIBITED (#58)."),
    "M-5": ("M-5 Industrial", *_SE, "§5.06.420",
            '§5.06.420 "Self-service storage facility ..." under §5.06.400 Special Exception '
            'Uses; light industrial by right §5.06.230; warehouse by right §5.06.280.',
            "self_storage/mini_warehouse CONDITIONAL (NAMED special exception §5.06.420). "
            "light_industrial PERMITTED (§5.06.230). luxury_garage_condo PROHIBITED (#58)."),
    "M-1": ("M-1 Industrial", *_ABS, "§5.02",
            'Article V §5.02: self-storage is NOT a listed use in M-1 (permitted §5.02.200 or '
            'special exception); light industrial by right §5.02.230; warehouse by right §5.02.280.',
            "self_storage/mini_warehouse PROHIBITED (absent; closed-list per-zone). "
            "light_industrial PERMITTED (§5.02.230). luxury_garage_condo PROHIBITED."),
    "M-3": ("M-3 Industrial", *_ABS, "§5.04",
            'Article V §5.04 (20-acre min): self-storage NOT listed; light industrial by right '
            '§5.04.230; warehouse by right §5.04.260.',
            "self_storage/mini_warehouse PROHIBITED (absent; closed-list). light_industrial "
            "PERMITTED (§5.04.230). luxury_garage_condo PROHIBITED."),
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
        for zc, (zname, ss, mw, li, lgc, conf, sec, quote, note) in VERDICTS.items():
            cites = json.dumps([{"ordinance": ORD, "section": sec, "quote": quote}])
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, sec, conf,
                              f"{zc} ({zname}) — {note}")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, mini_warehouse::text mw, "
            "light_industrial::text li, luxury_garage_condo::text lgc, confidence conf "
            "FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid AND municipality=$2 "
            "AND deleted_at IS NULL ORDER BY zone_code", JID, MUNI)
        print(f"applied {len(rows)} Newtown rows:")
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
