"""
Inspect zone_use_matrix for one jurisdiction. Reports each row with parcel-bind
count, current self_storage verdict, and confidence. Use to drive matrix
adjudication.

Run from backend/:
    python scripts/inspect_jurisdiction_matrix.py "Howard County, MD"
    python scripts/inspect_jurisdiction_matrix.py "Howard County, MD" --unclear-only

Output: tab-separated. Sorted by parcel bind count desc.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.db import async_session_maker

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def main(name: str, unclear_only: bool) -> None:
    async with async_session_maker() as db:
        jur = (
            await db.execute(
                text("SELECT id, name, state FROM jurisdictions WHERE name = :n"),
                {"n": name},
            )
        ).first()
        if jur is None:
            print(f"NOT_FOUND: {name}")
            return
        jid = jur.id

        rows = await db.execute(
            text(
                """
                SELECT
                  z.zone_code,
                  z.zone_name,
                  z.self_storage,
                  z.mini_warehouse,
                  z.light_industrial,
                  z.luxury_garage_condo,
                  z.confidence,
                  z.classification_source,
                  z.human_reviewed,
                  z.citations,
                  (SELECT COUNT(*) FROM parcels p
                     WHERE p.jurisdiction_id = z.jurisdiction_id
                       AND p.zoning_code = z.zone_code) AS parcel_bind_count
                FROM zone_use_matrix z
                WHERE z.jurisdiction_id = :jid
                  AND z.deleted_at IS NULL
                ORDER BY z.zone_code
                """
            ),
            {"jid": jid},
        )

        printed = 0
        total_unclear_bind = 0
        total_bind = 0
        all_rows = list(rows)
        for r in all_rows:
            total_bind += int(r.parcel_bind_count or 0)
            if r.self_storage == "unclear":
                total_unclear_bind += int(r.parcel_bind_count or 0)
        for r in sorted(all_rows, key=lambda x: -(x.parcel_bind_count or 0)):
            if unclear_only and r.self_storage != "unclear":
                continue
            print(
                "\t".join(
                    [
                        str(r.zone_code or ""),
                        str(r.zone_name or "")[:60],
                        str(r.self_storage or ""),
                        str(r.mini_warehouse or ""),
                        str(r.light_industrial or ""),
                        str(r.luxury_garage_condo or ""),
                        str(int(r.parcel_bind_count or 0)),
                        f"{(r.confidence or 0):.2f}",
                        str(r.classification_source or ""),
                        "Y" if r.human_reviewed else "N",
                    ]
                )
            )
            printed += 1
        print(
            f"\n--- {jur.name} ({jur.state}) total_rows={len(all_rows)} "
            f"printed={printed} total_parcel_bind={total_bind} "
            f"unclear_bind={total_unclear_bind} "
            f"unclear_share={(100*total_unclear_bind/total_bind if total_bind else 0):.1f}%",
            file=sys.stderr,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("name")
    p.add_argument("--unclear-only", action="store_true")
    a = p.parse_args()
    asyncio.run(main(a.name, a.unclear_only))
