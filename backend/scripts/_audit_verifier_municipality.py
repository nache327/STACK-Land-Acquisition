"""Audit: human-reviewed zone_use_matrix rows whose municipality is NULL or does
NOT match any parcels.city for their jurisdiction — the silent-mis-scope surface
left by the in-app Zoning Verifier NULL-municipality bug
(see memory: project_verifier_writes_null_municipality).

READ-ONLY. Prints per-county / per-jurisdiction breakdowns and classifies each
offending row so a backfill can act only on the safely-derivable ones:

  Classes for a human_reviewed=true, deleted_at IS NULL matrix row:
    OK              municipality matches a parcels.city (exact) in this jurisdiction
    NULL_SINGLE     municipality IS NULL and the jurisdiction has exactly ONE
                    distinct parcels.city  -> town is unambiguous, backfillable
    NULL_COUNTY_UDO municipality IS NULL, multi-town jurisdiction, notes look like a
                    deliberate county-wide apply (NOT the Verifier) -> LEAVE ALONE
    NULL_VERIFIER   municipality IS NULL, multi-town jurisdiction, notes show the
                    in-app Verifier wrote it -> town NOT derivable -> MANUAL REVIEW
    NULL_OTHER      municipality IS NULL, multi-town, notes inconclusive -> MANUAL
    CASE_MISMATCH   municipality set but no exact parcels.city match; a case-
                    insensitive match exists -> backfillable (fix casing)
    NO_MATCH        municipality set but matches no parcels.city (any case) ->
                    MANUAL REVIEW (dead row, arms nothing)

Run:  python -m scripts._audit_verifier_municipality
"""
from __future__ import annotations

import asyncio
import json

import asyncpg

from scripts._db import get_sync_dsn

# The in-app Verifier stamps this into notes (see
# frontend/app/api/apply-correction/route.ts). It is the discriminator that
# separates a per-town verdict written NULL by the Verifier from a deliberate
# county-wide (UDO) apply done by a script.
VERIFIER_NOTE_MARK = "Site Scout Zoning Chat"


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    try:
        # Disable the server statement timeout: the city_list CTE scans the full
        # (multi-million-row) parcels table and exceeds Supabase's default timeout.
        await con.execute("SET statement_timeout=0")
        # All active human-reviewed rows, with their jurisdiction + county context
        # and whether municipality matches a real parcels.city (exact / any-case).
        rows = await con.fetch(
            """
            WITH cities AS (
                SELECT jurisdiction_id,
                       array_agg(DISTINCT city) FILTER (WHERE city IS NOT NULL) AS city_list
                  FROM parcels
                 GROUP BY jurisdiction_id
            )
            SELECT m.id,
                   m.jurisdiction_id,
                   j.name          AS jur_name,
                   j.state,
                   j.county,
                   j.parcel_source,
                   m.zone_code,
                   m.municipality,
                   m.self_storage::text  AS self_storage,
                   m.mini_warehouse::text AS mini_warehouse,
                   m.notes,
                   COALESCE(c.city_list, ARRAY[]::text[]) AS city_list
              FROM zone_use_matrix m
              JOIN jurisdictions j ON j.id = m.jurisdiction_id
              LEFT JOIN cities c   ON c.jurisdiction_id = m.jurisdiction_id
             WHERE m.human_reviewed = true
               AND m.deleted_at IS NULL
             ORDER BY j.state, j.county, j.name, m.zone_code, m.municipality
            """
        )

        def classify(r) -> str:
            city_list = list(r["city_list"] or [])
            n_cities = len(city_list)
            muni = r["municipality"]
            notes = (r["notes"] or "")
            if muni is not None:
                if muni in city_list:
                    return "OK"
                lower = {c.lower(): c for c in city_list}
                if muni.lower() in lower:
                    return "CASE_MISMATCH"
                return "NO_MATCH"
            # municipality IS NULL
            if n_cities <= 1:
                return "NULL_SINGLE"
            if VERIFIER_NOTE_MARK in notes:
                return "NULL_VERIFIER"
            # Heuristic: a script-applied county-default usually names the ordinance
            # / county in notes and is NOT the Verifier. Treat non-Verifier NULLs on
            # multi-town jurisdictions as UDO-style unless notes are empty.
            if notes.strip():
                return "NULL_COUNTY_UDO"
            return "NULL_OTHER"

        by_county: dict[tuple, dict[str, int]] = {}
        by_jur: dict[tuple, dict[str, int]] = {}
        offenders: list[dict] = []

        for r in rows:
            cls = classify(r)
            ckey = (r["state"], r["county"])
            jkey = (r["state"], r["county"], r["jur_name"], str(r["jurisdiction_id"]))
            by_county.setdefault(ckey, {}).setdefault(cls, 0)
            by_county[ckey][cls] += 1
            by_jur.setdefault(jkey, {}).setdefault(cls, 0)
            by_jur[jkey][cls] += 1
            if cls not in ("OK",):
                offenders.append(
                    {
                        "id": str(r["id"]),
                        "jurisdiction_id": str(r["jurisdiction_id"]),
                        "jur_name": r["jur_name"],
                        "state": r["state"],
                        "county": r["county"],
                        "parcel_source": r["parcel_source"],
                        "zone_code": r["zone_code"],
                        "municipality": r["municipality"],
                        "self_storage": r["self_storage"],
                        "mini_warehouse": r["mini_warehouse"],
                        "class": cls,
                        "n_cities": len(r["city_list"] or []),
                        "city_list": list(r["city_list"] or [])[:6],
                        "notes": (r["notes"] or "")[:120],
                    }
                )

        total = len(rows)
        offend = len(offenders)
        print(f"=== human_reviewed active matrix rows: {total} | offenders (non-OK): {offend} ===\n")

        def _sk(t):
            return tuple("" if x is None else str(x) for x in t)

        print("--- Per-county class tallies (non-OK only shown when present) ---")
        for ckey in sorted(by_county, key=_sk):
            tallies = by_county[ckey]
            non_ok = {k: v for k, v in tallies.items() if k != "OK"}
            if not non_ok:
                continue
            st, co = ckey
            ok = tallies.get("OK", 0)
            print(f"  {st} / {co}: OK={ok}  " + "  ".join(f"{k}={v}" for k, v in sorted(non_ok.items())))

        print("\n--- Per-jurisdiction (only jurisdictions with offenders) ---")
        for jkey in sorted(by_jur, key=_sk):
            tallies = by_jur[jkey]
            non_ok = {k: v for k, v in tallies.items() if k != "OK"}
            if not non_ok:
                continue
            st, co, jn, jid = jkey
            print(f"  [{st}/{co}] {jn} ({jid})")
            print(f"       OK={tallies.get('OK',0)}  " + "  ".join(f"{k}={v}" for k, v in sorted(non_ok.items())))

        print("\n--- Offender detail ---")
        for o in offenders:
            print(json.dumps(o))

        # Machine-readable dump for the backfill step
        out_path = "scripts/_drafts/_verifier_audit_offenders.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(offenders, f, indent=2)
        print(f"\nWrote {offend} offenders to {out_path}")

        # Class rollup
        rollup: dict[str, int] = {}
        for o in offenders:
            rollup[o["class"]] = rollup.get(o["class"], 0) + 1
        print("\n=== Class rollup (offenders) ===")
        for k, v in sorted(rollup.items()):
            print(f"  {k}: {v}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
