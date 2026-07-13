"""One-command batch verification for a parallel-session county batch.

Replaces the ad-hoc SQL a coordinator otherwise hand-writes per batch. Given a
jurisdiction, prints ONE consolidated report:

  1. CASING CHECK  — every human-reviewed matrix municipality must match a
     parcels.city EXACTLY (the buybox join is case-sensitive; a wrong-case row
     silently scores 0). Flags CASE_MISMATCH / NO_MATCH.
  2. NEEDLE TALLY  — wealth-gated needles by town (grounded human self_storage
     in permitted/conditional AND acres>=1.5 AND dt10 median_home_value>=475k
     AND median_hhi>=100k). NOT homes_over_1m (NULL everywhere).
  3. ON-NEEDLE COSTAR — current CoStar listings sitting on a needle parcel, by
     town + total (the digest-ready deal pool).
  4. POST-INGEST GATE — runs run_postingest_gate() and prints PASS/FAIL +
     hard failures (URL-shaped codes, domination, unclear-masquerade, catch-#58
     lgc-outranks-ss sibling leak).

USAGE (from backend/):
  python scripts/verify_batch.py --jurisdiction <jid>
  python scripts/verify_batch.py --jurisdiction <jid> --towns Bedford,Ayer   # focus

Exit code: 0 if gate PASSES and no CASE_MISMATCH/NO_MATCH; 1 otherwise — so it
can gate a merge the same way postingest_gate.py does, but with the casing +
needle context a coordinator actually reads.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402
from app.services.postingest_gate import run_postingest_gate  # noqa: E402

# Wealth-gated needle: the muni-aware LATERAL mirrors buybox_scoring's join
# (a town row wins over a NULL county-default). Keep in sync with
# _backfill_verifier_municipality.NEEDLE_SQL.
_NEEDLE_LATERAL = """
    FROM parcels p
    JOIN parcel_ring_metrics prm ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
    JOIN LATERAL (
        SELECT self_storage::text AS ss
          FROM zone_use_matrix m
         WHERE m.jurisdiction_id = p.jurisdiction_id
           AND m.zone_code = p.zoning_code
           AND (m.municipality IS NULL OR m.municipality = p.city)
           AND m.deleted_at IS NULL
           AND m.human_reviewed
         ORDER BY (m.municipality IS NULL) ASC
         LIMIT 1
    ) v ON true
   WHERE p.jurisdiction_id = $1::uuid
     AND v.ss IN ('permitted', 'conditional')
     AND p.acres >= 1.5
     AND prm.median_home_value >= 475000
     AND prm.median_hhi >= 100000
"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdiction", required=True)
    ap.add_argument("--towns", default=None, help="optional comma-list to spotlight")
    args = ap.parse_args()
    jid = args.jurisdiction
    spotlight = {t.strip() for t in args.towns.split(",")} if args.towns else None

    conn = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    problems = 0
    try:
        await conn.execute("SET statement_timeout = 0")
        jname = await conn.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", jid)
        print(f"=== verify_batch — {jname} ({jid}) ===\n")

        # 1. CASING CHECK
        cities = {
            r["city"]
            for r in await conn.fetch(
                "SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1::uuid AND city IS NOT NULL",
                jid,
            )
        }
        lower = {c.lower(): c for c in cities}
        munis = await conn.fetch(
            "SELECT DISTINCT municipality FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1::uuid AND human_reviewed AND deleted_at IS NULL "
            "AND municipality IS NOT NULL ORDER BY municipality",
            jid,
        )
        print("--- 1. CASING (human matrix municipality vs parcels.city) ---")
        if not munis:
            print("  (no muni-scoped human rows — all NULL/county-default)")
        for r in munis:
            m = r["municipality"]
            if m in cities:
                tag = "OK"
            elif m.lower() in lower:
                tag = f"CASE_MISMATCH -> parcels.city is {lower[m.lower()]!r}"
                problems += 1
            else:
                tag = "NO_MATCH (matches no parcels.city — silently scores 0)"
                problems += 1
            print(f"  {m!r}: {tag}")

        # 2. NEEDLE TALLY by town
        print("\n--- 2. WEALTH-GATED NEEDLES by town ---")
        rows = await conn.fetch(
            f"SELECT p.city, count(*) n {_NEEDLE_LATERAL} GROUP BY p.city ORDER BY n DESC", jid
        )
        total = sum(r["n"] for r in rows)
        for r in rows:
            star = "  <-" if spotlight and r["city"] in spotlight else ""
            print(f"  {r['city']}: {r['n']}{star}")
        print(f"  TOTAL needles: {total}")

        # 3. ON-NEEDLE COSTAR listings
        print("\n--- 3. ON-NEEDLE CURRENT COSTAR LISTINGS (digest-ready pool) ---")
        onrows = await conn.fetch(
            f"""SELECT p.city, count(*) n
                  FROM forsale_listings f
                  JOIN parcels p ON p.id = f.matched_parcel_id
                  JOIN parcel_ring_metrics prm ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
                  JOIN LATERAL (
                     SELECT self_storage::text AS ss FROM zone_use_matrix m
                      WHERE m.jurisdiction_id = p.jurisdiction_id AND m.zone_code = p.zoning_code
                        AND (m.municipality IS NULL OR m.municipality = p.city)
                        AND m.deleted_at IS NULL AND m.human_reviewed
                      ORDER BY (m.municipality IS NULL) ASC LIMIT 1) v ON true
                 WHERE f.jurisdiction_id = $1::uuid AND f.is_current = true
                   AND v.ss IN ('permitted','conditional') AND p.acres >= 1.5
                   AND prm.median_home_value >= 475000 AND prm.median_hhi >= 100000
                 GROUP BY p.city ORDER BY n DESC""",
            jid,
        )
        on_total = sum(r["n"] for r in onrows)
        if not onrows:
            print("  (0 — no current listing sits on a needle parcel; armed-but-waiting)")
        for r in onrows:
            print(f"  {r['city']}: {r['n']}")
        print(f"  TOTAL on-needle: {on_total}")

        # 4. POST-INGEST GATE
        print("\n--- 4. POST-INGEST GATE ---")
        rep = await run_postingest_gate(conn, jid)
        status = "PASS" if rep.passed else "FAIL"
        print(f"  [{status}] stats: {rep.stats}")
        for f in rep.hard_failures:
            print(f"  HARD FAIL: {f}")
        for w in rep.warnings:
            print(f"  warn: {w}")
        if not rep.passed:
            problems += 1

        print("\n=== SUMMARY ===")
        print(f"  needles={total}  on-needle={on_total}  gate={'PASS' if rep.passed else 'FAIL'}  "
              f"casing_problems={sum(1 for r in munis if r['municipality'] not in cities)}")
        print("  VERDICT:", "CLEAN" if problems == 0 else f"{problems} PROBLEM(S) — review above")
    finally:
        await conn.close()
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
