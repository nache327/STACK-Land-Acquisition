"""One-shot: bump the Hot Deals filter_json with v2 hard-filter knobs.

Adds three new keys to the Hot Deals row in `buybox_filters`:
  - minAcres:          1.5    (drop sub-floor pad sites)
  - maxAcres:          15     (no oversized portfolio-scale tracts)
  - maxPricePerAcre:   2_000_000  ($2M/acre cap — keep raw-land economics)

Other filter_json keys (minPopulation, requireListed, etc.) are preserved
unchanged via jsonb_set. Idempotent: re-running just refreshes the values.

The `daily_email.py` worker reads these three keys from filter_json
when building the digest SQL — they fire as additional WHERE clauses,
NOT as new score factors. Selection-time filtering, not score-time.

Verification after running:
    SELECT filter_json FROM buybox_filters
     WHERE id = '1c5a257d-b971-4ff7-bdf8-1b9b62083879';

Expected: existing keys + the three new ones above.
"""
from __future__ import annotations

import asyncio
import sys

import asyncpg

DB_URL = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
HOT_DEALS_FILTER_ID = "1c5a257d-b971-4ff7-bdf8-1b9b62083879"

NEW_KEYS = {
    "minAcres": 1.5,
    "maxAcres": 15,
    "maxPricePerAcre": 2_000_000,
}


async def main() -> int:
    conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
    try:
        import json

        def _as_dict(raw) -> dict:
            """asyncpg returns jsonb as a string (no codec registered)."""
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str):
                return json.loads(raw) if raw else {}
            return {}

        # Pre-state
        row = await conn.fetchrow(
            "SELECT name, filter_json FROM buybox_filters WHERE id = $1::uuid",
            HOT_DEALS_FILTER_ID,
        )
        if row is None:
            print(f"  no filter row with id {HOT_DEALS_FILTER_ID}; aborting")
            return 1
        print(f"  filter:   {row['name']!r}")
        pre_fj = _as_dict(row["filter_json"])
        print(f"  pre-state filter_json keys: {sorted(pre_fj.keys())}")

        # Apply each new key via jsonb_set so we don't clobber existing keys.
        for k, v in NEW_KEYS.items():
            await conn.execute(
                """
                UPDATE buybox_filters
                   SET filter_json = jsonb_set(
                         COALESCE(filter_json, '{}'::jsonb),
                         ARRAY[$2],
                         $3::jsonb,
                         TRUE  -- create if missing
                       ),
                       updated_at = now()
                 WHERE id = $1::uuid
                """,
                HOT_DEALS_FILTER_ID, k, json.dumps(v),
            )
            print(f"  set {k} = {v}")

        # Post-state
        row = await conn.fetchrow(
            "SELECT filter_json FROM buybox_filters WHERE id = $1::uuid",
            HOT_DEALS_FILTER_ID,
        )
        print()
        print("  post-state filter_json:")
        fj = _as_dict(row["filter_json"])
        for k in sorted(fj.keys()):
            tag = "  <-- NEW" if k in NEW_KEYS else ""
            print(f"    {k!s:>22}: {fj[k]!r}{tag}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
