import asyncio, asyncpg
from scripts._db import get_sync_dsn

NOTE = (" | LGC demoted: sibling leak vs human-verified self_storage=prohibited; "
        "'garage condo' marker was inference-boilerplate, not a named use (QC 2026-07-21)")


async def main():
    c = await asyncpg.connect(get_sync_dsn())
    try:
        r = await c.fetchrow(
            """select m.id, m.luxury_garage_condo::text lgc from zone_use_matrix m
                 join jurisdictions j on j.id=m.jurisdiction_id
                where j.name='Monmouth County, NJ' and m.zone_code='BR' and m.deleted_at is null""")
        print(f"before: id={r['id']} lgc={r['lgc']}")
        await c.execute(
            """update zone_use_matrix
                  set luxury_garage_condo='prohibited', notes = coalesce(notes,'') || $2
                where id=$1""", r["id"], NOTE)
        after = await c.fetchval(
            "select luxury_garage_condo::text from zone_use_matrix where id=$1", r["id"])
        print(f"after:  lgc={after}")
        n = await c.fetchval(
            """select count(*) from zone_use_matrix
                where deleted_at is null and human_reviewed=true and self_storage::text='prohibited'
                  and luxury_garage_condo::text in ('permitted','conditional')
                  and light_industrial::text is distinct from 'permitted'""")
        print(f"REMAINING true sibling leaks (all jurisdictions): {n}")
    finally:
        await c.close()


asyncio.run(main())
