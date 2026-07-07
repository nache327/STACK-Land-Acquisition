"""Catch #51 — detect + reclassify SENTINEL zone codes for a jurisdiction.

Generic family tool (constraint 3), not an 'INC' special case:
  1. DETECT: any all-caps token <=6 chars covering > --threshold (default 25%)
     of a jurisdiction's coded parcels whose classification comes only from
     generic heuristics (i.e. in SENTINEL_ZONE_CODES, or unmatched by the
     explicit keyword/pattern rules) is reported as a sentinel candidate.
  2. RECLASSIFY (--apply CODE ...): batched parcels.zone_class -> 'unknown'
     for those codes; the county-wide zone_use_matrix rows for those codes are
     DEMOTED (verdicts -> 'unclear', note appended) — never deleted, so the
     2.2 gate serves them as unclear_verdict, not as leads.

USAGE:
  python scripts/reclassify_sentinel_codes.py --jurisdiction <uuid>            # detect only
  python scripts/reclassify_sentinel_codes.py --jurisdiction <uuid> --apply INC
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg

from _db import get_sync_dsn  # noqa: E402
from app.services.classification import SENTINEL_ZONE_CODES  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", required=True)
    ap.add_argument("--threshold", type=float, default=0.25)
    ap.add_argument("--apply", nargs="*", default=None, metavar="CODE")
    ap.add_argument("--batch", type=int, default=50000)
    a = ap.parse_args()

    con = await asyncpg.connect(get_sync_dsn(), statement_cache_size=0, command_timeout=7200)
    try:
        await con.execute("SET statement_timeout = 0")
        rows = await con.fetch("""
            SELECT zoning_code, count(*) n,
                   count(*)::float / SUM(count(*)) OVER () AS share
            FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 20""", a.jurisdiction)
        print("top codes:")
        cands = []
        for r in rows:
            code = r["zoning_code"]
            flag = ""
            if code.strip().upper() in SENTINEL_ZONE_CODES or (
                r["share"] > a.threshold and code.isupper() and len(code) <= 6):
                flag = "  <-- SENTINEL CANDIDATE"
                cands.append(code)
            print(f"  {code:<10} {r['n']:>9,}  {r['share']*100:5.1f}%{flag}")
        if not a.apply:
            print(f"\ncandidates: {cands} — rerun with --apply <codes> to reclassify")
            return

        for code in a.apply:
            total = 0
            while True:
                st = await con.execute(f"""
                    UPDATE parcels SET zone_class = 'unknown'
                    WHERE id IN (SELECT id FROM parcels
                        WHERE jurisdiction_id=$1::uuid AND zoning_code=$2
                          AND zone_class IS DISTINCT FROM 'unknown' LIMIT {int(a.batch)})
                """, a.jurisdiction, code)
                n = int(st.split()[-1]); total += n
                print(f"  [{code}] parcels reclassified +{n:,} (total {total:,})", flush=True)
                if n < a.batch:
                    break
            # demote (never delete) the county-wide matrix rows for this code
            demoted = await con.execute("""
                UPDATE zone_use_matrix
                SET self_storage='unclear', mini_warehouse='unclear',
                    light_industrial='unclear', luxury_garage_condo='unclear',
                    notes = COALESCE(notes,'') || ' | catch #51: sentinel code demoted to unclear (not a zoning district)'
                WHERE jurisdiction_id=$1::uuid AND zone_code=$2
                  AND deleted_at IS NULL AND human_reviewed = false
                  AND classification_source NOT IN ('human','llm','llm_rule','op5_factory')
            """, a.jurisdiction, code)
            print(f"  [{code}] matrix rows demoted: {demoted.split()[-1]} (grounded rows untouched)")
    finally:
        await con.close()


asyncio.run(main())
