"""Apply Alembic 0030 (zone_matrix_structured_conditions) directly to
prod via asyncpg so the Howard MD sprint can start writing structured
conditions immediately, without waiting for a deploy cycle.

The SQL is identical to backend/alembic/versions/0030_zone_matrix_structured_conditions.py.
Uses IF NOT EXISTS so the Alembic upgrade later is a no-op.
"""
import asyncio, asyncpg, sys

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"

DDL = [
    "ALTER TABLE zone_use_matrix ADD COLUMN IF NOT EXISTS cited_subsection TEXT NULL",
    "ALTER TABLE zone_use_matrix ADD COLUMN IF NOT EXISTS conditions_json JSONB NULL",
    "ALTER TABLE zone_use_matrix ADD COLUMN IF NOT EXISTS overlay_codes   TEXT[] NULL",
]

async def main() -> int:
    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        for sql in DDL:
            print(f"  > {sql}")
            await conn.execute(sql)

        # Verify
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
              FROM information_schema.columns
             WHERE table_name='zone_use_matrix'
               AND column_name IN ('cited_subsection','conditions_json','overlay_codes')
             ORDER BY column_name
            """
        )
        print()
        print("  Verified columns now exist:")
        for r in rows:
            print(f"    {r['column_name']:20s} {r['data_type']:10s} null={r['is_nullable']}")
        return 0
    finally:
        await conn.close()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
