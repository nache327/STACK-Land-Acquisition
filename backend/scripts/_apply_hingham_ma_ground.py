"""Town of Hingham (Hingham, MA — single-town jid) — Stage-4 human verdicts.

(Distinct from the old wave-6 substrate seeder _apply_hingham_ma.py — this is the grounding.)

Zoning-bound already (MassGIS codes, "131"+district). Ring-precompute complete (7,610 dt=10,
ALL wealth-pass — uniformly wealthy town). Grounds against the Hingham Zoning By-Law (revised
through April 29, 2025), Section III-A Schedule of Uses. #37 verbatim basis.

Legend (III-A): P = permitted; A1/A2/A3 = Special Permit (by named board); O = not permitted.
Column order: RA RB RC RD RE | BA BB | OP | WB | WR | I | IP | LIP | BR | OO.

Self-storage is NOT a separately named use; the storage/warehouse uses are:
  4.14 "Freight terminal or storage warehouse": P in BB, I, IP (by-right); O in LIP.
  6.1  "Wholesale warehouse, incl. office/showroom": BA=P, BB=P, OP=A2, I=P, IP=P, LIP=A2.
  6.2  "Light industrial uses, including manufacturing, storage, processing, fabrication,
        packaging, and assembly": OP=A2, I=P, IP=P, LIP=A2 (else O).
Warehouse/storage permitted by-right in I, IP (and BB storage-warehouse) -> warehouse-by-right
convention -> self_storage/mini_warehouse CONDITIONAL. In LIP/OP the storage/warehouse uses are
Special-Permit (A2) -> CONDITIONAL. This matches Hingham's own practice: the Board of Appeals has
permitted self-storage facilities in the Industrial and Limited Industrial Park districts by
Special Permit A2. lgc PROHIBITED (unnamed).

Run: python scripts/_apply_hingham_ma_ground.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "4208af9b-5a97-4ca8-9b77-43aac5b58fb2"
MUNI = "Hingham"
ORD = ("Town of Hingham MA Zoning By-Law (revised through April 29, 2025), Section III-A "
       "Schedule of Uses (hingham-ma.gov)")
_IND_Q = ('III-A uses 4.14 "Freight terminal or storage warehouse" (P in I, IP) and 6.2 "Light '
          'industrial uses, including manufacturing, storage, processing, fabrication, packaging, '
          'and assembly" (P in I, IP). Warehouse/storage permitted by-right -> self_storage/'
          'mini_warehouse conditional (warehouse-by-right convention; Board grants self-storage by '
          'Special Permit A2 in these districts). light_industrial permitted (6.2 by-right).')
_LIP_Q = ('III-A uses 6.1 "Wholesale warehouse" and 6.2 "Light industrial … storage" = "A2" (Special '
          'Permit) in LIP. Storage/warehouse by Special Permit -> self_storage/mini_warehouse '
          'conditional; light_industrial conditional. Matches Board grants of self-storage in the '
          'Limited Industrial Park district by Special Permit A2.')
_OP_Q = ('III-A uses 6.1 "Wholesale warehouse" and 6.2 "Light industrial … storage" = "A2" (Special '
         'Permit) in Office Park -> self_storage/mini_warehouse conditional; light_industrial conditional.')
_BB_Q = ('III-A use 4.14 "storage warehouse" = P (by-right) in Business B -> self_storage/mini_warehouse '
         'conditional (warehouse-by-right convention). light_industrial prohibited (6.2 BB=O).')
_BA_Q = ('III-A: Business A permits only 6.1 "Wholesale warehouse" (=P) — a wholesale/distribution '
         'logistics use (Berkeley-Heights warehouse-vs-wholesale rule), NOT customer self-storage; '
         '4.14 storage-warehouse = O in BA. Self-storage not named -> prohibited.')
_NO_Q = ('III-A: no storage/warehouse/self-storage use permitted (4.14/6.1/6.2 = O). Self-storage '
         'not permitted -> prohibited.')

V = {
    "131I":  ("I Industrial", "conditional", "conditional", "permitted", "prohibited", 0.86, "III-A 4.14/6.2", _IND_Q),
    "131IP": ("IP Industrial Park", "conditional", "conditional", "permitted", "prohibited", 0.86, "III-A 4.14/6.2", _IND_Q),
    "131LIP":("LIP Limited Industrial Park", "conditional", "conditional", "conditional", "prohibited", 0.85, "III-A 6.1/6.2", _LIP_Q),
    "131BB": ("BB Business B", "conditional", "conditional", "prohibited", "prohibited", 0.83, "III-A 4.14", _BB_Q),
    "131OP": ("OP Office Park", "conditional", "conditional", "conditional", "prohibited", 0.80, "III-A 6.1/6.2", _OP_Q),
    "131BA": ("BA Business A", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, "III-A 6.1/4.14", _BA_Q),
    "131BR": ("BR Business Recreation", "prohibited", "prohibited", "prohibited", "prohibited", 0.85, "III-A", _NO_Q),
    "131RA": ("RA Residence A", "prohibited", "prohibited", "prohibited", "prohibited", 0.9, "III-A", _NO_Q),
    "131RB": ("RB Residence B", "prohibited", "prohibited", "prohibited", "prohibited", 0.9, "III-A", _NO_Q),
    "131RC": ("RC Residence C", "prohibited", "prohibited", "prohibited", "prohibited", 0.9, "III-A", _NO_Q),
    "131RD": ("RD Residence D", "prohibited", "prohibited", "prohibited", "prohibited", 0.9, "III-A", _NO_Q),
    "131RE": ("RE Residence E", "prohibited", "prohibited", "prohibited", "prohibited", 0.9, "III-A", _NO_Q),
    "131OO": ("OO Official & Open Space", "prohibited", "prohibited", "prohibited", "prohibited", 0.9, "III-A", _NO_Q),
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
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=120)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Hingham" in jn, f"unexpected jurisdiction: {jn!r}"
        cities = {r["city"] for r in await con.fetch(
            "SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid", JID)}
        assert MUNI in cities, f"{MUNI!r} not in parcels.city {cities}"
        present = {r["z"] for r in await con.fetch(
            "SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid "
            "AND zoning_code IS NOT NULL", JID)}
        await con.execute("SET statement_timeout='120s'")
        applied = 0
        for zc, (zname, ss, mw, li, lgc, conf, sec, quote) in V.items():
            if zc not in present:
                continue
            cites = json.dumps([{"ordinance": ORD, "section": sec, "quote": quote}])
            note = f"{MUNI} {zc} ({zname}) — ss={ss} mw={mw} li={li} lgc={lgc}"
            await con.execute(SQL, JID, zc, zname, MUNI, ss, mw, li, lgc, cites, sec, conf, note)
            applied += 1
        print(f"applied {applied} human-reviewed Hingham rows")
        rows = await con.fetch(
            """SELECT m.zone_code, m.self_storage::text ss, m.light_industrial::text li,
                   count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000
                        AND prm.median_hhi>=100000) needles
               FROM zone_use_matrix m
               LEFT JOIN parcels p ON p.jurisdiction_id=m.jurisdiction_id AND p.zoning_code=m.zone_code
                    AND p.city=m.municipality
               LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
               WHERE m.jurisdiction_id=$1::uuid AND m.municipality=$2 AND m.human_reviewed
                 AND m.deleted_at IS NULL
               GROUP BY 1,2,3 ORDER BY needles DESC, 1""", JID, MUNI)
        tot = 0
        for r in rows:
            mark = "  <-- needle zone" if r["ss"] in ("permitted", "conditional") else ""
            print(f"  {r['zone_code']:7} ss={r['ss']:11} li={r['li']:11} needles={r['needles']}{mark}")
            if r["ss"] in ("permitted", "conditional"):
                tot += r["needles"]
        print(f"TOTAL wealth-gated self-storage needles: {tot}")
    finally:
        await con.close()


asyncio.run(main())
