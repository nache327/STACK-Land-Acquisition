"""Clear vendor-mirror ordinance_url values (catch #37 hygiene, 2026-08-21).

The abandoned Zoneomics batch scraper (batch_populate_ordinances.py:358) wrote
`zoneomics.com/code/<slug>` into jurisdictions.ordinance_url for its UT-pilot
jurisdictions (~17-21 rows, flagged in the 2026-07-29 ordinance-URL audit). A
vendor mirror is not a primary source: those URLs poison the freshness
sentinel's URL surface (it would monitor the vendor's re-crawl, not the town's
code) and taint any golden-sample vendor benchmark (self-agreement).

This NULLs them, printing every old value first so they're preserved in the
session log / can be repointed to primary hosts muni-by-muni later. NULL is the
honest state — 61 jurisdictions already have no ordinance_url (script-grounded;
normal). SELECT before/after per catch #42. Dry-run by default.

  python scripts/_drafts/_repoint_zoneomics_ordinance_urls.py           # dry-run
  python scripts/_drafts/_repoint_zoneomics_ordinance_urls.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg  # noqa: E402

from _db import get_sync_dsn  # noqa: E402


async def run(apply: bool) -> int:
    conn = await asyncpg.connect(get_sync_dsn(), timeout=60, statement_cache_size=0)
    try:
        rows = await conn.fetch(
            """SELECT id, name, state, ordinance_url FROM jurisdictions
                WHERE ordinance_url ~* 'zoneomics'
                ORDER BY state, name"""
        )
        print(f"jurisdictions with zoneomics ordinance_url: {len(rows)}")
        for r in rows:
            print(f"  {r['state'] or '??'}  {r['name']}: {r['ordinance_url']}  (id={r['id']})")
        if not rows:
            return 0
        if not apply:
            print("dry-run (no writes). Re-run with --apply.")
            return 0
        result = await conn.execute(
            "UPDATE jurisdictions SET ordinance_url = NULL WHERE ordinance_url ~* 'zoneomics'"
        )
        remaining = await conn.fetchval(
            "SELECT count(*) FROM jurisdictions WHERE ordinance_url ~* 'zoneomics'"
        )
        print(f"{result}; remaining zoneomics URLs: {remaining}")
        return 0 if remaining == 0 else 1
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    return asyncio.run(run(ap.parse_args().apply))


if __name__ == "__main__":
    raise SystemExit(main())
