"""
Rename all Utah 'City, UT' jurisdictions to just 'City' so the old Railway
geocoder (which returns bare city names) finds the correct data rows.
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from scripts._db import get_dsn

URL = get_dsn()

# source id (has data) -> target id (empty duplicate to absorb into)
MERGE = {
    '3b02c87c-3bda-4898-97fe-1b469695c568': '0cf50881-fdf3-4149-8c9f-6db758c4a08f',
    '1251e8d0-9976-4860-a6bd-3f30b1528ae8': 'd3757bf8-b4f1-4142-bece-8c774c863955',
}

# id -> new bare city name (no ", UT")
RENAME = {
    'cb5017c6-a845-4ffd-91a3-7dc26e2e5ce9': 'Bluffdale',
    'b320fac8-d8ef-4325-8722-022036169218': 'Cottonwood Heights',
    '1f0d6f93-8e5c-462b-88ed-9d6a9e107bc1': 'Eagle Mountain',
    'f90d021b-98fe-47b0-ad31-bf8c1b2dd23f': 'Farmington',
    '8c489a6c-fdec-4d4d-98c1-3157d0233a8b': 'Herriman',
    '648f20ae-ff2d-4876-b936-d67c20488eec': 'Hurricane',
    '0a9e2fb0-031a-4905-a07f-b645dadc5827': 'Kaysville',
    '5f366dff-dde9-471c-8fb2-58894796535d': 'Midvale',
    '0fd008ca-1a7e-41d6-9995-c59c6fe8a8d9': 'Millcreek',
    'f4e528c2-35aa-4856-a159-14471f3e8277': 'North Salt Lake',
    'fe0f482f-da80-4673-b83b-556b0cca7ba4': 'Ogden',
    '47fb1539-2aff-4b1c-8e8b-58ff6a6f08c7': 'Orem',
    '354ba226-bd38-4721-a0b5-8716b577ab4c': 'Payson',
    'ea4648de-5e6b-4a83-adca-eb47f947841d': 'Pleasant Grove',
    'b3b0b5f4-b6c1-4761-9e4a-10b9c2206740': 'Roy',
    '69ad5926-6404-4a17-8387-59e4f9f3a917': 'South Jordan',
    'e44b2d47-ce45-4de0-84a9-ead0ee2f9741': 'Taylorsville',
    'ee7678ff-9d5d-4ed0-896c-0a7061ade1f8': 'Tooele',
    'cad6d22f-7447-4a26-8385-587e93f7f340': 'Washington',
    '60506efb-2485-4198-ad01-9419941cc78d': 'West Haven',
    'f6273f2b-0911-440d-b639-fa80090f7f54': 'West Jordan',
}


async def run():
    engine = create_async_engine(URL)
    async with engine.begin() as conn:
        for src_id, tgt_id in MERGE.items():
            r = await conn.execute(
                text(f"UPDATE parcels SET jurisdiction_id = '{tgt_id}' WHERE jurisdiction_id = '{src_id}'")
            )
            print(f"Parcels moved: {r.rowcount}")
            r2 = await conn.execute(
                text(f"UPDATE zone_use_matrix SET jurisdiction_id = '{tgt_id}' WHERE jurisdiction_id = '{src_id}'")
            )
            print(f"Zones moved: {r2.rowcount}")
            await conn.execute(text(f"DELETE FROM jurisdictions WHERE id = '{src_id}'"))
            r3 = await conn.execute(text(f"SELECT name FROM jurisdictions WHERE id = '{tgt_id}'"))
            print(f"Kept: {r3.fetchone()[0]}")

        for jid, new_name in RENAME.items():
            await conn.execute(
                text(f"UPDATE jurisdictions SET name = :name WHERE id = :id"),
                {"name": new_name, "id": jid}
            )
            print(f"Renamed to: {new_name}")

    print("Done.")

asyncio.run(run())
