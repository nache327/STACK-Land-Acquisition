import asyncio, asyncpg, os, sys
sys.path.insert(0, __file__.rsplit('\\', 2)[0])

from app.config import settings

async def main():
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url, statement_cache_size=0, command_timeout=30)
    row = await conn.fetchrow(
        "SELECT COUNT(*) as t, COUNT(*) FILTER (WHERE zoning_code IS NOT NULL AND zoning_code != '') as z "
        "FROM parcels WHERE jurisdiction_id = '821d1007-9dec-4fad-868a-104385d5ef43'"
    )
    print(f"Total: {row[0]} | Zoned: {row[1]} | Unzoned: {row[0] - row[1]}")
    await conn.close()

asyncio.run(main())
