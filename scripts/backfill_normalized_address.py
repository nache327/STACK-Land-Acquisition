"""Backfill parcels.normalized_address using the same normalize()
the listing matcher runs on listing addresses.

Fixes the asymmetric-normalization bug: matcher Tier 1/2 compares
normalize(listing.address) to a SQL-only lower()+strip-punct of the
parcel address. With this column materialized via the real normalize(),
both sides canonicalize identically (Dr->drive, N->north, route folding).

Applies the Alembic 0035 DDL first (idempotent), then backfills.

Usage:
    # one jurisdiction (fast, ~40K parcels)
    py scripts/backfill_normalized_address.py --jid 8e7992d0-...

    # all jurisdictions that have any unbackfilled parcels
    py scripts/backfill_normalized_address.py --all

Per spatial-backfill memory: session-mode port 5432 + statement_timeout=0.
Batched in chunks of 5000 so progress is visible and the transaction
doesn't balloon.
"""
from __future__ import annotations

import argparse, asyncio, sys
from pathlib import Path

import asyncpg

# Make backend importable for normalize()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.address_normalizer import normalize  # noqa: E402

DB_SESSION = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
CHUNK = 5000


async def _ensure_column(conn: asyncpg.Connection) -> None:
    await conn.execute("ALTER TABLE parcels ADD COLUMN IF NOT EXISTS normalized_address TEXT NULL")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_parcels_jur_normaddr "
        "ON parcels (jurisdiction_id, normalized_address)"
    )


async def _backfill_jurisdiction(conn: asyncpg.Connection, jid: str) -> int:
    total = 0
    while True:
        # Pull a chunk of parcels in this jurisdiction with an address
        # but no normalized_address yet.
        rows = await conn.fetch(
            """
            SELECT id, address FROM parcels
             WHERE jurisdiction_id = $1::uuid
               AND address IS NOT NULL
               AND normalized_address IS NULL
             LIMIT $2
            """,
            jid, CHUNK,
        )
        if not rows:
            break
        # Compute normalize() in Python, then write back via a values-list UPDATE.
        updates = [(r["id"], normalize(r["address"])) for r in rows]
        await conn.executemany(
            "UPDATE parcels SET normalized_address = $2 WHERE id = $1",
            updates,
        )
        total += len(updates)
        print(f"    +{len(updates)} (running {total:,})")
    return total


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jid", help="single jurisdiction_id")
    ap.add_argument("--all", action="store_true", help="all jurisdictions with unbackfilled parcels")
    args = ap.parse_args()

    conn = await asyncpg.connect(DB_SESSION, statement_cache_size=0, command_timeout=600)
    try:
        await conn.execute("SET statement_timeout = 0")
        await _ensure_column(conn)

        if args.jid:
            jids = [args.jid]
        elif args.all:
            rows = await conn.fetch(
                """
                SELECT DISTINCT jurisdiction_id::text AS jid
                  FROM parcels
                 WHERE address IS NOT NULL AND normalized_address IS NULL
                """
            )
            jids = [r["jid"] for r in rows]
        else:
            print("  pass --jid <uuid> or --all"); return 1

        print(f"  backfilling {len(jids)} jurisdiction(s)")
        grand = 0
        for jid in jids:
            name = await conn.fetchval("SELECT name FROM jurisdictions WHERE id=$1::uuid", jid)
            print(f"  === {name} ({jid}) ===")
            n = await _backfill_jurisdiction(conn, jid)
            grand += n
            print(f"  done: {n:,}")
        print()
        print(f"  TOTAL parcels normalized: {grand:,}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
