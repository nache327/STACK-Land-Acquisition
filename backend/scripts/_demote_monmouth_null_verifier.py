"""Demote the mis-scoped municipality=NULL "Permitted"/speculative human rows in Monmouth
County NJ that fan an UNVERIFIED verdict county-wide (the Verifier NULL-municipality bug tail).

Monmouth is NJ home-rule — there is NO county-wide zoning ordinance, so a municipality=NULL
"permitted" verdict cannot be a legitimate county default; it fans one unverified call across all
56 towns. Per #37 (verbatim basis required) these three rows have NO defensible basis and are
demoted (tombstoned). The properly-grounded town-scoped LI rows (Marlboro §220-92 conditional;
Red Bank §490-150 permitted) are UNTOUCHED and remain authoritative.

Rows demoted (municipality=NULL, human_reviewed, active):
  LI  ss=permitted  note "Permitted" — #38 DECISIVE: contradicted by Marlboro's own §220-92
      (LI self-storage = CONDITIONAL there) and Red Bank §490-150 (permitted) — the two verified
      towns DISAGREE, so a county-wide "permitted" is factually wrong. Fans 67 unverified needles
      (Manalapan 28, Aberdeen 14, Neptune 14, Shrewsbury 8, Freehold 3); Marlboro 31 + Red Bank 2
      keep their OWN verified rows.
  IOR ss=permitted  note "Permitted" — no verbatim basis, no town-scoped IOR verdict exists; bare
      county-wide "permitted" across 56 home-rule towns fails #37. Fans 35 unverified needles.
  CIR ss=conditional note "It says 'Storage of products or materials'. I think we should consider
      this." — a speculative musing, not a grounded verdict (#37 fail). Arms 0 needles.

NET: removes ~102 UNVERIFIED wealth-gated needles (false-confidence leads). Recommend a proper
per-town grounding pass for Monmouth LI/IOR towns (esp. Manalapan — 347 LI parcels) to recover any
GENUINE needles on a verbatim basis. Marlboro + Red Bank verified needles are preserved.

Run (dry):   python -m scripts._demote_monmouth_null_verifier
Apply+rescore: python -m scripts._demote_monmouth_null_verifier --apply
"""
from __future__ import annotations
import argparse, asyncio
import asyncpg
from scripts._db import get_sync_dsn

MON = "703d95b4-3229-42f8-8bb1-460d46b3ceb2"
CODES = ["LI", "IOR", "CIR"]
NEEDLE_SQL = """
 SELECT count(*) FROM parcels p
  JOIN parcel_ring_metrics prm ON prm.parcel_id=p.id AND prm.drive_time_minutes=10
  JOIN LATERAL (
     SELECT self_storage::text ss FROM zone_use_matrix m
      WHERE m.jurisdiction_id=p.jurisdiction_id AND m.zone_code=p.zoning_code
        AND (m.municipality IS NULL OR m.municipality=p.city)
        AND m.deleted_at IS NULL AND m.human_reviewed=true
      ORDER BY (m.municipality IS NULL) ASC LIMIT 1) v ON true
  WHERE p.jurisdiction_id=$1::uuid AND v.ss IN ('permitted','conditional')
    AND p.acres>=1.5 AND prm.median_home_value>=475000 AND prm.median_hhi>=100000
"""
TOMB = ("[DEMOTED 2026-07-15: municipality=NULL '{ss}' verdict with no #37 verbatim per-town basis "
        "fanned county-wide across NJ home-rule Monmouth (no county UDO). "
        "{extra} Verifier NULL-municipality bug tail; town-scoped verdicts unaffected.]")
EXTRA = {
    "LI": "Contradicted by Marlboro §220-92 (conditional) vs Red Bank §490-150 (permitted) — county-wide 'permitted' is factually wrong.",
    "IOR": "No town-scoped IOR verdict exists; bare 'Permitted' note.",
    "CIR": "Note was a speculative musing ('I think we should consider this'), not a verdict.",
}


async def main(apply: bool) -> None:
    con = await asyncpg.connect(get_sync_dsn(), timeout=180, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout=0")
        print("=== target NULL rows ===")
        rows = await con.fetch(
            "SELECT zone_code, self_storage::text ss, left(notes,70) note FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1::uuid AND zone_code=ANY($2::text[]) AND municipality IS NULL "
            "AND deleted_at IS NULL AND human_reviewed", MON, CODES)
        for r in rows:
            print(f"  {r['zone_code']:5} ss={r['ss']:11} note={r['note']!r}")
        before = await con.fetchval(NEEDLE_SQL, MON)
        print(f"\nMonmouth wealth-gated needles BEFORE: {before}")
        if not apply:
            print("\n[dry-run] no writes. --apply to demote + re-score.")
            return
        async with con.transaction():
            for zc in CODES:
                ssv = await con.fetchval(
                    "SELECT self_storage::text FROM zone_use_matrix WHERE jurisdiction_id=$1::uuid "
                    "AND zone_code=$2 AND municipality IS NULL AND deleted_at IS NULL AND human_reviewed", MON, zc)
                if ssv is None:
                    print(f"  {zc}: no active NULL row (skip)")
                    continue
                note = TOMB.format(ss=ssv, extra=EXTRA[zc])
                st = await con.execute(
                    "UPDATE zone_use_matrix SET deleted_at=now(), updated_at=now(), "
                    "notes=left(coalesce(notes,'')||' '||$3, 1000) "
                    "WHERE jurisdiction_id=$1::uuid AND zone_code=$2 AND municipality IS NULL "
                    "AND deleted_at IS NULL AND human_reviewed", MON, zc, note)
                print(f"  {zc}: DEMOTED ({st})")
        print("\n=== RE-SCORING Monmouth (advisory-locked) ===")
        import sys, json as _json, uuid as _uuid
        sys.path.insert(0, ".")
        from app.services.buybox_scoring import score_jurisdiction
        f = await con.fetchrow("SELECT id, filter_json FROM buybox_filters WHERE is_default=true ORDER BY updated_at DESC LIMIT 1")
        fj = f["filter_json"]
        if isinstance(fj, str):
            fj = _json.loads(fj)
        n = await score_jurisdiction(_uuid.UUID(MON), f["id"], fj or {})
        print(f"  parcels_scored = {n}")
        after = await con.fetchval(NEEDLE_SQL, MON)
        print(f"\nMonmouth needles AFTER: {after}  (delta {after-before})")
        # confirm Marlboro + Red Bank LI verified needles preserved
        keep = await con.fetch(
            "SELECT municipality, self_storage::text ss, (deleted_at IS NOT NULL) tomb FROM zone_use_matrix "
            "WHERE jurisdiction_id=$1::uuid AND zone_code='LI' ORDER BY tomb, municipality NULLS FIRST", MON)
        print("LI rows after:", [(r['municipality'], r['ss'], 'TOMB' if r['tomb'] else 'live') for r in keep])
    finally:
        await con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    asyncio.run(main(ap.parse_args().apply))
