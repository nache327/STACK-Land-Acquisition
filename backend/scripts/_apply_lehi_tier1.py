"""Lehi, UT — Tier-1 zoning correction (user-greenlit 2026-06-09).
Flips light_industrial unclear->permitted for LI and C-H, the two zones whose
columns are unique multi-char codes the verifier could trace with confidence
(Light Manufacturing/Processing/Assembly = P; LI also Warehousing = P).
Tier-2 conditional flips (CR/MU/T-M/HI mini_warehouse + light_industrial) HELD
pending PDF visual confirmation. luxury_garage_condo untouched (already correct:
C-H/LI permitted, rest prohibited — matches user's visual verification)."""
import asyncio, asyncpg
JID="038e93cf-4457-4f74-825d-d78f241e4724"
EVID={
 "LI":"LI light_industrial=permitted: Light Manufacturing/Processing/Assembly=P AND Warehousing & Wholesale Distribution=P in LI column (Lehi Table 05.030-B Nonresidential Zones)",
 "C-H":"C-H light_industrial=permitted: Light Manufacturing/Processing/Assembly=P in C-H column (Lehi Table 05.030-B Nonresidential Zones)",
}
def dburl():
    for line in open(".env", encoding="utf-8"):
        if line.startswith("DATABASE_URL="):
            return line.split("=",1)[1].strip().strip('"').replace("postgresql+asyncpg://","postgresql://")
async def main():
    c=await asyncpg.connect(dburl(), statement_cache_size=0)
    async with c.transaction():
        for zone,ev in EVID.items():
            row=await c.fetchrow("""
              UPDATE zone_use_matrix
                 SET light_industrial='permitted',
                     human_reviewed=true,
                     classification_source='human',
                     confidence=0.900,
                     notes = COALESCE(NULLIF(notes,''),'') ||
                             CASE WHEN COALESCE(notes,'')='' THEN '' ELSE ' | ' END || $3,
                     updated_at=now()
               WHERE jurisdiction_id=$1 AND municipality IS NULL
                 AND zone_code=$2 AND deleted_at IS NULL
              RETURNING zone_code, light_industrial::text, confidence, human_reviewed, classification_source::text""",
              JID, zone, ev)
            print(f"updated {row['zone_code']}: light_industrial={row['light_industrial']} conf={row['confidence']} hr={row['human_reviewed']} src={row['classification_source']}")
    await c.close()
asyncio.run(main())
