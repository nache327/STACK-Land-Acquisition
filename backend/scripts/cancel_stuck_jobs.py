"""Cancel all non-terminal Philadelphia jobs so the queued one can run."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from app.db import async_session_maker
from app.models.job import Job, JobStatus

TERMINAL = {JobStatus.ready, JobStatus.failed, JobStatus.cancelled}


async def main() -> None:
    async with async_session_maker() as db:
        result = await db.execute(
            select(Job).order_by(Job.created_at.desc()).limit(15)
        )
        jobs = result.scalars().all()

        print("Recent jobs:")
        for j in jobs:
            print(f"  {j.id}  {j.status:<22}  created={str(j.created_at)[:19]}")

        # Cancel anything that is active (not terminal) except the newest queued job
        newest_queued = next((j for j in jobs if j.status == JobStatus.queued), None)
        cancelled = 0
        for j in jobs:
            if j.status in TERMINAL:
                continue
            if newest_queued and j.id == newest_queued.id:
                continue  # keep this one — let it run
            print(f"Cancelling {j.id} ({j.status}) ...")
            j.status = JobStatus.cancelled
            j.locked_by = None
            j.locked_at = None
            cancelled += 1

        await db.commit()
        print(f"\nCancelled {cancelled} job(s).")
        if newest_queued:
            print(f"Kept queued job {newest_queued.id} — it should pick up a worker shortly.")


if __name__ == "__main__":
    asyncio.run(main())
