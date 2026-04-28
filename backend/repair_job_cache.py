"""
One-time repair: ensure every jurisdiction with parcels loads instantly.

For each jurisdiction that has parcels:
  1. Set last_indexed_at if NULL
  2. Ensure a ready Job row exists with jurisdiction_id pointing to it

Run from backend/:
  railway run python repair_job_cache.py
"""
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel


async def main() -> None:
    async with async_session_maker() as db:
        # All jurisdictions + their parcel counts
        result = await db.execute(
            select(
                Jurisdiction,
                func.count(Parcel.id).label("parcel_count"),
            )
            .outerjoin(Parcel, Parcel.jurisdiction_id == Jurisdiction.id)
            .group_by(Jurisdiction.id)
            .order_by(Jurisdiction.name)
        )
        rows = result.all()

        now = datetime.now(timezone.utc)
        patched_ts = 0
        patched_job = 0

        for jurisdiction, parcel_count in rows:
            if parcel_count == 0:
                print(f"  SKIP  {jurisdiction.name} — 0 parcels")
                continue

            # 1. Ensure last_indexed_at is set
            if jurisdiction.last_indexed_at is None:
                jurisdiction.last_indexed_at = now
                patched_ts += 1
                print(f"  TS    {jurisdiction.name} ({parcel_count:,} parcels) — set last_indexed_at")
            else:
                print(f"  OK-TS {jurisdiction.name} ({parcel_count:,} parcels) — last_indexed_at already set")

            # 2. Ensure a ready job with jurisdiction_id exists
            r = await db.execute(
                select(Job)
                .where(
                    Job.status == JobStatus.ready,
                    Job.jurisdiction_id == jurisdiction.id,
                )
                .order_by(Job.updated_at.desc())
                .limit(1)
            )
            ready_job = r.scalars().first()

            if ready_job is not None:
                print(f"  OK-JB {jurisdiction.name} — ready job {ready_job.id} exists")
                continue

            # Try to find an existing ready job by jurisdiction_input (old jobs had no jurisdiction_id)
            r2 = await db.execute(
                select(Job)
                .where(
                    Job.status == JobStatus.ready,
                    text("LOWER(jurisdiction_input) LIKE :name"),
                )
                .params(name=f"{jurisdiction.name.lower().split(',')[0]}%")
                .order_by(Job.updated_at.desc())
                .limit(1)
            )
            old_job = r2.scalars().first()

            if old_job is not None:
                # Adopt the existing job — just stamp its jurisdiction_id
                old_job.jurisdiction_id = jurisdiction.id
                patched_job += 1
                print(f"  ADOPT {jurisdiction.name} — stamped jurisdiction_id on job {old_job.id}")
            else:
                # Create a minimal synthetic ready job so the cache path fires
                new_job = Job(
                    jurisdiction_input=jurisdiction.name,
                    jurisdiction_id=jurisdiction.id,
                    status=JobStatus.ready,
                    target_uses=[
                        "self_storage",
                        "mini_warehouse",
                        "light_industrial",
                        "luxury_garage_condo",
                    ],
                )
                db.add(new_job)
                patched_job += 1
                print(f"  SYNTH {jurisdiction.name} — created synthetic ready job")

        await db.commit()
        print(f"\nDone. Patched timestamps: {patched_ts}, patched/created jobs: {patched_job}")


if __name__ == "__main__":
    asyncio.run(main())
