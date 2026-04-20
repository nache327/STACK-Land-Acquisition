import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

URL = "postgresql+asyncpg://postgres:WebIIPTvnxZfmKgMbuUKmzYZdjEqaotS@nozomi.proxy.rlwy.net:56784/railway"

async def test():
    engine = create_async_engine(URL)
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT schemaname, tablename FROM pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog','information_schema') "
            "ORDER BY schemaname, tablename"
        ))
        tables = [(row[0], row[1]) for row in r.fetchall()]
        print("Tables found:", tables)
        r2 = await conn.execute(text("SELECT current_database(), current_schema()"))
        print("DB/schema:", r2.fetchone())

asyncio.run(test())
