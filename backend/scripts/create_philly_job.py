"""Create a fresh Philadelphia job, bypassing dedup."""
import asyncio, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import redis as redis_lib
from sqlalchemy import text
from app.config import settings
from app.db import async_session_maker
from app.models.job import Job, JobStatus

async def main():
    async with async_session_maker() as db:
        result = await db.execute(
            text("SELECT id, name FROM jurisdictions WHERE name ILIKE '%philadelphia%'")
        )
        jur = result.fetchone()
        if not jur:
            print("Philadelphia jurisdiction not found!")
            return
        print(f"Jurisdiction: {jur.name} ({jur.id})")

        job = Job(
            id=uuid.uuid4(),
            jurisdiction_id=jur.id,
            status=JobStatus.queued,
            jurisdiction_input="Philadelphia, PA",
            force=True,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        print(f"Created job: {job.id}")

        # Enqueue via Redis directly (dramatiq not available locally)
        r = redis_lib.from_url(settings.redis_url)
        import json
        message = {
            "queue_name": "default",
            "actor_name": "run_pipeline",
            "args": [str(job.id)],
            "kwargs": {},
            "options": {},
            "message_id": str(uuid.uuid4()),
            "message_timestamp": 0,
        }
        r.lpush("dramatiq:default", json.dumps(message).encode())
        print(f"Enqueued. Dashboard: https://zoning-finder.vercel.app/dashboard/{job.id}")

asyncio.run(main())
