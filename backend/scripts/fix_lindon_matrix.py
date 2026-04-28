"""Fix three Lindon zone_use_matrix rows to match actual AxA-Table use matrix."""
import asyncio, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import dotenv_values
for k, v in dotenv_values(Path(__file__).parent.parent / ".env").items():
    if k not in os.environ:
        os.environ[k] = v

from app.db import async_session_maker
from sqlalchemy import text

async def fix():
    async with async_session_maker() as db:
        r = await db.execute(text("SELECT id FROM jurisdictions WHERE name ILIKE '%lindon%' LIMIT 1"))
        jur_id = r.scalar_one()
        print("Lindon id:", jur_id)

        # CG-S: shows P in AxA-Table — was incorrectly classified as prohibited
        await db.execute(text("""
            UPDATE zone_use_matrix SET
                self_storage = 'permitted',
                mini_warehouse = 'permitted',
                confidence = 0.99,
                notes = 'Confirmed P in AxA-Table: Vault Security Storage / Mini-Storage row'
            WHERE jurisdiction_id = :jid AND zone_code = 'CG-S'
        """), {"jid": jur_id})

        # LI-W: shows N in AxA-Table — was incorrectly classified as permitted
        # RB: shows N in AxA-Table — was incorrectly classified as permitted
        await db.execute(text("""
            UPDATE zone_use_matrix SET
                self_storage = 'prohibited',
                mini_warehouse = 'prohibited',
                luxury_garage_condo = 'prohibited',
                confidence = 0.99,
                notes = 'Confirmed N in AxA-Table: Vault Security Storage / Mini-Storage row'
            WHERE jurisdiction_id = :jid AND zone_code IN ('LI-W', 'RB')
        """), {"jid": jur_id})

        await db.commit()

        r2 = await db.execute(text("""
            SELECT zone_code, self_storage, mini_warehouse, luxury_garage_condo, confidence
            FROM zone_use_matrix
            WHERE jurisdiction_id = :jid AND zone_code IN ('CG-S','LI','LI-W','MC','RB','HI')
            ORDER BY zone_code
        """), {"jid": jur_id})
        print("\nStorage zones after fix:")
        for row in r2.fetchall():
            print(f"  {row[0]:<8} self_storage={row[1]:<12} mini_wh={row[2]:<12} garage={row[3]:<12} conf={row[4]:.2f}")

asyncio.run(fix())
