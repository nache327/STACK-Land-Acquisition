"""Contra Costa CA — normalize verbose descriptive zoning_code strings to their leading code token
(coordinator-authorized). The source GIS stored full names ("IB Industrial Business", "RL2 Single Family
Low Density Residential", "CM-5 Commercial Mixed-Use Activity Center", ...) as zoning_code for Richmond /
San Pablo / El Cerrito / El Sobrante / (unincorporated). These trip the post-ingest gate's over-length
check (_MAX_CODE_LEN=20) and are the cause of the batch-1 gate FAIL.

Pattern: normalize only codes matching `^[^ ]+ [A-Z][a-z]` (a code token + space + a Capitalized
description word) -> keep only the leading token (split on first space). This SKIPS combining/overlay
codes ("A-2 -BS", "C -CE", "H-I -X", "P-1 (R-40)", "HPUD 279", "B-1 PUD") whose remainder starts with a
hyphen / "(" / all-caps — verified: 29 verbose codes normalize (21,458 parcels); no >20 code escapes; no
normalized token exceeds 20 chars. Deterministic + idempotent.

Run: cd backend && PYTHONUTF8=1 python scripts/_normalize_contra_costa_codes.py [--apply]
"""
import asyncio, sys, asyncpg

JID = "7ad622d4-0d36-4fe5-ad8b-53352bdac162"
PAT = r"^[^ ]+ [A-Z][a-z]"


async def main(apply: bool):
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=90, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        preview = await con.fetch(
            "SELECT zoning_code zc, split_part(zoning_code,' ',1) norm, count(*) n "
            "FROM parcels WHERE jurisdiction_id=$1 AND zoning_code ~ $2 GROUP BY zc ORDER BY zc", JID, PAT)
        print(f"{len(preview)} verbose codes -> leading token ({sum(r['n'] for r in preview)} parcels):")
        for r in preview:
            print(f"  '{r['zc']}' -> '{r['norm']}' ({r['n']})")
        if not apply:
            print("\n[DRY RUN] pass --apply to write.")
            return
        res = await con.execute(
            "UPDATE parcels SET zoning_code = split_part(zoning_code,' ',1), updated_at=now() "
            "WHERE jurisdiction_id=$1 AND zoning_code ~ $2", JID, PAT)
        print(f"\n=== normalized: {res} ===")
        left = await con.fetchval(
            "SELECT count(DISTINCT zoning_code) FROM parcels WHERE jurisdiction_id=$1 AND length(zoning_code)>20", JID)
        print(f"remaining zoning_code >20 chars: {left}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
