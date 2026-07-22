"""Set Nache's hard triage floors on the board/digest filters.

Two defaults from the 2026-07-22 buy-box walkthrough:
  - minPop3mi = 30000  ("too rural" floor — both lanes)
  - maxAcres  = 15     (upper acreage band — oversize isn't actionable)

Applied to every dashboard-enabled filter (filter_json.dashboardEnabled='true')
AND the seed default filters (is_default=true). minPop3mi is always (re)set;
maxAcres is only added where a filter hasn't already set its own, so an
operator's explicit override is never clobbered.

This is a one-time data step, NOT a migration (backfills don't belong in
Railway-boot migrations). Idempotent — safe to re-run.

USAGE (from backend/):  python scripts/set_board_filter_defaults.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _db import get_dsn  # noqa: E402

_TARGET = (
    "(filter_json->>'dashboardEnabled' = 'true' OR is_default = true)"
)

# Always (re)set minPop3mi; only add maxAcres where it's not already present.
_SET_POP = text(f"""
    UPDATE buybox_filters
       SET filter_json = filter_json || '{{"minPop3mi": 30000}}'::jsonb
     WHERE {_TARGET}
""")
_SET_MAXACRES = text(f"""
    UPDATE buybox_filters
       SET filter_json = filter_json || '{{"maxAcres": 15}}'::jsonb
     WHERE {_TARGET}
       AND (filter_json->>'maxAcres') IS NULL
""")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_async_engine(get_dsn())
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        before = (await db.execute(text(
            f"SELECT id, filter_json->>'maxAcres' AS ma, filter_json->>'minPop3mi' AS mp "
            f"FROM buybox_filters WHERE {_TARGET}"
        ))).all()
        print(f"{len(before)} target filter(s):")
        for r in before:
            print(f"  {str(r[0])[:8]}  maxAcres={r[1]}  minPop3mi={r[2]}")

        if args.dry_run:
            print("dry-run — no changes.")
        else:
            n1 = (await db.execute(_SET_POP)).rowcount
            n2 = (await db.execute(_SET_MAXACRES)).rowcount
            await db.commit()
            print(f"minPop3mi set on {n1}; maxAcres added on {n2}.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
