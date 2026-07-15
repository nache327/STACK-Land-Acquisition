"""Minnetonka MN (jid 3267204b…) — Stage-4 verdicts. amlegal (Ch. 3 §300.x), fetched via Playwright.

Zoning-bound + ring complete (20,911 dt=10). municipality='Minnetonka'. #37 verbatim (amlegal
rendered via Playwright headless — curl/WebFetch/content-API all fail on the amlegal SPA).

NO-OP for self-storage. Discovery-rank in-ring >=1.5ac: B-2 (4), B-1 (3); I-1 industrial = 0 in-ring;
PID (Public/Institutional) = 0 in-ring.
  - B-1 Office Business (§300.17): only accessory "storage ... related to a permitted use ... <=10% of
    gross floor area"; no self-storage/warehouse use -> PROHIBITED.
  - B-2 Limited Business (§300.18): permitted/accessory/conditional lists name NO self-service storage
    or warehouse (accessory storage <=10% GFA; conditional "outside storage, display, sales or
    servicing" only) -> PROHIBITED. (This is the in-ring swing zone; confirmed no storage-facility use.)
  - I-1 Industrial (§300.20): "no structure or land may be used except for a cultivation, warehouse,
    storage, manufacturing, processing, office ..." -> warehouse/storage by-right -> ss/mw CONDITIONAL
    (warehouse-by-right convention), light_industrial PERMITTED. **0 in-ring -> 0 needles** (industrial
    sits outside the wealth ring here).
  lgc prohibited throughout.

Net: 0 wealth-gated self-storage needles (correct no-op — the in-ring business districts don't permit
self-storage; the industrial district that does is out of the wealth ring).
Run: python scripts/_apply_minnetonka_mn.py
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent)); sys.path.insert(0, str(Path(__file__).parent))
import asyncpg
from _db import get_sync_dsn

JID = "3267204b-fa88-45c5-bddd-3162cea4eb41"
MUNI = "Minnetonka"
ORD = "City of Minnetonka MN Code Ch. 3 Zoning (amlegal, §300.x; rendered via Playwright)"
V = {
 "B-1": ("B-1 Office Business", "prohibited","prohibited","prohibited","prohibited",0.87,"§300.17",
   '§300.17 B-1: only accessory "storage ... related to a permitted use ... occupying no more than 10 percent of the gross floor area"; no self-storage/warehouse use.'),
 "B-2": ("B-2 Limited Business", "prohibited","prohibited","prohibited","prohibited",0.85,"§300.18",
   '§300.18 B-2 permitted/accessory/conditional lists name no self-service storage or warehouse (accessory storage <=10% GFA; conditional "outside storage, display, sales or servicing" only).'),
 "I-1": ("I-1 Industrial", "conditional","conditional","permitted","prohibited",0.82,"§300.20",
   '§300.20 I-1: "no structure or land may be used except for a cultivation, warehouse, storage, manufacturing, processing, office ..." -> warehouse/storage by-right -> ss/mw conditional (warehouse-by-right convention).'),
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
        assert "Minnetonka" in (await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", JID))
        assert MUNI in {r["city"] for r in await con.fetch("SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2", JID, MUNI)}
        present = {r["z"] for r in await con.fetch("SELECT DISTINCT zoning_code z FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL", JID)}
        await con.execute("SET statement_timeout='120s'"); n=0
        for zc,(zn,ss,mw,li,lgc,conf,sec,q) in V.items():
            if zc not in present: continue
            cites=json.dumps([{"ordinance":ORD,"section":sec,"quote":q}])
            await con.execute(SQL,JID,zc,zn,MUNI,ss,mw,li,lgc,cites,sec,conf,f"Minnetonka {zc} ({zn}) ss={ss} mw={mw} li={li}"); n+=1
        print(f"applied {n} Minnetonka rows")
        j=await con.fetchrow("SELECT count(*) FILTER (WHERE p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000) needles FROM parcels p JOIN zone_use_matrix m ON m.jurisdiction_id=p.jurisdiction_id AND m.zone_code=p.zoning_code AND m.municipality=p.city AND m.deleted_at IS NULL AND m.human_reviewed AND m.self_storage IN ('permitted','conditional') LEFT JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10 WHERE p.jurisdiction_id=$1::uuid AND p.city=$2",JID,MUNI)
        print(f"Minnetonka needles: {j['needles']} (expected 0 — no-op)")
    finally:
        await con.close()
asyncio.run(main())
