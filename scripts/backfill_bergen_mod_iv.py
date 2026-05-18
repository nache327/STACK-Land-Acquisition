"""One-shot: backfill MOD-IV class + assessment values for Bergen County NJ
parcels from the NJOGIS statewide composite.

Bergen was ingested with empty `raw`, NULL `is_residential`, NULL
`assessed_value`, and a messy free-text `land_use_code`. This script
pulls the canonical NJ MOD-IV columns from Parcels_Composite_NJ_WM
and joins back to our DB on `parcels.apn = composite.PAMS_PIN`.

Tweaks per review:
  1. APN format pre-checked against composite — 20/20 random Bergen
     APNs matched PAMS_PIN directly. No transformation needed.
  2. Pulls more than PROP_CLASS — also LAND_VAL, IMPRVT_VAL, NET_VALUE,
     YR_CONSTR, DWELL. (OWNER_NAME is empty in the statewide composite —
     deferred to a per-county MOD-IV pull.)
  3. UPDATE-only. APNs in composite but not in DB are reported as a
     diagnostic, never inserted.
  4. Final mapping is honest: writes PROP_CLASS into `land_use_code`
     (replacing free-text junk). Does NOT touch `zoning_code` —
     MOD-IV class is land-use, not zoning. Downstream candidate
     filter changes are a separate PR.

is_residential mapping (per review):
    '1'    → FALSE  (vacant — STORAGE-ELIGIBLE)
    '2'    → TRUE   (residential <4 units)
    '3A'   → FALSE  (farm regular — separate bucket)
    '3B'   → FALSE  (farm qualified)
    '4A'   → FALSE  (commercial — eligible)
    '4B'   → FALSE  (industrial — eligible)
    '4C'   → TRUE   (apartment 5+ units — residential)
    '5A','5B','6A','6B','15A'..'15F' → FALSE
    other  → NULL   (leave as-is, don't guess)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from typing import Any

import asyncpg
import requests

CACHE_PATH = os.path.join(tempfile.gettempdir(), "bergen_composite_cache.json")

DB_URL = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
BERGEN = "4bf00234-4455-4987-a067-b22ee6b6aa1f"

COMPOSITE = (
    "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/"
    "Parcels_Composite_NJ_WM/FeatureServer/0/query"
)
PAGE = 2000  # ArcGIS Online server hard cap

_RESIDENTIAL_TRUE = {"2", "4C"}
_NON_RESIDENTIAL = {"1", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B",
                    "15A", "15B", "15C", "15D", "15E", "15F"}


def map_is_residential(prop_class: str | None) -> bool | None:
    if not prop_class:
        return None
    pc = prop_class.strip().upper()
    if pc in _RESIDENTIAL_TRUE:
        return True
    if pc in _NON_RESIDENTIAL:
        return False
    return None  # unknown class — leave NULL rather than guess


def _safe_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def fetch_bergen_composite() -> dict[str, dict[str, Any]]:
    """Pull all Bergen rows from the NJ composite, keyed by PAMS_PIN.
    Caches to a temp file on first success — re-runs hit the cache."""
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                cached = json.load(fh)
                if isinstance(cached, dict) and len(cached) > 100000:
                    print(f"  cache hit: {CACHE_PATH} ({len(cached)} rows)")
                    return cached
        except Exception as exc:
            print(f"  cache read failed ({exc}); re-fetching")

    out: dict[str, dict[str, Any]] = {}
    offset = 0
    fields = "PAMS_PIN,PROP_CLASS,LAND_VAL,IMPRVT_VAL,NET_VALUE,YR_CONSTR,DWELL"
    while True:
        params = {
            "where": "COUNTY='BERGEN'",
            "outFields": fields,
            "returnGeometry": "false",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": PAGE,
            "orderByFields": "OBJECTID",
        }
        resp = requests.get(COMPOSITE, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        feats = data.get("features", [])
        for f in feats:
            a = f.get("attributes", {})
            pin = a.get("PAMS_PIN")
            if not pin:
                continue
            out[pin] = a
        got = len(feats)
        print(f"  fetched offset={offset:>6} batch={got:>4}  running_total={len(out):>6}")
        if got < PAGE:
            break
        offset += PAGE
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(out, fh)
        print(f"  cached to {CACHE_PATH}")
    except Exception as exc:
        print(f"  cache write failed: {exc}")
    return out


async def main() -> int:
    print("Step 1: fetching Bergen composite (COUNTY='BERGEN')...")
    composite = fetch_bergen_composite()
    print(f"  composite total: {len(composite)} unique PAMS_PIN")
    print()

    print("Step 2: reading Bergen APNs from DB...")
    conn = await asyncpg.connect(
        DB_URL, statement_cache_size=0, command_timeout=300,
    )
    db_apns: set[str] = set()
    async with conn.transaction():
        async for r in conn.cursor(
            "SELECT apn FROM parcels WHERE jurisdiction_id = $1",
            BERGEN,
        ):
            db_apns.add(r["apn"])
    print(f"  db total: {len(db_apns)} Bergen parcels")
    print()

    print("Step 3: join diagnostics")
    composite_keys = set(composite.keys())
    matched = db_apns & composite_keys
    db_only = db_apns - composite_keys
    composite_only = composite_keys - db_apns
    print(f"  matched (both):                {len(matched):>7}")
    print(f"  in DB only (no composite row): {len(db_only):>7}  (will NOT be updated)")
    print(f"  in composite only (no DB row): {len(composite_only):>7}  (will NOT be inserted — diagnostic only)")
    if db_only:
        sample = sorted(db_only)[:10]
        print(f"    sample db_only: {sample}")
    print()

    print("Step 4: building UPDATE batch...")
    batch: list[tuple[str | None, int | None, bool | None, str]] = []
    pc_dist: dict[str, int] = {}
    for apn in matched:
        a = composite[apn]
        pc = (a.get("PROP_CLASS") or None)
        if pc:
            pc = pc.strip().upper()
        is_res = map_is_residential(pc)
        net_value = _safe_int(a.get("NET_VALUE"))
        batch.append((pc, net_value, is_res, apn))
        pc_dist[pc or "NULL"] = pc_dist.get(pc or "NULL", 0) + 1

    print("  PROP_CLASS distribution (matched parcels):")
    for k in sorted(pc_dist, key=lambda x: -pc_dist[x]):
        print(f"    {k!s:>6}  {pc_dist[k]:>7}")
    print()

    print(f"Step 5: applying UPDATEs to {len(batch):,} rows (UPDATE only, no INSERT)...")
    # asyncpg's executemany over UPDATE is fast enough for ~280k rows but
    # we chunk for memory + progress visibility.
    CHUNK = 5000
    updated_total = 0
    for i in range(0, len(batch), CHUNK):
        chunk = batch[i:i + CHUNK]
        await conn.executemany(
            """
            UPDATE parcels
            SET land_use_code = $1,
                assessed_value = COALESCE($2, assessed_value),
                is_residential = COALESCE($3, is_residential)
            WHERE jurisdiction_id = $4::uuid
              AND apn = $5
            """,
            [(pc, nv, isr, BERGEN, apn) for (pc, nv, isr, apn) in chunk],
        )
        updated_total += len(chunk)
        print(f"  applied {updated_total:,} / {len(batch):,}")
    print()

    print("Step 6: post-state sanity check")
    r = await conn.fetchrow(
        """
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE is_residential IS NOT NULL) AS is_res_set,
          COUNT(*) FILTER (WHERE is_residential = TRUE)  AS res_true,
          COUNT(*) FILTER (WHERE is_residential = FALSE) AS res_false,
          COUNT(*) FILTER (WHERE assessed_value > 0) AS assessed_set,
          COUNT(*) FILTER (WHERE land_use_code ~ '^[1-6]') AS modiv_classified
        FROM parcels WHERE jurisdiction_id = $1
        """,
        BERGEN,
    )
    print("  Bergen post-state:")
    for k, v in dict(r).items():
        print(f"    {k}: {v:,}" if isinstance(v, int) else f"    {k}: {v}")

    await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
