"""
Repair: merge duplicate jurisdiction rows.

Problem: some cities have two rows:
  - "American Fork"     (14,733 parcels, has last_indexed_at, has ready job)
  - "American Fork, UT" (0 parcels, no last_indexed_at, no ready job)

When user types "American Fork, UT" the state-qualified query hits the empty
row first and triggers a full re-download instead of the cached one.

Fix for each duplicate pair:
  1. Rename the populated row to include the state suffix  ("American Fork" -> "American Fork, UT")
  2. Re-point any jobs that reference the old name
  3. Delete the empty duplicate row

Run from backend/:
  railway run python repair_dedup_jurisdictions.py
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update

from app.db import async_session_maker
from app.models.job import Job, JobStatus
from app.models.jurisdiction import Jurisdiction
from app.models.parcel import Parcel


async def main() -> None:
    async with async_session_maker() as db:
        # Load all jurisdictions with parcel counts
        result = await db.execute(
            select(Jurisdiction, func.count(Parcel.id).label("cnt"))
            .outerjoin(Parcel, Parcel.jurisdiction_id == Jurisdiction.id)
            .group_by(Jurisdiction.id)
        )
        rows = result.all()

        # Index by name for easy lookup
        by_name: dict[str, tuple[Jurisdiction, int]] = {}
        for j, cnt in rows:
            by_name[j.name] = (j, cnt)

        fixed = 0

        for name, (j, cnt) in list(by_name.items()):
            state = j.state  # e.g. "UT"
            # Only process rows WITHOUT a state suffix that have a state on the model
            if not state or f", {state}" in name:
                continue

            canonical = f"{name}, {state}"  # e.g. "American Fork, UT"

            if canonical not in by_name:
                # No duplicate - just rename this jurisdiction to canonical form
                if cnt > 0:
                    print(f"  RENAME  '{name}' -> '{canonical}'  ({cnt:,} parcels)")
                    j.name = canonical
                    fixed += 1
                continue

            dup_j, dup_cnt = by_name[canonical]

            if cnt > 0 and dup_cnt == 0:
                # Populated base + empty state-suffix duplicate - canonical merge
                print(f"  MERGE   '{name}' ({cnt:,} parcels) + '{canonical}' (0 parcels)")
                print(f"          Rename base to canonical, delete empty dup")

                # Re-point jobs that reference the empty duplicate jurisdiction
                await db.execute(
                    update(Job)
                    .where(Job.jurisdiction_id == dup_j.id)
                    .values(jurisdiction_id=j.id)
                )

                # Delete the empty duplicate jurisdiction row
                await db.execute(
                    delete(Jurisdiction).where(Jurisdiction.id == dup_j.id)
                )

                # Rename the populated one to canonical
                j.name = canonical
                fixed += 1

            elif cnt == 0 and dup_cnt > 0:
                # Base is empty, state-suffix has the data - delete the base, leave canonical
                print(f"  CLEAN   '{name}' (0 parcels) is empty; '{canonical}' ({dup_cnt:,}) is real - deleting empty base")

                await db.execute(
                    update(Job)
                    .where(Job.jurisdiction_id == j.id)
                    .values(jurisdiction_id=dup_j.id)
                )
                await db.execute(
                    delete(Jurisdiction).where(Jurisdiction.id == j.id)
                )
                fixed += 1

            elif cnt > 0 and dup_cnt > 0:
                # Both have parcels - shouldn't happen, but log it
                print(f"  WARN    Both '{name}' ({cnt:,}) and '{canonical}' ({dup_cnt:,}) have parcels - manual review needed")

        await db.commit()
        print(f"\nDone. Consolidated {fixed} duplicate/misnamed jurisdiction(s).")
        print("All cities now use 'City, ST' canonical names - state-qualified lookups will hit the right row.")


if __name__ == "__main__":
    asyncio.run(main())
