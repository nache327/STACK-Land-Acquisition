"""One-time direct KMZ import script — bypasses HTTP, writes straight to Supabase."""
import asyncio
import os

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://postgres.bbvywbpxwsoyvdvygvyw:"
    "Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
)

from app.db import async_session_maker
from app.services.competitor_kmz import ingest_kmz_file

KMZ_PATH = r"C:\Users\nache_rl1pdne\Desktop\26.04.17 - Combined Storage.kmz"


async def main():
    print("Opening KMZ file...")
    with open(KMZ_PATH, "rb") as f:
        async with async_session_maker() as db:
            print("Parsing and inserting — this takes ~30 seconds...")
            inserted, skipped = await ingest_kmz_file(f, None, db)
            await db.commit()
    print(f"\nDone! {inserted:,} facilities inserted, {skipped:,} skipped (no coordinates).")


asyncio.run(main())
