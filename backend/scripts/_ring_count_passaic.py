import asyncio, asyncpg, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts._db import get_sync_dsn
JID='7a9ed95d-df89-4864-a203-f831a987b562'
async def m():
    c=await asyncpg.connect(get_sync_dsn())
    n=await c.fetchval("select count(*) from parcel_ring_metrics prm join parcels p on p.id=prm.parcel_id where p.jurisdiction_id=$1 and prm.drive_time_minutes=10",JID)
    print(n)
    await c.close()
asyncio.run(m())
