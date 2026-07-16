"""Backfill forsale_listings owner/last-sale/broker-phone from raw_row JSONB.

The CoStar parser previously dropped Owner *, Recorded Owner *, Last Sale *,
and (for the new report template) broker phone — but raw_row preserved every
column. This populates the new 0046 columns for rows already ingested, so no
re-upload is needed. Idempotent: only fills columns that are currently NULL.

    python scripts/_backfill_listing_owner_from_raw.py            # dry-run count
    python scripts/_backfill_listing_owner_from_raw.py --apply
"""
from __future__ import annotations

import argparse
import asyncio

import asyncpg
from _db import get_sync_dsn

# new_column -> raw_row JSON keys to try (first non-empty wins)
MAP = {
    "owner_name":           ["Owner Name"],
    "owner_phone":          ["Owner Phone"],
    "owner_contact":        ["Owner Contact"],
    "recorded_owner_name":  ["Recorded Owner Name"],
    "recorded_owner_phone": ["Recorded Owner Phone"],
    "last_sale_price":      ["Last Sale Price"],
    "last_sale_date":       ["Last Sale Date"],
    # broker phone: the new template uses Sale Company Phone / Sales Contact Phone
    "listing_broker_phone": ["Sale Company Phone", "Sales Contact Phone", "Listing Broker Phone"],
}
# owner_address = "Owner Address" + ", " + "Owner City State Zip"


def _coalesce_sql(col: str, keys: list[str]) -> str:
    parts = [f"NULLIF(btrim(raw_row->>'{k}'), '')" for k in keys]
    return f"COALESCE({', '.join(parts)})"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = await asyncpg.connect(get_sync_dsn())
    await c.execute("SET statement_timeout = 0")

    # scope: costar rows where at least one target column is still NULL and raw_row has data
    n = await c.fetchval(
        "SELECT count(*) FROM forsale_listings WHERE source='costar' AND raw_row IS NOT NULL "
        "AND (owner_name IS NULL AND owner_phone IS NULL AND last_sale_price IS NULL "
        "AND listing_broker_phone IS NULL)"
    )
    print(f"candidate rows (costar, owner/phone/last-sale still NULL): {n}")
    if not args.apply:
        print("dry-run — re-run with --apply")
        await c.close()
        return

    sets = []
    for col, keys in MAP.items():
        cast = "::numeric" if col == "last_sale_price" else ("::date" if col == "last_sale_date" else "")
        expr = _coalesce_sql(col, keys)
        if cast == "::date":
            # tolerate ISO datetime strings; cast fails safely via NULLIF+try is not available,
            # so wrap in a guarded cast using to_date-friendly substring (first 10 chars = YYYY-MM-DD)
            expr = f"NULLIF(left({expr}, 10), '')::date"
        elif cast == "::numeric":
            expr = f"replace(replace({expr}, '$',''), ',','')::numeric"
        sets.append(f"{col} = COALESCE({col}, {expr})")
    # owner_address from two raw keys
    addr = ("owner_address = COALESCE(owner_address, "
            "NULLIF(btrim(concat_ws(', ', NULLIF(btrim(raw_row->>'Owner Address'),''), "
            "NULLIF(btrim(raw_row->>'Owner City State Zip'),''))), ''))")
    sets.append(addr)

    sql = ("UPDATE forsale_listings SET " + ", ".join(sets) +
           " WHERE source='costar' AND raw_row IS NOT NULL")
    res = await c.execute(sql)
    print("UPDATE result:", res)
    # report populated counts
    for col in ("owner_name", "owner_phone", "owner_address", "last_sale_price", "listing_broker_phone"):
        cnt = await c.fetchval(f"SELECT count(*) FROM forsale_listings WHERE source='costar' AND {col} IS NOT NULL")
        print(f"  {col}: {cnt} non-null")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())
