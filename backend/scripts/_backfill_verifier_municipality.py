"""Backfill: scope the SAFELY-DERIVABLE mis-scoped human verdict rows found by
_audit_verifier_municipality.py to their correct municipality (exact
parcels.city casing), then re-score the affected county under the advisory lock
and report the needle delta.

Scope is deliberately narrow (catch #42 verify-before-declare, demote-don't-guess):
we ONLY touch rows whose intended town is derivable from the verbatim human note
(catch #37 basis). The current audit yields exactly three such rows — Somerset
County NJ G-B / PAC / S-C-V, whose notes each name "Franklin" — which are
Franklin-township verdicts written at municipality=NULL and therefore fanning
county-wide across 28 towns. Everything else the audit found is either correct
as-is (genuine county-wide UDO defaults, single-place jurisdictions whose
parcels.city is NULL) or NOT safely derivable (17 in-app Verifier rows with
generic notes) and is left for manual review.

Run (dry-run, default):  python -m scripts._backfill_verifier_municipality
Apply + re-score:         python -m scripts._backfill_verifier_municipality --apply
"""
from __future__ import annotations

import argparse
import asyncio

import asyncpg

from scripts._db import get_sync_dsn

SOMERSET_JID = "394ef40c-ca0d-4d57-9b11-dc5417430240"

# (jurisdiction_id, zone_code, target municipality) — target MUST match
# parcels.city exactly (verified: Somerset parcels use "<Name> township").
BACKFILL = [
    (SOMERSET_JID, "G-B", "Franklin township"),
    (SOMERSET_JID, "PAC", "Franklin township"),
    (SOMERSET_JID, "S-C-V", "Franklin township"),
]

NEEDLE_SQL = """
    SELECT count(*) FROM parcels p
     JOIN parcel_ring_metrics prm
       ON prm.parcel_id = p.id AND prm.drive_time_minutes = 10
     JOIN LATERAL (
        SELECT self_storage::text AS ss
          FROM zone_use_matrix m
         WHERE m.jurisdiction_id = p.jurisdiction_id
           AND m.zone_code = p.zoning_code
           AND (m.municipality IS NULL OR m.municipality = p.city)
           AND m.deleted_at IS NULL
           AND m.human_reviewed = true
         ORDER BY (m.municipality IS NULL) ASC
         LIMIT 1
     ) v ON true
     WHERE p.jurisdiction_id = $1::uuid
       AND v.ss IN ('permitted', 'conditional')
       AND p.acres >= 1.5
       AND prm.median_home_value >= 475000
       AND prm.median_hhi >= 100000
"""


async def main(apply: bool) -> None:
    con = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    try:
        # Verify exact parcels.city target exists (catch: case-sensitive join)
        for jid, _code, target in BACKFILL:
            exists = await con.fetchval(
                "SELECT 1 FROM parcels WHERE jurisdiction_id=$1::uuid AND city=$2 LIMIT 1",
                jid, target,
            )
            if not exists:
                raise SystemExit(f"ABORT: target city {target!r} not found in parcels for {jid}")

        print("=== BEFORE — target rows (current municipality) ===")
        for jid, code, target in BACKFILL:
            rows = await con.fetch(
                """SELECT municipality, self_storage::text ss, mini_warehouse::text mw,
                          human_reviewed, left(notes, 90) note
                     FROM zone_use_matrix
                    WHERE jurisdiction_id=$1::uuid AND zone_code=$2 AND deleted_at IS NULL""",
                jid, code,
            )
            for r in rows:
                print(f"  {code:6} muni={r['municipality']!r} ss={r['ss']} mw={r['mw']} "
                      f"human={r['human_reviewed']} note={r['note']!r}")

        needles_before = await con.fetchval(NEEDLE_SQL, SOMERSET_JID)
        print(f"\nSomerset wealth-gated needles BEFORE: {needles_before}")

        if not apply:
            print("\n[dry-run] No changes written. Re-run with --apply to scope + re-score.")
            return

        # Apply. For each mis-scoped NULL row: if the target (jur, code, town)
        # slot is FREE -> scope it there. If the town ALREADY has an active row
        # for this code, that town-scoped verdict is the authority (it wins the
        # LATERAL anyway) and the NULL row is a superseded bug artifact whose
        # only live effect is fanning the verdict across the OTHER towns ->
        # soft-delete it (demote-don't-delete). This also avoids colliding with
        # the (jur, code, COALESCE(muni,'')) unique index.
        print("\n=== APPLYING (scope where slot free, else demote the NULL duplicate) ===")
        async with con.transaction():
            for jid, code, target in BACKFILL:
                taken = await con.fetchval(
                    """SELECT self_storage::text FROM zone_use_matrix
                        WHERE jurisdiction_id=$1::uuid AND zone_code=$2
                          AND municipality=$3 AND deleted_at IS NULL""",
                    jid, code, target,
                )
                if taken is None:
                    status = await con.execute(
                        """UPDATE zone_use_matrix
                              SET municipality=$3, updated_at=now()
                            WHERE jurisdiction_id=$1::uuid AND zone_code=$2
                              AND municipality IS NULL AND deleted_at IS NULL""",
                        jid, code, target,
                    )
                    print(f"  {code}: SCOPED -> {target!r} ({status})")
                else:
                    status = await con.execute(
                        """UPDATE zone_use_matrix
                              SET deleted_at=now(), updated_at=now(),
                                  notes=left(coalesce(notes,'') ||
                                    ' [DEMOTED 2026-07-13: mis-scoped NULL county-wide '
                                    'duplicate; superseded by the '''||$3||''' town-scoped '
                                    'verdict (ss='||$4||'). Verifier NULL-municipality bug.]', 1000)
                            WHERE jurisdiction_id=$1::uuid AND zone_code=$2
                              AND municipality IS NULL AND deleted_at IS NULL""",
                        jid, code, target, taken,
                    )
                    print(f"  {code}: DEMOTED NULL row (Franklin already has ss={taken}) ({status})")

        print("\n=== AFTER — target rows incl. tombstones (catch #42 verify) ===")
        for jid, code, target in BACKFILL:
            rows = await con.fetch(
                """SELECT municipality, self_storage::text ss, human_reviewed,
                          (deleted_at IS NOT NULL) AS tombstoned
                     FROM zone_use_matrix
                    WHERE jurisdiction_id=$1::uuid AND zone_code=$2
                    ORDER BY tombstoned, municipality NULLS FIRST""",
                jid, code,
            )
            for r in rows:
                print(f"  {code:6} muni={r['municipality']!r} ss={r['ss']} "
                      f"human={r['human_reviewed']} tombstoned={r['tombstoned']}")

        # Re-score Somerset under the advisory lock (service fn owns the lock).
        print("\n=== RE-SCORING Somerset (advisory-locked) ===")
        import sys
        sys.path.insert(0, ".")
        from app.services.buybox_scoring import score_jurisdiction  # noqa: E402
        import json as _json
        import uuid as _uuid

        f = await con.fetchrow(
            """SELECT bf.id, bf.filter_json
                 FROM buybox_filters bf
                WHERE bf.is_default = true
                ORDER BY bf.updated_at DESC LIMIT 1"""
        )
        if f is None:
            raise SystemExit("ABORT: no default buybox filter found")
        fj = f["filter_json"]
        if isinstance(fj, str):
            fj = _json.loads(fj)
        n = await score_jurisdiction(_uuid.UUID(SOMERSET_JID), f["id"], fj or {})
        print(f"  parcels_scored = {n}")

        needles_after = await con.fetchval(NEEDLE_SQL, SOMERSET_JID)
        print(f"\nSomerset wealth-gated needles AFTER: {needles_after}")
        print(f"DELTA (after - before): {needles_after - needles_before}")
    finally:
        await con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes + re-score")
    args = ap.parse_args()
    asyncio.run(main(args.apply))
