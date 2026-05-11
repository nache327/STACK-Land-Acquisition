"""Backfill ``parcels.assessed_value`` and ``parcels.is_residential`` from the
per-row ``raw`` JSONB.

Every parcel record already stores its source ArcGIS row in ``parcels.raw``;
we just never projected NET_VALUE / JV / PROP_CLASS / DOR_UC into named
columns. This script pulls them out using ``app.services.parcel_value_mapper``
and updates the two new columns added in migration 0018.

Idempotent — running it twice produces the same result. Safe to run while
the worker is live; uses small batches and short transactions so a long
backfill never holds locks long enough to block an ingest.

Run (from backend/):
    railway run python scripts/backfill_assessed_value.py            # all states
    railway run python scripts/backfill_assessed_value.py --state NJ # one state
    railway run python scripts/backfill_assessed_value.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg

from app.config import settings
from app.services.parcel_value_mapper import map_value_and_residential


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _session_dsn() -> str:
    """Session-mode pooler — required for long-running statements."""
    return (
        settings.database_url
        .replace(":6543/", ":5432/")
        .replace("postgresql+asyncpg://", "postgresql://")
    )


async def _backfill_state(
    conn: asyncpg.Connection,
    state: str,
    batch_size: int = 5000,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Backfill every parcel in one state. Returns
    (rows_scanned, rows_with_value, rows_marked_residential)."""
    scanned = 0
    with_value = 0
    residential = 0
    last_id = 0

    while True:
        rows = await conn.fetch(
            """
            SELECT p.id, p.raw
            FROM parcels p
            JOIN jurisdictions j ON j.id = p.jurisdiction_id
            WHERE j.state = $1
              AND p.id > $2
              AND p.raw IS NOT NULL
              AND (p.assessed_value IS NULL OR p.is_residential IS NULL)
            ORDER BY p.id
            LIMIT $3
            """,
            state, last_id, batch_size,
        )
        if not rows:
            break

        updates: list[tuple[int, float | None, bool | None]] = []
        for r in rows:
            scanned += 1
            raw = r["raw"]
            if not isinstance(raw, dict):
                # asyncpg sometimes hands JSONB back as str — parse if so.
                try:
                    import json as _json
                    raw = _json.loads(raw) if raw else None
                except Exception:
                    raw = None
            val, is_res = map_value_and_residential(state, raw or {})
            if val is not None:
                with_value += 1
            if is_res is True:
                residential += 1
            updates.append((r["id"], val, is_res))

        last_id = rows[-1]["id"]

        if not dry_run:
            # executemany so the whole batch goes in one round trip.
            await conn.executemany(
                """
                UPDATE parcels
                SET assessed_value = $2,
                    is_residential = $3
                WHERE id = $1
                """,
                updates,
            )

        logger.info(
            "  %s: scanned %d  with_value %d  residential %d  (last_id=%d)",
            state, scanned, with_value, residential, last_id,
        )

    return scanned, with_value, residential


async def main(states: list[str] | None, dry_run: bool) -> None:
    conn = await asyncpg.connect(
        _session_dsn(), statement_cache_size=0, command_timeout=7200,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        if not states:
            rows = await conn.fetch(
                "SELECT DISTINCT state FROM jurisdictions WHERE state IS NOT NULL"
            )
            states = sorted({r["state"] for r in rows})
        logger.info("Backfill scope: states=%s dry_run=%s", states, dry_run)

        totals = (0, 0, 0)
        for s in states:
            t0 = time.perf_counter()
            scanned, with_value, residential = await _backfill_state(
                conn, s, dry_run=dry_run,
            )
            dt = time.perf_counter() - t0
            logger.info(
                "Done %s in %.1fs: scanned=%d with_value=%d residential=%d",
                s, dt, scanned, with_value, residential,
            )
            totals = (
                totals[0] + scanned,
                totals[1] + with_value,
                totals[2] + residential,
            )

        logger.info(
            "TOTAL: scanned=%d with_value=%d residential=%d (dry_run=%s)",
            *totals, dry_run,
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--state", action="append", help="Two-letter state code; may repeat")
    p.add_argument("--dry-run", action="store_true", help="Scan + report only, no writes")
    args = p.parse_args()
    asyncio.run(main(args.state, args.dry_run))
