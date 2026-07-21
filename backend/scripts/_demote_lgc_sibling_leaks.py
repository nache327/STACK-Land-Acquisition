"""QC one-off: demote stored luxury_garage_condo -> prohibited where a HUMAN found
self_storage prohibited (the Brink Rd sibling-leak class), UNLESS the row names a real
garage use.

This keeps the STORED matrix column consistent with the query-time derivation veto added in
use_verdicts._LGC_VERDICT_SQL (a human storage-prohibition blocks sibling-derived LGC), and
makes the hardened post-ingest gate (catch #58 v2) pass. Rows that are NOT human-reviewed are
left alone — an un-reviewed storage-dead industrial zone is the legitimate LGC thesis.

Demote, don't delete: sets luxury_garage_condo='prohibited' and appends an audit note; the
row and its human self_storage verdict are otherwise untouched.

Usage:
  python -m scripts._demote_lgc_sibling_leaks            # DRY-RUN (default): print candidates
  python -m scripts._demote_lgc_sibling_leaks --apply    # commit demotions + write audit JSON
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json

import asyncpg

from app.services.postingest_gate import _NAMED_GARAGE_MARKERS
from scripts._db import get_sync_dsn

_NOTE = "LGC demoted: sibling leak vs human-verified self_storage=prohibited (QC 2026-07-21)"


def _named_garage(basis: str) -> bool:
    t = (basis or "").lower()
    return any(m in t for m in _NAMED_GARAGE_MARKERS)


async def main(apply: bool) -> None:
    conn = await asyncpg.connect(get_sync_dsn())
    try:
        rows = await conn.fetch(
            """
            SELECT m.id, j.name AS jur, m.municipality, m.zone_code,
                   m.self_storage::text ss, m.luxury_garage_condo::text lgc,
                   coalesce(m.notes,'') AS notes, coalesce(m.citations::text,'') AS cites
              FROM zone_use_matrix m
              JOIN jurisdictions j ON j.id = m.jurisdiction_id
             WHERE m.deleted_at IS NULL
               AND m.human_reviewed IS TRUE
               AND m.self_storage::text = 'prohibited'
               AND m.luxury_garage_condo::text IN ('permitted', 'conditional')
               -- keep genuinely industrial zones (light_industrial='permitted') garage-viable
               AND m.light_industrial::text IS DISTINCT FROM 'permitted'
             ORDER BY j.name, m.municipality NULLS FIRST, m.zone_code
            """
        )
        demote, exempt = [], []
        for r in rows:
            (exempt if _named_garage(r["notes"] + " " + r["cites"]) else demote).append(r)

        print(f"candidates (human-verified ss=prohibited, lgc permitted/conditional): {len(rows)}")
        print(f"  -> to DEMOTE: {len(demote)}   |   named-garage EXEMPT (review manually): {len(exempt)}")
        for r in demote:
            print(f"   DEMOTE  {r['jur']:34.34} {str(r['municipality'] or '-'):18.18} {r['zone_code']:8} lgc={r['lgc']}")
        for r in exempt:
            print(f"   EXEMPT  {r['jur']:34.34} {str(r['municipality'] or '-'):18.18} {r['zone_code']:8}  (named garage use)")

        if not apply:
            print("\nDRY-RUN — nothing changed. Re-run with --apply to demote the DEMOTE rows.")
            return

        ids = [r["id"] for r in demote]
        if not ids:
            print("\nnothing to apply.")
            return
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE zone_use_matrix
                   SET luxury_garage_condo = 'prohibited',
                       notes = trim(both E'\\n' from coalesce(notes,'') || E'\\n' || $2),
                       updated_at = now()
                 WHERE id = ANY($1::uuid[])
                """,
                ids, _NOTE,
            )
        audit = {
            "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "demoted_ids": [str(i) for i in ids],
            "demoted": [f"{r['jur']}/{r['municipality']}/{r['zone_code']}" for r in demote],
            "exempt": [f"{r['jur']}/{r['municipality']}/{r['zone_code']}" for r in exempt],
        }
        path = "scripts/_drafts/_lgc_demote_audit.json"
        open(path, "w", encoding="utf-8").write(json.dumps(audit, indent=2))
        print(f"\nAPPLIED: demoted {len(ids)} rows. Audit -> {path}")
        print("Next: re-score affected jurisdictions + run postingest_gate (must PASS).")
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="commit demotions (default: dry-run)")
    a = ap.parse_args()
    asyncio.run(main(a.apply))
