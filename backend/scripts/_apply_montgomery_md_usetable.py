"""Montgomery County MD — Self-Storage verdicts from §3.1.6 Use Table + §3.6.8.D standards.

Read from the adopted Montgomery County Zoning Ordinance (Ch.59, 2014), §3.1.6 Use Table,
Self-Storage row (key P=permitted, L=limited use, C=conditional, blank=not allowed),
cross-checked with §3.6.8.D Self-Storage use standards. Base-zone verdicts:
  IL, IM            -> permitted   (P)
  CRN, CRT, CR, GR  -> conditional (C/L; §3.6.8.D.2.a.i GR, .ii/.iii CR, .b CRN conditional)
  IH, AR, RC, RNC, TLD/TMD/THD, R*, RE*, NR, LSC, EOF -> prohibited (blank)

Applied as prefix UPDATEs over the EXISTING county-default zone_use_matrix rows (the heuristic
bootstrap already seeded one row per zone) — operates on ~197 matrix rows, NOT a 281k-parcel scan,
so it completes even while the prod DB is under load. HELD (untouched, not in the 2014 §3.1.6
table): MXD/MXCD/MXB/CBD/CD/C2/CC/I1-I4/PI/PC and any other non-zMOD code.
Run: python scripts/_apply_montgomery_md_usetable.py
"""
import asyncio
import json

import asyncpg

MM = "c64d5cd2-4164-42f4-9795-f862ea741d16"
CITE = "Montgomery County Zoning Ordinance §3.1.6 Use Table (Self-Storage) + §3.6.8.D use standards"
_CITES = json.dumps([{"ordinance": "Montgomery County MD Zoning Ordinance (2014)",
                      "section": "§3.1.6 Use Table / §3.6.8.D", "basis": "Self-Storage per §3.1.6 use table"}])

# (verdict, WHERE-predicate on zone_code) — applied to municipality IS NULL rows.
PASSES = [
    ("permitted", "(zone_code LIKE 'IL%' OR zone_code LIKE 'IM%')"),
    ("conditional", "(zone_code LIKE 'CR%' OR zone_code LIKE 'GR%')"),  # CR/CRN/CRT all conditional
    ("prohibited",
     "(zone_code LIKE 'IH%' OR zone_code LIKE 'AR%' OR zone_code LIKE 'RC%' OR zone_code LIKE 'RNC%' "
     "OR zone_code LIKE 'TMD%' OR zone_code LIKE 'TLD%' OR zone_code LIKE 'THD%' OR zone_code LIKE 'RE%' "
     "OR zone_code LIKE 'NR%' OR zone_code LIKE 'LSC%' OR zone_code LIKE 'EOF%' "
     "OR zone_code ~ '^R-?[0-9]' OR zone_code = 'R')"),
]


async def main():
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=60, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout='40s'")
        for verdict, pred in PASSES:
            sql = f"""
                UPDATE zone_use_matrix
                SET self_storage=$2::use_permission_enum, mini_warehouse=$2::use_permission_enum,
                    human_reviewed=true, classification_source='human',
                    citations=$3::jsonb, cited_subsection=$4, confidence=0.93,
                    notes='Self-storage '||$2||' (Montgomery County §3.1.6 Use Table)', updated_at=now()
                WHERE jurisdiction_id=$1 AND municipality IS NULL AND deleted_at IS NULL AND {pred}
            """
            res = await con.execute(sql, MM, verdict, _CITES, CITE)
            print(f"{verdict}: {res}")
        # report what's now human-reviewed + what's left heuristic (held)
        held = await con.fetch("""SELECT zone_code, self_storage::text ss FROM zone_use_matrix
            WHERE jurisdiction_id=$1 AND municipality IS NULL AND deleted_at IS NULL
              AND NOT human_reviewed ORDER BY zone_code""", MM)
        print(f"\nHELD (still heuristic, not in §3.1.6 table): {len(held)} -> {[r['zone_code'] for r in held]}")
        elig = await con.fetchval("""SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id=$1
            AND municipality IS NULL AND deleted_at IS NULL AND human_reviewed
            AND self_storage IN ('permitted','conditional')""", MM)
        print(f"human-reviewed needle-eligible zones now: {elig}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
