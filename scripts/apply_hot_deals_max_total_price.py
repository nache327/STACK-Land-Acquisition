"""Hot Deals tighten-guardrails: add maxTotalPrice=$7.5M to the Hot
Deals filter_json so 15ac x $900k/ac = $13.5M deals can't sneak
through the maxPricePerAcre=$2M filter.

Per user buy-box answers:
  Q2 "$10m is too much, but $2m per acre is also a good metric for
      too expensive"
  -> Both filters fire. Keep maxPricePerAcre=$2M, set maxTotalPrice
     below $10M. Picked $7.5M (middle of original 5/7.5/10 options).
  Q3 "Permitted should be scored higher than Conditional, not
      eliminate them"
  -> Already done: compositeScore.ts + buybox_scoring.py both give
     Permitted +30 and Conditional +15 (a 15-pt penalty). No filter
     change needed.

The daily_email worker reads maxTotalPrice from filter_json and
applies it as an additional WHERE clause in the digest SQL.

Idempotent. Re-running just resets the value.
"""
from __future__ import annotations

import asyncio
import json
import sys

import asyncpg

DB_URL = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
HOT_DEALS_FILTER_ID = "1c5a257d-b971-4ff7-bdf8-1b9b62083879"
NEW_KEY = "maxTotalPrice"
NEW_VALUE = 7_500_000


async def main() -> int:
    conn = await asyncpg.connect(DB_URL, statement_cache_size=0)
    try:
        def _as_dict(raw) -> dict:
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str):
                return json.loads(raw) if raw else {}
            return {}

        row = await conn.fetchrow(
            "SELECT name, filter_json FROM buybox_filters WHERE id = $1::uuid",
            HOT_DEALS_FILTER_ID,
        )
        if row is None:
            print(f"  no filter row with id {HOT_DEALS_FILTER_ID}; aborting")
            return 1
        print(f"  filter: {row['name']!r}")
        pre = _as_dict(row["filter_json"])
        print(f"  pre-state filter_json keys: {sorted(pre.keys())}")
        print(f"    maxAcres         = {pre.get('maxAcres')!r}")
        print(f"    minAcres         = {pre.get('minAcres')!r}")
        print(f"    maxPricePerAcre  = {pre.get('maxPricePerAcre')!r}")
        print(f"    maxTotalPrice    = {pre.get('maxTotalPrice')!r}")

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
            HOT_DEALS_FILTER_ID, NEW_KEY, json.dumps(NEW_VALUE),
        )
        print(f"  set {NEW_KEY} = {NEW_VALUE}")

        row = await conn.fetchrow(
            "SELECT filter_json FROM buybox_filters WHERE id = $1::uuid",
            HOT_DEALS_FILTER_ID,
        )
        post = _as_dict(row["filter_json"])
        print()
        print("  post-state filter_json:")
        for k in sorted(post.keys()):
            tag = "  <-- NEW" if k == NEW_KEY else ""
            print(f"    {k!s:>22}: {post[k]!r}{tag}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
