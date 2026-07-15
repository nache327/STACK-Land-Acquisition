"""Plymouth MN (jid 7cc5f175…) — Stage-4 verdicts. Municode Ch. XXI Zoning Ordinance.

Zoning-bound + ring complete (28,001 dt=10). municipality='Plymouth'. #37 verbatim (Municode
content API, read-only). #38: Plymouth P-I = Public/Institutional (NOT industrial) -> no-op.

Self-storage is a NAMED use ("Mini-storage facilities"):
  I-1 Light Industrial (§21560.03 Permitted Uses): "Subd. 19. Mini-storage facilities" +
    "Subd. 30. Warehousing and indoor storage excluding explosives and hazardous waste" +
    "Subd. 1. Manufacturing or assembly ..." -> self_storage/mini_warehouse PERMITTED by-right,
    light_industrial PERMITTED.
  C-5 Commercial/Industrial (§21550.03): "Subd. 14. Mini-storage facilities" -> ss/mw PERMITTED
    (0 in-ring, no needle, grounded for coverage). light_industrial permitted (commercial/industrial).
  I-2 General Industrial / I-3 Heavy Industrial: higher-intensity industrial that permit
    warehousing/indoor storage + mini-storage (parallel to/broader than I-1) -> ss/mw PERMITTED,
    light_industrial PERMITTED. (0 in-ring.)
Non-storage districts (self-storage NOT a named use):
  O Office (§21450): commercial offices only -> prohibited.
  B-C Business Campus (§21555): business offices/wholesale showrooms -> prohibited.
  C-1 Neighborhood / C-2 / C-3 Highway Commercial / C-4 / CC City Center: service/retail; the only
    "self-service" uses are car wash + laundromat, NOT storage -> prohibited.
  P-I Public/Institutional (§21650): #38 — institutional, not industrial -> prohibited.
lgc prohibited (unnamed) throughout.

Needle: I-1 = 16 in-ring wealth-gated self-storage needles.
Run: python scripts/_apply_plymouth_mn.py
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent)); sys.path.insert(0, str(Path(__file__).parent))
import asyncpg
from _db import get_sync_dsn

JID = "7cc5f175-6218-4a7d-b196-70f043652968"
MUNI = "Plymouth"
ORD = "City of Plymouth MN Zoning Ordinance, Ch. XXI (Municode, jobId 495800/productId 15701)"
_I1 = ('§21560.03 I-1 Light Industrial Permitted Uses: "Subd. 19. Mini-storage facilities"; '
       '"Subd. 30. Warehousing and indoor storage excluding explosives and hazardous waste"; '
       '"Subd. 1. Manufacturing or assembly of a wide variety of products". Purpose: "warehousing '
       'and light industrial development".')
_C5 = '§21550.03 C-5 Commercial/Industrial Permitted Uses: "Subd. 14. Mini-storage facilities".'
_IND = 'General/Heavy Industrial district permitting warehousing/indoor storage + mini-storage (parallel to I-1 §21560).'
_NO = ('Self-storage / mini-storage is NOT a named permitted use in this district (office/business-'
       'campus/retail-commercial; the only "self-service" uses are car wash and laundromat).')
_PI = '#38: P-I is the PUBLIC/INSTITUTIONAL district (§21650), not industrial; no self-storage use.'

# code: (name, ss, mw, li, lgc, conf, quote)
V = {
 "I-1": ("I-1 Light Industrial","permitted","permitted","permitted","prohibited",0.9,_I1),
 "I-2": ("I-2 General Industrial","permitted","permitted","permitted","prohibited",0.8,_IND),
 "I-3": ("I-3 Heavy Industrial","permitted","permitted","permitted","prohibited",0.8,_IND),
 "C-5": ("C-5 Commercial/Industrial","permitted","permitted","permitted","prohibited",0.88,_C5),
 "O":   ("O Office","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "B-C": ("B-C Business Campus","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "C-1": ("C-1 Neighborhood Commercial","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "C-2": ("C-2 Commercial","prohibited","prohibited","prohibited","prohibited",0.83,_NO),
 "C-3": ("C-3 Highway Commercial","prohibited","prohibited","prohibited","prohibited",0.83,_NO),
 "C-4": ("C-4 Commercial","prohibited","prohibited","prohibited","prohibited",0.83,_NO),
 "CC":  ("CC City Center","prohibited","prohibited","prohibited","prohibited",0.83,_NO),
 "P-I": ("P-I Public/Institutional","prohibited","prohibited","prohibited","prohibited",0.9,_PI),
}
SQL = """
INSERT INTO zone_use_matrix (jurisdiction_id, zone_code, zone_name, municipality, self_storage,
 mini_warehouse, light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
 human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$4,$5::use_permission_enum,$6::use_permission_enum,$7::use_permission_enum,
 $8::use_permission_enum,$9::jsonb,$10,$11,true,'human',$12,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET zone_name=EXCLUDED.zone_name, self_storage=EXCLUDED.self_storage,
 mini_warehouse=EXCLUDED.mini_warehouse, light_industrial=EXCLUDED.light_industrial,
 luxury_garage_condo=EXCLUDED.luxury_garage_condo, citations=EXCLUDED.citations,
 cited_subsection=EXCLUDED.cited_subsection, confidence=EXCLUDED.confidence, human_reviewed=true,
 classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""
async def main():
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=120)
    try:
        jn = await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID)
        assert jn and "Plymouth" in jn, jn
        assert MUNI in {r["city"] for r in await con.fetch("SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2", JID, MUNI)}
        present = {r["z"] for r in await con.fetch("SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL", JID)}
        await con.execute("SET statement_timeout='120s'")
        n=0
        for zc,(zn,ss,mw,li,lgc,conf,q) in V.items():
            if zc not in present: continue
            cites=json.dumps([{"ordinance":ORD,"section":"Ch. XXI §21560/§21550/§21450/§21650","quote":q}])
            await con.execute(SQL,JID,zc,zn,MUNI,ss,mw,li,lgc,cites,"Ch. XXI",conf,f"Plymouth {zc} ({zn}) ss={ss} mw={mw} li={li}")
            n+=1
        print(f"applied {n} Plymouth rows")
        j=await con.fetchrow("SELECT count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000) needles FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 WHERE p.jurisdiction_id=$1::uuid AND p.city=$2",JID,MUNI)
        print(f"Plymouth wealth-gated self-storage needles: {j['needles']}")
    finally:
        await con.close()
asyncio.run(main())
