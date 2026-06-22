"""Doylestown BOROUGH (Bucks County PA) — self-storage verdicts. Borough of Doylestown Table of
Use Regulations (§406), pasted. catch #38: Borough (not Township); codes CI/PI present in parcels.

No explicit self-storage/mini-storage use. Self-storage maps to Use (56) Warehousing:
  (56) Warehousing = SE in CI and PI only (N everywhere else).
  (55) Wholesale and Storage = SE in CI/PI; Manufacturing (57)=P, Laboratory (58)=P in CI/PI.
  -> CI = conditional, PI = conditional (warehousing/storage by special exception; self-storage
     unnamed but is a warehousing use -> SE -> conditional). conf 0.85. light_industrial permitted.
  -> all other zones: Warehousing (56) = N -> self_storage PROHIBITED. conf 0.90.

HELD: R-4 (not in the Borough use table). Muni-specific 'Doylestown Borough' (Bucks), human-UPSERT (#29).
Run: python scripts/_apply_doylestown_borough_bucks.py
"""
import asyncio, json, asyncpg
JID="b5fb97a5-39f5-4aed-8701-494eab075c97"; MUNI="Doylestown Borough"
TBL="Doylestown Borough Table of Use Regulations (§406)"
COND=(f"{TBL}: Use (56) Warehousing = SE + (55) Wholesale and Storage = SE; self-storage unnamed -> warehousing use -> special exception -> conditional; Manufacturing (57)/Lab (58) = P",0.85)
VERDICTS={"CI":("conditional","permitted",*COND),"PI":("conditional","permitted",*COND)}
for z in ["CC","CR","CRH","O","R-1","R-2","R-3","R2A","RC","RC-1","FC","TND-1","TND-2"]:
    VERDICTS[z]=("prohibited","unclear",f"{TBL}: Use (56) Warehousing = N in {z}; self-storage not a permitted use; silence/explicit-N",0.90)
SQL="""
INSERT INTO zone_use_matrix
 (jurisdiction_id, zone_code, zone_name, municipality, self_storage, mini_warehouse,
  light_industrial, luxury_garage_condo, citations, cited_subsection, confidence,
  human_reviewed, classification_source, notes, created_at, updated_at)
VALUES ($1,$2,$3,$8,$4::use_permission_enum,$4::use_permission_enum,$5::use_permission_enum,'unclear',
  $6::jsonb,$7,$9,true,'human',$10,now(),now())
ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
DO UPDATE SET self_storage=EXCLUDED.self_storage, mini_warehouse=EXCLUDED.mini_warehouse,
  light_industrial=EXCLUDED.light_industrial, citations=EXCLUDED.citations, cited_subsection=EXCLUDED.cited_subsection,
  confidence=EXCLUDED.confidence, human_reviewed=true, classification_source='human', notes=EXCLUDED.notes, updated_at=now()
"""
async def main():
    url=[l.split("=",1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0].replace("postgresql+asyncpg://","postgresql://")
    con=await asyncpg.connect(url,timeout=40,statement_cache_size=0)
    try:
        jn=await con.fetchval("SELECT name FROM jurisdictions WHERE id=$1",JID); assert "Bucks" in jn
        await con.execute("SET statement_timeout='60s'")
        for zc,(ss,li,cite,conf) in VERDICTS.items():
            cites=json.dumps([{"ordinance":"Doylestown Borough Zoning","section":"Table of Use Regs (56) Warehousing","basis":f"self_storage={ss} in {zc}"}])
            await con.execute(SQL,JID,zc,f"Doylestown Boro {zc}",ss,li,cites,cite,MUNI,conf,f"{zc}: self_storage {ss}. {cite}")
        rows=await con.fetch("SELECT zone_code, self_storage::text ss, confidence, human_reviewed hr FROM zone_use_matrix WHERE jurisdiction_id=$1 AND municipality=$2 AND deleted_at IS NULL ORDER BY self_storage, zone_code",JID,MUNI)
        print(f"applied {len(rows)} Doylestown Borough rows:")
        for r in rows: print(f"  {r['zone_code']:6} self_storage={r['ss']:11} conf={r['confidence']} hr={r['hr']}")
    finally: await con.close()
asyncio.run(main())
