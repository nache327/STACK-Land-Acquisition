"""South Charlotte NC (per-city jid c9af9445…) — Stage-4 verdicts.

Zoning-bound (Charlotte UDO + legacy conditional codes). Ring-precompute complete (4,768 dt=10,
2,265 wealth-pass). municipality='Charlotte' (exact parcels.city).

NEAR-NO-OP (Greenwich/Hudson pattern): the wealth ring here is affluent RESIDENTIAL + OFFICE +
mixed-use (South Charlotte / SouthPark-Ballantyne), not industrial. Discovery-rank of in-ring
>=1.5ac parcels: N2-B (404), OFC (47), R-*MF/PUD, MUDD (32), N1-A (28) ... and only ONE industrial
parcel in-ring (ML-1 x1). Industrial/logistics districts sit OUTSIDE the wealth ring here.

Verdicts:
  Industrial / Manufacturing-Logistics: ML-1, ML-2 (Manufacturing & Logistics), I-1 (Light
    Industrial, legacy conditional), IMU (Innovation Mixed-Use), BP (Business Park) — self_storage/
    mini_warehouse = CONDITIONAL. Basis: these districts permit warehousing/logistics by-right
    (ML = "Manufacturing & Logistics"; legacy I-1 permits warehousing/mini-warehouse) -> established
    warehouse-by-right => self_storage/mini_warehouse conditional convention. light_industrial permitted.
    lgc prohibited. (Only ML-1 has an in-ring >=1.5ac wealth parcel -> ~1 needle.)
  In-ring residential / office / mixed-use (N2-B, N1-A, R-12MF(CD), R-15MF(CD), R-12PUD, R-15PUD,
    OFC, O-15(CD), MUDD(CD), MUDD-O): self_storage/mini_warehouse = PROHIBITED — residential/office/
    mixed-use districts; self-storage is not a by-right standalone use there. Establishes the correct
    wealthy-residential no-op.

Run: python scripts/_apply_south_charlotte.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn

JID = "c9af9445-0148-4660-ac80-930bcc8a2271"
MUNI = "Charlotte"
ORD = ("City of Charlotte Unified Development Ordinance (UDO, eff. 2023) + legacy conditional zoning; "
       "Manufacturing & Logistics (Art. 8 ML) / Innovation Mixed-Use (Art. 9 IMU) / legacy I-1")
_IND_Q = ('Manufacturing & Logistics (ML-1/ML-2) and legacy Light Industrial (I-1) districts permit '
          'warehousing/logistics by-right (ML = "Manufacturing & Logistics"; legacy I-1 permits '
          'warehousing and mini-warehouse). Established warehouse-by-right => self_storage/mini_warehouse '
          'conditional convention. light_industrial permitted.')
_NO_Q = ('Residential / office / mixed-use district (Charlotte UDO neighborhood N1/N2, residential '
         'R-*MF/PUD, office OFC/O-*, mixed-use MUDD). Self-service storage is not a by-right standalone '
         'principal use here -> prohibited (wealthy-residential/office no-op).')

# (zone_code, ss, mw, li, lgc, conf, quote)
IND = ["ML-1", "ML-2", "I-1(CD)", "I-1(CD)(ANDO)", "ML-1(ANDO)", "ML-2(ANDO)", "IMU", "BP(CD)"]
NO_OP = ["N2-B", "N1-A", "N1-B", "R-12MF(CD)", "R-15MF(CD)", "R-8MF(CD)", "R-12PUD", "R-15PUD",
         "OFC", "OFC(HDO)", "O-15(CD)", "O-1(CD)", "MUDD(CD)", "MUDD-O", "UR-2(CD)", "INST(CD)",
         "B-1SCD", "NS"]

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
        assert jn and "Charlotte" in jn, f"unexpected jurisdiction: {jn!r}"
        assert MUNI in {r["city"] for r in await con.fetch(
            "SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2", JID, MUNI)}
        present = {r["z"] for r in await con.fetch(
            "SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid "
            "AND zoning_code IS NOT NULL", JID)}
        await con.execute("SET statement_timeout='120s'")
        n = 0
        for zc in IND:
            if zc not in present:
                continue
            cites = json.dumps([{"ordinance": ORD, "section": "Art. 8 ML / Art. 9 IMU / legacy I-1", "quote": _IND_Q}])
            await con.execute(SQL, JID, zc, f"{zc} (industrial/logistics)", MUNI, "conditional",
                              "conditional", "permitted", "prohibited", cites, "Art. 8/9 / legacy I-1",
                              0.75, f"Charlotte {zc} — ss/mw conditional (warehouse-by-right convention), li permitted")
            n += 1
        for zc in NO_OP:
            if zc not in present:
                continue
            cites = json.dumps([{"ordinance": ORD, "section": "UDO use matrix", "quote": _NO_Q}])
            await con.execute(SQL, JID, zc, f"{zc} (residential/office/mixed)", MUNI, "prohibited",
                              "prohibited", "prohibited", "prohibited", cites, "UDO use matrix", 0.82,
                              f"Charlotte {zc} — self_storage prohibited (residential/office/mixed no-op)")
            n += 1
        print(f"applied {n} South Charlotte rows")
        j = await con.fetchrow(
            "SELECT count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 "
            "  AND prm.median_hhi>=100000) needles "
            "FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id "
            "AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL "
            "AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') "
            "LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 "
            "WHERE p.jurisdiction_id=$1::uuid AND p.city=$2", JID, MUNI)
        print(f"South Charlotte wealth-gated self-storage needles: {j['needles']} (near-no-op expected)")
    finally:
        await con.close()


asyncio.run(main())
