"""CoStar-sweep QA harness — verify one county's CoStar ingest end-to-end (read-only).

Runs the 4 QA-lane checks for a jurisdiction and emits a one-line per-county report:
  1. MATCHER DRAINED  — forsale_listings match_method IS NULL must be 0 (else re-run _match_listings_direct).
  2. ON-NEEDLE + GATE  — verify_batch section-3 on-needle tally + post-ingest gate + casing.
  3. JID-ALIGNMENT     — the trap: for per-city-pocket metros the county-jid upload lands where there are NO
     needles (silently on-needle=0). Flags when this jid has listings but 0 human needles AND a sibling
     jurisdiction (same county/metro name) DOES hold needles -> listings likely on the wrong jid.
  4. SPOT-CHECK 3      — print 3 matched listings (address vs matched parcel address) for #42 eyeballing.

Read-only (no writes). Report the printed REPORT line + any FLAGS to the coordinator.
Run: cd backend && PYTHONUTF8=1 python scripts/_qa_costar.py <jid-or-name-substring> [more...]
"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import asyncpg  # noqa: E402
from app.services.postingest_gate import run_postingest_gate  # noqa: E402

ON_NEEDLE_SQL = """SELECT count(*) FROM forsale_listings f
  JOIN parcels p ON p.id=f.matched_parcel_id
  JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
  JOIN LATERAL (SELECT self_storage::text ss FROM zone_use_matrix m
     WHERE m.jurisdiction_id=p.jurisdiction_id AND m.zone_code=p.zoning_code
       AND (m.municipality IS NULL OR m.municipality=p.city) AND m.deleted_at IS NULL AND m.human_reviewed
     ORDER BY (m.municipality IS NULL) ASC LIMIT 1) v ON true
  WHERE f.jurisdiction_id=$1::uuid AND f.is_current=true AND v.ss IN ('permitted','conditional')
    AND p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000"""

NEEDLE_SQL = """SELECT count(*) FROM parcels p
  JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
  JOIN LATERAL (SELECT self_storage::text ss FROM zone_use_matrix m
     WHERE m.jurisdiction_id=p.jurisdiction_id AND m.zone_code=p.zoning_code
       AND (m.municipality IS NULL OR m.municipality=p.city) AND m.deleted_at IS NULL AND m.human_reviewed
     ORDER BY (m.municipality IS NULL) ASC LIMIT 1) v ON true
  WHERE p.jurisdiction_id=$1::uuid AND v.ss IN ('permitted','conditional') AND p.acres>=1.5
    AND prm.median_home_value>=475000 AND prm.median_hhi>=100000"""


async def resolve(con, tok):
    try:
        import uuid as _u; _u.UUID(tok)
        r = await con.fetchrow("SELECT id,name FROM jurisdictions WHERE id=$1", tok)
    except ValueError:
        r = await con.fetch("SELECT id,name FROM jurisdictions WHERE name ILIKE $1 ORDER BY name", f"%{tok}%")
        if len(r) != 1:
            print(f"  '{tok}' matched {len(r)} jurisdictions: {[x['name'] for x in r][:8]}"); return None
        r = r[0]
    return r


async def qa(con, jid, name):
    print(f"\n================ {name}  [{jid}] ================")
    # 1. matcher drained
    tot = await con.fetchval("SELECT count(*) FROM forsale_listings WHERE jurisdiction_id=$1", jid)
    cur = await con.fetchval("SELECT count(*) FROM forsale_listings WHERE jurisdiction_id=$1 AND is_current", jid)
    unmatched = await con.fetchval("SELECT count(*) FROM forsale_listings WHERE jurisdiction_id=$1 AND match_method IS NULL", jid)
    matched = await con.fetchval("SELECT count(*) FROM forsale_listings WHERE jurisdiction_id=$1 AND is_current AND matched_parcel_id IS NOT NULL", jid)
    drained = "DRAINED" if unmatched == 0 else f"NOT-DRAINED ({unmatched} pending — re-run _match_listings_direct.py {jid})"
    matched_pct = (100 * matched / cur) if cur else 0
    print(f"  1. matcher: {drained}")
    # 2. on-needle + gate + needles
    needles = await con.fetchval(NEEDLE_SQL, jid)
    on_needle = await con.fetchval(ON_NEEDLE_SQL, jid)
    rep = await run_postingest_gate(con, jid)
    gate = "PASS" if rep.passed else "FAIL"
    # casing
    munis = await con.fetch("SELECT DISTINCT municipality FROM zone_use_matrix WHERE jurisdiction_id=$1 AND human_reviewed AND deleted_at IS NULL AND municipality IS NOT NULL", jid)
    cities = set(r["city"] for r in await con.fetch("SELECT DISTINCT city FROM parcels WHERE jurisdiction_id=$1", jid))
    casing_bad = [m["municipality"] for m in munis if m["municipality"] not in cities]
    print(f"  2. needles={needles}  on-needle={on_needle}  gate={gate}  casing_problems={len(casing_bad)}")
    if not rep.passed:
        for f in rep.hard_failures: print(f"     GATE HARD FAIL: {f}")
    if casing_bad: print(f"     CASING MISMATCH: {casing_bad[:6]}")
    # 3. jid-alignment trap
    if cur and needles == 0:
        cty = name.split(" County")[0].split(",")[0].strip()
        sibs = await con.fetch("SELECT id,name FROM jurisdictions WHERE name ILIKE $1 AND id!=$2", f"%{cty}%", jid)
        sib_hits = []
        for s in sibs:
            sn = await con.fetchval(NEEDLE_SQL, s["id"])
            if sn and sn > 0: sib_hits.append(f"{s['name']}={sn}")
        if sib_hits:
            print(f"  3. *** JID-ALIGNMENT FLAG: {cur} listings on a jid with 0 needles, but sibling(s) hold needles: {sib_hits[:6]} — listings likely uploaded to the wrong jid; FLAG to coordinator (do not re-upload).")
        else:
            print(f"  3. jid-alignment: 0 needles on this jid and no needle-bearing sibling found (may be a true no-op county).")
    else:
        print(f"  3. jid-alignment: OK ({needles} needles on this jid).")
    # 4. spot-check 3 matched listings
    spot = await con.fetch("""SELECT f.address f_addr, f.city f_city, f.match_method, round(f.match_confidence::numeric,2) conf,
        p.address p_addr, p.city p_city, p.zoning_code FROM forsale_listings f JOIN parcels p ON p.id=f.matched_parcel_id
        WHERE f.jurisdiction_id=$1 AND f.is_current AND f.matched_parcel_id IS NOT NULL ORDER BY f.match_confidence DESC NULLS LAST LIMIT 3""", jid)
    print(f"  4. spot-check (listing addr -> matched parcel addr):")
    for s in spot:
        print(f"     '{s['f_addr']}, {s['f_city']}' -> '{s['p_addr']}, {s['p_city']}' [{s['zoning_code']}] {s['match_method']} conf={s['conf']}")
    print(f"  REPORT | {name}: current={cur} matched%={matched_pct:.0f} on-needle={on_needle} gate={gate} needles={needles} {'| DRAINED' if unmatched==0 else '| NOT-DRAINED='+str(unmatched)}")


async def main(toks):
    url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0].replace("postgresql+asyncpg://", "postgresql://")
    con = await asyncpg.connect(url, timeout=90, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        for tok in toks:
            j = await resolve(con, tok)
            if j: await qa(con, j["id"], j["name"])
    finally:
        await con.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: _qa_costar.py <jid-or-name> [...]"); sys.exit(1)
    asyncio.run(main(sys.argv[1:]))
