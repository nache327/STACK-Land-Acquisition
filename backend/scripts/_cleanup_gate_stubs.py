"""Coordinator cleanup (Nache-approved 2026-07-14): clear the two pre-existing
gate-FAIL stubs so the post-ingest gate is a true signal again.

1. Westchester — Hastings-on-Hudson 'View Preservation Overlay': an OVERLAY name
   mis-ingested as a base zoning_code on 79 parcels (25 chars → trips the gate's
   over-length/URL-shaped check, which scans parcels.zoning_code). We don't have
   the Hastings source to re-derive the real base district, so NULL the invalid
   code (honest unclassified — no inference, catch #37) and soft-delete the
   overlay-as-base matrix row. Zero needle impact (the row was prohibited).
2. Morris — Mine Hill township 'AOZ' (Airport Overlay Zone): all-uses-'unclear'
   grounded stubs with 0 matching parcels → the gate's unclear-masquerade fail.
   Soft-delete (demote) both the human and rule rows. Zero needle/scoring impact.

Idempotent-ish; run once. Re-verifies both gates PASS at the end.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import asyncpg  # noqa: E402
from _db import get_sync_dsn  # noqa: E402
from app.services.postingest_gate import run_postingest_gate  # noqa: E402

WC = "3e706886-919f-4ecf-b5aa-567040e295e8"
MO = "746b7604-f362-470f-aa42-70dc8973b4ee"
_NOTE = " [CLEANUP 2026-07-14 Nache-approved: overlay/unclear stub demoted so the gate is a true signal; not a base district.]"


async def main() -> None:
    con = await asyncpg.connect(get_sync_dsn(), timeout=120, statement_cache_size=0)
    try:
        await con.execute("SET statement_timeout = 0")
        async with con.transaction():
            # 1a. NULL the 79 Hastings overlay-name parcels
            r = await con.execute(
                "UPDATE parcels SET zoning_code=NULL "
                "WHERE jurisdiction_id=$1::uuid AND zoning_code='View Preservation Overlay'", WC)
            print(f"Hastings parcels NULLed: {r}")
            # 1b. soft-delete the overlay-as-base matrix row
            r = await con.execute(
                "UPDATE zone_use_matrix SET deleted_at=now(), updated_at=now(), "
                "notes=left(coalesce(notes,'')||$2, 1000) "
                "WHERE jurisdiction_id=$1::uuid AND zone_code='View Preservation Overlay' AND deleted_at IS NULL",
                WC, _NOTE)
            print(f"Hastings overlay matrix row soft-deleted: {r}")
            # 2. soft-delete both Mine Hill AOZ stubs (human + rule)
            r = await con.execute(
                "UPDATE zone_use_matrix SET deleted_at=now(), updated_at=now(), "
                "notes=left(coalesce(notes,'')||$2, 1000) "
                "WHERE jurisdiction_id=$1::uuid AND zone_code='AOZ' AND deleted_at IS NULL",
                MO, _NOTE)
            print(f"Mine Hill AOZ stub(s) soft-deleted: {r}")

        # catch #42 — verify both gates now PASS
        for name, jid in (("Westchester", WC), ("Morris", MO)):
            rep = await run_postingest_gate(con, jid)
            status = "PASS" if rep.passed else "FAIL"
            print(f"\n[{status}] {name} gate — stats: {rep.stats}")
            for f in rep.hard_failures:
                print(f"  HARD FAIL: {f}")
    finally:
        await con.close()


if __name__ == "__main__":
    asyncio.run(main())
