"""TMOH-3 needle PATCH (Holmdel/Monmouth) + Saddle River all-prohibited (Bergen).
User-greenlit 2026-06-09. TMOH-3: Route 35 overlay verified single-district
(naming variance from 'Route 35 Business Overlay'); §30-144.1(e) warehouses+
wholesale by-right + limited industrial → self_storage/mini_warehouse conditional
by convention. Saddle River: Schedule B dimensional-only, no industrial zone →
silence rule, all prohibited. Closes Bergen wealth-tail Batch 1."""
import asyncio, asyncpg
MON="703d95b4-3229-42f8-8bb1-460d46b3ceb2"
BER="4bf00234-4455-4987-a067-b22ee6b6aa1f"
TMOH_NOTE=("Transitional Mixed Highway Oriented (TMHO base) on Route 35 corridor. "
  "Route 35 overlay verified SINGLE district (Nache 'Route 35 Business Overlay' = naming variance "
  "for the one 'Route 35 Highway Overlay'/RT35H). §30-144.1 limited industrial + §30-144.1(e) "
  "warehouses & wholesale distribution by-right; self-storage unnamed -> conditional by warehouse "
  "convention; mini_warehouse conditional; light_industrial permitted; luxury_garage_condo conditional. "
  "Nache spatially confirmed 13 parcels inside overlay. Basis: prior full-ordinance parse + §-ref "
  "(live §30-144 re-read blocked by ecode360 403).")
SR_NOTE=("Saddle River Schedule B (210 Attachment 1) is dimensional-only; no use list names "
  "warehouse/self-storage; NO industrial zone exists in the borough; silence rule -> prohibited.")
SR=[("R-1","Residential 1"),("R-2","Residential 2"),("R-3","Residential 3"),
    ("PUD","Planned Unit Development"),("O-1","Office"),("B-1","Business")]
def dburl():
    for line in open(".env", encoding="utf-8"):
        if line.startswith("DATABASE_URL="):
            return line.split("=",1)[1].strip().strip('"').replace("postgresql+asyncpg://","postgresql://")
async def main():
    c=await asyncpg.connect(dburl(), statement_cache_size=0)
    async with c.transaction():
        # A) TMOH-3 PATCH
        t=await c.fetchrow("""
          UPDATE zone_use_matrix
             SET self_storage='conditional', mini_warehouse='conditional',
                 light_industrial='permitted', luxury_garage_condo='conditional',
                 human_reviewed=true, classification_source='human', confidence=0.850,
                 notes=$3, updated_at=now()
           WHERE jurisdiction_id=$1 AND municipality=$2 AND zone_code='TMOH-3' AND deleted_at IS NULL
          RETURNING zone_code, self_storage::text ss, mini_warehouse::text mw,
                    light_industrial::text li, luxury_garage_condo::text lgc, confidence""",
          MON, "Holmdel township", TMOH_NOTE)
        print(f"TMOH-3 PATCH: ss={t['ss']} mw={t['mw']} li={t['li']} lgc={t['lgc']} c={t['confidence']}")
        # B) Saddle River CREATE 6 (idempotent on the partial unique index)
        cr=0
        for code,name in SR:
            r=await c.fetchrow("""
              INSERT INTO zone_use_matrix
                (jurisdiction_id, zone_code, zone_name, municipality,
                 self_storage, mini_warehouse, light_industrial, luxury_garage_condo,
                 classification_source, confidence, human_reviewed, notes, created_at, updated_at)
              VALUES ($1,$2,$3,$4,'prohibited','prohibited','prohibited','prohibited',
                 'human',0.950,true,$5, now(), now())
              ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,''))
                WHERE deleted_at IS NULL DO NOTHING
              RETURNING zone_code""", BER, code, name, "Saddle River borough", SR_NOTE)
            if r: cr+=1; print(f"  SR create {code:6} prohibited")
            else: print(f"  SR {code:6} already existed (skipped)")
        print(f"\nSaddle River created={cr}/{len(SR)}")
    await c.close()
asyncio.run(main())
