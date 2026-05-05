"""One-time fix: add 'downloading_zoning' to job_status_enum in production.

Run from backend/:
    railway run python scripts/fix_job_status_enum.py

Alembic migration 0007 was stamped as applied but the ALTER TYPE ADD VALUE
did not persist (likely due to Supabase PgBouncer transaction-mode read-only
connection). This script uses asyncpg directly in autocommit mode, which is
the only reliable way to run ADD VALUE outside a transaction.
"""
from __future__ import annotations

import asyncio
import os
import sys

import asyncpg


async def main() -> None:
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    # asyncpg expects postgresql:// not postgresql+asyncpg://
    url = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS "
            "'downloading_zoning' AFTER 'downloading_parcels'"
        )
        print("Done: 'downloading_zoning' is now in job_status_enum")

        # Verify
        rows = await conn.fetch(
            "SELECT enumlabel FROM pg_enum "
            "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
            "WHERE pg_type.typname = 'job_status_enum' "
            "ORDER BY enumsortorder"
        )
        print("Current enum values:", [r["enumlabel"] for r in rows])
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
