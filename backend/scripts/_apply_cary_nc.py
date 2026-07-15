"""Cary NC (in Wake jid b05b7317…) — Stage-4 verdicts. Cary LDO Table 5.1-1 via Playwright.

Wake muni bind applied Cary zoning (Phase-5). Ring done. municipality='Cary'. #37 verbatim: Cary
LDO §5.1.2 Table 5.1-1 (Table of Permitted Uses — General Use Districts, EXCEPT PDD/TC/CT), rendered
via Playwright headless (amlegal SPA; curl/WebFetch/content-API fail). Column-aligned by <td> index;
VALIDATED vs the "Office, business or professional" row (P in OI/GC/ORD/I/overlays).

Header cols (after 2 label cells): R80 R40 R20 R12 R8 TR RMF RR | OI GC ORD I | N2 C3 R4.
Legend: P=permitted, S=special use (-> conditional), blank/'-'=not permitted.

Row "Mini-storage [6]" (Warehouse & Freight Movement): **ORD = S (Special Use), I = P (Permitted)**;
OI/GC and all others blank -> not permitted. (Row "Warehousing and distribution establishment": GC=S,
ORD=P, I=P — a distinct logistics use, not self-storage.)

Verdicts (municipality='Cary'):
  ORD / ORDCU (Office/Research/Development; -CU = conditional-use overlay on same base): self_storage /
    mini_warehouse = CONDITIONAL (Mini-storage = Special Use in ORD). light_industrial = prohibited
    (office/research district; no principal light-industrial grant in the mini-storage context). -> 37
    in-ring wealth-gated needles.
  I / ICU (Industrial): self_storage / mini_warehouse = PERMITTED (Mini-storage = P), light_industrial
    permitted. (0 in-ring -> 0 needles, grounded for coverage.)
  GC / GCCU / OI / OICU / MXD: self_storage / mini_warehouse = PROHIBITED (Mini-storage blank in these
    columns — not a permitted use). light_industrial prohibited.
  lgc prohibited throughout. (PDD is excluded from Table 5.1-1 by Cary's own table -> not ground here.)

Run: python scripts/_apply_cary_nc.py
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent)); sys.path.insert(0, str(Path(__file__).parent))
import asyncpg
from _db import get_sync_dsn

JID = "b05b7317-b412-492c-a56c-433d447d17bf"
MUNI = "Cary"
ORD_ = "Town of Cary NC LDO §5.1.2 Table 5.1-1 (amlegal, rendered via Playwright); 'Mini-storage [6]' row"
_ORD = ('LDO Table 5.1-1 "Mini-storage [6]" row: ORD column = "S" (Special Use). Column-aligned by <td> '
        'index, validated vs "Office, business or professional" row (P in OI/GC/ORD/I). Special Use -> conditional.')
_I = 'LDO Table 5.1-1 "Mini-storage [6]" row: I (Industrial) column = "P" (permitted by right).'
_NO = ('LDO Table 5.1-1 "Mini-storage [6]" row: this column is blank (not a permitted or special use) -> '
       'self-storage not permitted. (Only ORD=S and I=P allow Mini-storage.)')
# code: (name, ss, mw, li, lgc, conf, quote)
V = {
 "ORD":  ("ORD Office/Research/Development","conditional","conditional","prohibited","prohibited",0.88,_ORD),
 "ORDCU":("ORD Office/Research/Development (CU overlay)","conditional","conditional","prohibited","prohibited",0.88,_ORD),
 "I":    ("I Industrial","permitted","permitted","permitted","prohibited",0.88,_I),
 "ICU":  ("I Industrial (CU overlay)","permitted","permitted","permitted","prohibited",0.88,_I),
 "GC":   ("GC General Commercial","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "GCCU": ("GC General Commercial (CU overlay)","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "OI":   ("OI Office/Institutional","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "OICU": ("OI Office/Institutional (CU overlay)","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
 "MXD":  ("MXD Mixed Use","prohibited","prohibited","prohibited","prohibited",0.85,_NO),
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
    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=180)
    try:
        assert "Wake" in (await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID))
        assert MUNI in {r["city"] for r in await con.fetch("SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2", JID, MUNI)}
        present = {r["z"] for r in await con.fetch("SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2 AND zoning_code IS NOT NULL", JID, MUNI)}
        await con.execute("SET statement_timeout='180s'"); n=0
        for zc,(zn,ss,mw,li,lgc,conf,q) in V.items():
            if zc not in present: continue
            cites=json.dumps([{"ordinance":ORD_,"section":"LDO Table 5.1-1","quote":q}])
            await con.execute(SQL,JID,zc,zn,MUNI,ss,mw,li,lgc,cites,"LDO Table 5.1-1",conf,f"Cary {zc} ({zn}) ss={ss} mw={mw} li={li}"); n+=1
        print(f"applied {n} Cary rows")
        j=await con.fetchrow("SELECT count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000) needles FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 WHERE p.jurisdiction_id=$1::uuid AND p.city=$2",JID,MUNI)
        print(f"Cary wealth-gated self-storage needles: {j['needles']}")
    finally:
        await con.close()
asyncio.run(main())
