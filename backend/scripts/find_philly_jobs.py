import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlalchemy import select, text
from app.db import async_session_maker

async def main():
    async with async_session_maker() as db:
        result = await db.execute(text("""
            SELECT j.id, j.status, jur.name, j.created_at
            FROM jobs j
            JOIN jurisdictions jur ON j.jurisdiction_id = jur.id
            WHERE jur.name ILIKE '%philadelphia%'
            ORDER BY j.created_at DESC
            LIMIT 10
        """))
        rows = result.fetchall()
        for row in rows:
            print(row)

asyncio.run(main())
