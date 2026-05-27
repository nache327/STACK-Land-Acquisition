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
          -- NEVER stamp the jurisdiction name onto a county-as-jurisdiction's
          -- parcels: those span many cities and must keep their real per-row
          -- city (from PARCEL_CITY at ingest, or a spatial join). Only the
          -- single-city (city_gis / regrid) jurisdictions get the safe fallback.
          AND (j.parcel_source::text IS DISTINCT FROM 'county_gis')
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
