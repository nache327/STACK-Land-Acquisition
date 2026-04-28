"""Backfill parcels.city / parcels.state from jurisdictions.

Run after a fresh parcel import. The zoning system-of-record keys
zoning_rules by (city, zone_code), so leaving parcels.city NULL collapses
every jurisdiction's rules into a single ('unknown', code) row.

    .venv/bin/python -m scripts.backfill_parcel_city
"""
from __future__ import annotations

import asyncio

from app.db import engine
from app.services.batched_update import run_batched_update


SQL = """
    WITH batch AS (
        SELECT p.id, j.name AS j_name, j.state AS j_state
        FROM parcels p
        JOIN jurisdictions j ON p.jurisdiction_id = j.id
        WHERE p.city IS NULL
        LIMIT :n
        FOR UPDATE OF p SKIP LOCKED
    )
    UPDATE parcels p
    SET city = b.j_name,
        state = COALESCE(p.state, b.j_state)
    FROM batch b
    WHERE p.id = b.id
    RETURNING 1
"""


async def main() -> None:
    total = await run_batched_update(SQL)
    print(f"Done. Updated {total} parcel rows.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
