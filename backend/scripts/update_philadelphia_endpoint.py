"""
One-time: switch Philadelphia parcel_endpoint from OPA (points) to PWD_PARCELS (polygons).

Run from backend/:
    python scripts/update_philadelphia_endpoint.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db import async_session_maker

NEW_ENDPOINT = (
    "https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest"
    "/services/PWD_PARCELS/FeatureServer/0"
)


async def main() -> None:
    async with async_session_maker() as db:
        result = await db.execute(
            text("""
                UPDATE jurisdictions
                SET parcel_endpoint = :ep
                WHERE name = 'Philadelphia, PA'
                RETURNING id, name, parcel_endpoint
            """),
            {"ep": NEW_ENDPOINT},
        )
        row = result.fetchone()
        if row:
            print(f"Updated {row.name} ({row.id})")
            print(f"  parcel_endpoint = {row.parcel_endpoint}")
        else:
            print("Philadelphia, PA not found — nothing updated")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
