"""Batched whole-table update helper.

Supabase's pooler enforces a ~60s `statement_timeout`. Single-statement UPDATEs
that touch hundreds of thousands of rows get cancelled mid-flight, often after
already mutating data, leaving the table in a half-updated state.

This helper does each batch in its own transaction with `FOR UPDATE … SKIP
LOCKED` so concurrent writers (e.g. the Dramatiq worker, parcel ingestion)
keep working while the backfill drains.

Usage:

    from app.services.batched_update import run_batched_update

    sql = '''
        WITH batch AS (
            SELECT p.id, j.name AS j_name
            FROM parcels p
            JOIN jurisdictions j ON p.jurisdiction_id = j.id
            WHERE p.city IS NULL
            LIMIT :n
            FOR UPDATE OF p SKIP LOCKED
        )
        UPDATE parcels p SET city = b.j_name FROM batch b WHERE p.id = b.id
        RETURNING 1
    '''
    total = await run_batched_update(sql)
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from app.db import async_session_maker

logger = logging.getLogger(__name__)


async def run_batched_update(
    sql: str,
    *,
    batch: int = 50_000,
    params: dict[str, Any] | None = None,
) -> int:
    """Run a `WITH batch AS (... LIMIT :n FOR UPDATE … SKIP LOCKED) UPDATE … RETURNING 1`
    statement repeatedly in fresh transactions until a batch returns 0 rows.

    The SQL must use the bind parameter `:n` for the batch size and must
    `RETURNING 1` (or any column) so we can count rows-modified per batch.
    """
    if ":n" not in sql:
        raise ValueError("SQL must use `:n` for the batch-size bind parameter")
    if "RETURNING" not in sql.upper():
        raise ValueError("SQL must end with RETURNING so we can count rows per batch")

    total = 0
    while True:
        async with async_session_maker() as db:
            result = await db.execute(text(sql), {**(params or {}), "n": batch})
            n = len(result.all())
            await db.commit()
        total += n
        logger.info("batched-update: batch=%s, total=%s", n, total)
        if n == 0:
            return total
