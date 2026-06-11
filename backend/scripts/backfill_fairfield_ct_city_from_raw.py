"""Phase-2B-redux one-off: populate parcels.city for Fairfield CT from raw.Town_Name.

Per PR #221's pre-flight finding, the CT CAMA layer publishes
`Town_Name` and `Property_City` on every row, and the 2026-05-08
Fairfield CT ingest captured both into `parcels.raw` (JSONB). The
current `_CITY_FIELDS` list at backend/app/services/ingestion.py:181
already includes `TOWN_NAME` and `_first()` is case-insensitive,
so re-running ingestion would populate `parcels.city`. This script
takes the surgical equivalent path: a batched SQL UPDATE that
reads `raw->>'Town_Name'` and writes `city` for the single
jurisdiction, with no touch to geometry, zoning_code, or matrix.

Master authorized this specific prod write via PR #221's Option B
("Fairfield-only city re-ingest, ~1 h operator time"). Hard rule:
no parcel geometry / zoning_code / matrix changes.

Field choice rationale:

  Town_Name agrees with Property_City on 250,147 / 261,652 rows
  (95.6 %); they disagree on 11,505 / 261,652 (4.4 %). For the
  zoning-authority join key, Town_Name is correct: it names the
  legal town with zoning jurisdiction (CGS Chapter 124), while
  Property_City can reflect mailing-address conventions that
  cross town lines.

Safety:

  - Only updates `city` (plus `updated_at` via existing trigger).
  - WHERE clause is scoped to the Fairfield CT jurisdiction_id only
    AND parcels where city IS NULL — so a re-run is a no-op once
    the initial sweep completes.
  - Batched 50K rows per transaction via run_batched_update so
    Supabase's 60 s statement_timeout never cancels mid-flight.
  - Returns 1 per row so the helper can count the total updates.

Usage:

    cd backend && python -m scripts.backfill_fairfield_ct_city_from_raw
"""
from __future__ import annotations

import asyncio
import uuid

from app.db import engine
from app.services.batched_update import run_batched_update


FAIRFIELD_CT_ID = uuid.UUID("66230887-aabe-4d62-aebb-856939ba77bb")


SQL = """
    WITH batch AS (
        SELECT p.id, p.raw->>'Town_Name' AS town_from_raw
        FROM parcels p
        WHERE p.jurisdiction_id = :jid::uuid
          AND (p.city IS NULL OR btrim(p.city) = '')
          AND p.raw IS NOT NULL
          AND p.raw ? 'Town_Name'
          AND btrim(p.raw->>'Town_Name') <> ''
        LIMIT :n
        FOR UPDATE OF p SKIP LOCKED
    )
    UPDATE parcels p
    SET city = b.town_from_raw
    FROM batch b
    WHERE p.id = b.id
    RETURNING 1
"""


async def main() -> None:
    total = await run_batched_update(
        SQL, params={"jid": str(FAIRFIELD_CT_ID)}
    )
    print(f"Done. Updated city on {total} Fairfield CT parcels.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
