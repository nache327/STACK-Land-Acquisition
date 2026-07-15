import asyncio, asyncpg, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts._db import get_sync_dsn
JIDS={"Birmingham":"97474794-c0c8-4903-9fae-51fb8fc795bc","BloomfieldHills":"e914f6d4-9dfd-467a-a0a6-0e6b02c28691",
      "BeverlyHills":"53edb548-7359-4e9d-9ff0-ec81fadb8c5d","BloomfieldTwp":"15ecf7aa-e9d4-4804-a64c-282f8b172701",
      "Franklin":"ec91da85-6cf3-4243-bbff-5d7f71017c44"}
async def m():
    c=await asyncpg.connect(get_sync_dsn(),timeout=60)
    out=[]
    for n,j in JIDS.items():
        r=await c.fetchval("select count(*) from parcel_ring_metrics prm join parcels p on p.id=prm.parcel_id where p.jurisdiction_id=$1 and prm.drive_time_minutes=10",j)
        out.append(f"{n}={r}")
    print(" ".join(out))
    await c.close()
asyncio.run(m())
