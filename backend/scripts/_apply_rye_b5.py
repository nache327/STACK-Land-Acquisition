"""Apply Westchester / Rye City B-5 self_storage needle verdict (user-greenlit 2026-06-12).
B-5 Interchange Office Building: self-storage explicitly PERMITTED by special permit,
§197-86 Table B Col2(4) [Added 1-6-2021 L.L. 1-2021]. The single Westchester needle.
DO UPDATE (not DO NOTHING) per reverse-direction discipline (#13): hand verdict must
overwrite any pre-existing factory row. municipality='Rye' (matches parcels.city)."""
import asyncio, asyncpg
WC="3e706886-919f-4ecf-b5aa-567040e295e8"
NOTE=("City of Rye B-5 Interchange Office Building: self-storage explicitly PERMITTED by special "
      "permit per §197-86 Table B Col2(4) [Added 1-6-2021 L.L. No. 1-2021]. Westchester single needle "
      "(Harrison SB-*/Rye Brook OB-*/Rye B-4 all prohibited). Ground-truthed 2026-06-12.")
def dburl():
    for line in open(".env",encoding="utf-8"):
        if line.startswith("DATABASE_URL="): return line.split("=",1)[1].strip().strip('"').replace("postgresql+asyncpg://","postgresql://")
async def main():
    c=await asyncpg.connect(dburl(),statement_cache_size=0)
    r=await c.fetchrow("""
      INSERT INTO zone_use_matrix
        (jurisdiction_id, municipality, zone_code, zone_name, self_storage, mini_warehouse,
         light_industrial, luxury_garage_condo, classification_source, confidence, human_reviewed, notes, created_at, updated_at)
      VALUES ($1,'Rye','B-5','Interchange Office Building','permitted','prohibited','prohibited','prohibited',
         'human',0.90,true,$2, now(), now())
      ON CONFLICT (jurisdiction_id, zone_code, COALESCE(municipality,'')) WHERE deleted_at IS NULL
      DO UPDATE SET self_storage='permitted', mini_warehouse='prohibited', light_industrial='prohibited',
         luxury_garage_condo='prohibited', human_reviewed=true, classification_source='human',
         confidence=0.90, notes=EXCLUDED.notes, updated_at=now()
      RETURNING zone_code, municipality, self_storage::text ss, human_reviewed hr, confidence, classification_source::text src""", WC, NOTE)
    print(f"Rye B-5 applied: muni={r['municipality']} zone={r['zone_code']} self_storage={r['ss']} hr={r['hr']} conf={r['confidence']} src={r['src']}")
    await c.close()
asyncio.run(main())
