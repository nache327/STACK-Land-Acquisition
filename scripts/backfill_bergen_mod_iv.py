"""One-shot backfill of NJ MOD-IV class + assessment values for any NJ
county whose parcel ingest left messy free-text `land_use_code` and
NULL `assessed_value`/`is_residential`. Pulls canonical PROP_CLASS +
LAND_VAL/IMPRVT_VAL/NET_VALUE from NJOGIS Parcels_Composite_NJ_WM and
joins back on `parcels.apn = composite.PAMS_PIN`.

Originally Bergen-only; generalized to take --county / --jurisdiction-id
flags + a NJ_COUNTIES registry for batch runs.

Usage:
    # one county
    python backfill_bergen_mod_iv.py --county MORRIS --jurisdiction-id 746b...

    # one county, jurisdiction-id looked up from the registry
    python backfill_bergen_mod_iv.py --county MORRIS

    # default — Bergen, no flags (back-compat with the original run)
    python backfill_bergen_mod_iv.py

    # everything we know needs backfilling, one at a time
    python backfill_bergen_mod_iv.py --all-nj

Tweaks per review (carried over from the Bergen-only original):
  1. APN format pre-verified — 20/20 random Bergen APNs matched
     PAMS_PIN directly; we trust the same shape across NJ counties.
  2. Pulls PROP_CLASS + LAND_VAL + IMPRVT_VAL + NET_VALUE + YR_CONSTR +
     DWELL. OWNER_NAME deliberately skipped (statewide composite strips
     it for privacy — needs a per-county MOD-IV pull for owner outreach).
  3. UPDATE-only. APNs in composite but not in DB are reported as a
     diagnostic, never inserted.
  4. Final mapping writes PROP_CLASS into `land_use_code` (replacing the
     free-text junk). Does NOT touch `zoning_code` — MOD-IV class is
     land-use, not zoning.
  5. Idempotency guard: before fetching the composite for a county, the
     script checks if >50% of that county's parcels already have a
     canonical MOD-IV code in `land_use_code` and short-circuits if so.

is_residential mapping (per the storage-perm spec):
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

import argparse
import asyncio
import json
import os
import sys
import tempfile
from typing import Any

import asyncpg
import requests

DB_URL = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"

# Registry: NJ counties that have parcel ingest in the DB. Bergen was
# the first run (May 18 morning). The rest are added here so --all-nj
# can sweep them. Monmouth + Somerset are deliberately omitted from
# the sweep — Monmouth was already backfilled; Somerset already has
# canonical codes per the 2026-05-18 coverage audit (97% lu coverage
# with proper MOD-IV strings).
NJ_COUNTIES: dict[str, str] = {
    "BERGEN":    "4bf00234-4455-4987-a067-b22ee6b6aa1f",
    "MORRIS":    "746b7604-f362-470f-aa42-70dc8973b4ee",
    "MIDDLESEX": "9c039328-c995-41fc-83ce-fb4966fd402b",
    "ESSEX":     "67541a18-c599-423b-bf05-d68153af1e2f",
    "UNION":     "16dc5ad9-8211-47c6-bfad-93bf588b15e4",
    "HUDSON":    "e7a3304a-9684-4fb6-9e25-8ba54542fe1c",
    "PASSAIC":   "7a9ed95d-df89-4864-a203-f831a987b562",
    "HUNTERDON": "e8612f49-218b-48cc-9eb0-a1dd90cf583d",
    # Added 2026-05-21. This jurisdiction was originally created with
    # name="Burlington County, NJ" by a live-discovery resolve bug that
    # pointed at Ocean's GIS service; APN inspection confirmed the
    # parcels are Ocean (PAMS_PIN prefix 1501... = Ocean county code
    # in NJ MOD-IV). Renamed to "Ocean County, NJ" and backfilled via
    # this script with --county OCEAN. Real Burlington needs a fresh
    # ingest with a corrected source (NJOGIS Parcels_Composite_NJ_WM
    # filtered by COUNTY='BURLINGTON').
    "OCEAN":     "b26af20d-b32e-4319-beb3-dae6b48d0d99",
    # BURLINGTON: not yet ingested under a real jurisdiction row.
    # When the proper Burlington ingest lands, add the new
    # jurisdiction_id here with "BURLINGTON" as the key.
}

# Counties to sweep when --all-nj is passed. Bergen + Monmouth + Somerset
# already in good shape per the audit. Bergen is left in for paranoid
# idempotency re-checks (it will short-circuit via the >50% guard).
# Ocean is included so a future --all-nj re-runs the backfill if any
# previously-unmatched parcels get a PAMS_PIN added upstream.
ALL_NJ_SWEEP: list[str] = [
    "MORRIS", "MIDDLESEX", "ESSEX", "UNION",
    "HUDSON", "PASSAIC", "HUNTERDON", "OCEAN",
]

COMPOSITE = (
    "https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/"
    "Parcels_Composite_NJ_WM/FeatureServer/0/query"
)
PAGE = 2000  # ArcGIS Online server hard cap

_RESIDENTIAL_TRUE = {"2", "4C"}
_NON_RESIDENTIAL = {"1", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B",
                    "15A", "15B", "15C", "15D", "15E", "15F"}
# Canonical MOD-IV class strings — anything matching one of these in
# `land_use_code` is treated as "already backfilled" for the
# idempotency check.
_CANONICAL_CODES = _RESIDENTIAL_TRUE | _NON_RESIDENTIAL


def map_is_residential(prop_class: str | None) -> bool | None:
    if not prop_class:
        return None
    pc = prop_class.strip().upper()
    if pc in _RESIDENTIAL_TRUE:
        return True
    if pc in _NON_RESIDENTIAL:
        return False
    return None


def _safe_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def cache_path_for(county: str) -> str:
    """Per-county temp cache so we don't have to refetch 100k+ rows
    on a script retry. Resolves to e.g. /tmp/morris_composite_cache.json.
    """
    return os.path.join(
        tempfile.gettempdir(), f"{county.lower()}_composite_cache.json"
    )


def fetch_composite(county: str) -> dict[str, dict[str, Any]]:
    """Pull all rows for one county from the NJ composite, keyed by
    PAMS_PIN. Caches to a per-county temp file on first success."""
    path = cache_path_for(county)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cached = json.load(fh)
                # Sanity threshold — empty caches shouldn't short-circuit.
                if isinstance(cached, dict) and len(cached) > 1000:
                    print(f"  cache hit: {path} ({len(cached)} rows)")
                    return cached
        except Exception as exc:
            print(f"  cache read failed ({exc}); re-fetching")

    out: dict[str, dict[str, Any]] = {}
    offset = 0
    fields = "PAMS_PIN,PROP_CLASS,LAND_VAL,IMPRVT_VAL,NET_VALUE,YR_CONSTR,DWELL"
    while True:
        params = {
            "where": f"COUNTY='{county}'",
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
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh)
        print(f"  cached to {path}")
    except Exception as exc:
        print(f"  cache write failed: {exc}")
    return out


async def already_backfilled(conn: asyncpg.Connection, jid: str) -> bool:
    """Idempotency belt-and-suspenders. If >50% of the county's parcels
    already have a canonical MOD-IV class in `land_use_code`, treat it
    as already-backfilled and skip the run."""
    r = await conn.fetchrow(
        """
        SELECT
          COUNT(*)                                       AS total,
          COUNT(*) FILTER (WHERE land_use_code = ANY($2)) AS canonical
        FROM parcels WHERE jurisdiction_id = $1
        """,
        jid, list(_CANONICAL_CODES),
    )
    total, canonical = r["total"], r["canonical"]
    if total == 0:
        return False
    pct = 100 * canonical / total
    print(f"  pre-check: {canonical:,} / {total:,} parcels already canonical ({pct:.1f}%)")
    return pct > 50


async def backfill_one(county: str, jid: str) -> dict[str, Any]:
    """Run the backfill for one county. Returns a summary dict."""
    print(f"\n========== {county} ({jid}) ==========")
    print("Step 1: idempotency check...")
    conn = await asyncpg.connect(DB_URL, statement_cache_size=0, command_timeout=300)
    try:
        if await already_backfilled(conn, jid):
            print(f"  ALREADY BACKFILLED, skipping {county}")
            return {"county": county, "skipped": True, "updated": 0}
    finally:
        await conn.close()

    print("Step 2: fetching composite...")
    composite = fetch_composite(county)
    print(f"  composite total: {len(composite)} unique PAMS_PIN")
    if not composite:
        print(f"  [FAIL] composite returned 0 rows for COUNTY='{county}' — check NJOGIS spelling")
        return {"county": county, "skipped": False, "error": "empty_composite", "updated": 0}

    print("Step 3: reading APNs from DB...")
    conn = await asyncpg.connect(DB_URL, statement_cache_size=0, command_timeout=300)
    db_apns: set[str] = set()
    async with conn.transaction():
        async for r in conn.cursor(
            "SELECT apn FROM parcels WHERE jurisdiction_id = $1", jid,
        ):
            db_apns.add(r["apn"])
    print(f"  db total: {len(db_apns)} {county} parcels")

    composite_keys = set(composite.keys())
    matched = db_apns & composite_keys
    db_only = db_apns - composite_keys
    composite_only = composite_keys - db_apns
    print(f"  matched (both):                {len(matched):>7}")
    print(f"  in DB only (no composite row): {len(db_only):>7}  (NOT updated)")
    print(f"  in composite only (no DB row): {len(composite_only):>7}  (NOT inserted)")

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
    print("  PROP_CLASS distribution (matched):")
    for k in sorted(pc_dist, key=lambda x: -pc_dist[x])[:10]:
        print(f"    {k!s:>6}  {pc_dist[k]:>7}")

    print(f"Step 5: applying UPDATEs to {len(batch):,} rows...")
    # Smaller chunks reduce deadlock blast-radius; retry-on-deadlock
    # handles the case where another Railway job (matrix_bootstrap,
    # auto-scorer, etc.) holds locks on the same parcel rows mid-run.
    CHUNK = 1000
    updated_total = 0
    for i in range(0, len(batch), CHUNK):
        chunk = batch[i:i + CHUNK]
        params = [(pc, nv, isr, jid, apn) for (pc, nv, isr, apn) in chunk]
        attempt = 0
        while True:
            try:
                await conn.executemany(
                    """
                    UPDATE parcels
                    SET land_use_code = $1,
                        assessed_value = COALESCE($2, assessed_value),
                        is_residential = COALESCE($3, is_residential)
                    WHERE jurisdiction_id = $4::uuid
                      AND apn = $5
                    """,
                    params,
                )
                break
            except asyncpg.exceptions.DeadlockDetectedError:
                attempt += 1
                if attempt > 5:
                    print(f"  chunk {i:,}: 5 deadlock retries exhausted, giving up on this chunk")
                    break
                wait_s = 2 ** attempt  # exponential backoff: 2, 4, 8, 16, 32
                print(f"  chunk {i:,}: deadlock (attempt {attempt}), retrying in {wait_s}s")
                await asyncio.sleep(wait_s)
        updated_total += len(chunk)
        if (i // CHUNK) % 10 == 0:  # log every 10 chunks
            print(f"  applied {updated_total:,} / {len(batch):,}")

    print("Step 6: post-state...")
    r = await conn.fetchrow(
        """
        SELECT
          COUNT(*)                                       AS total,
          COUNT(*) FILTER (WHERE is_residential IS NOT NULL) AS is_res_set,
          COUNT(*) FILTER (WHERE is_residential = TRUE)  AS res_true,
          COUNT(*) FILTER (WHERE is_residential = FALSE) AS res_false,
          COUNT(*) FILTER (WHERE assessed_value > 0)     AS assessed_set,
          COUNT(*) FILTER (WHERE land_use_code = ANY($2)) AS canonical
        FROM parcels WHERE jurisdiction_id = $1
        """,
        jid, list(_CANONICAL_CODES),
    )
    for k, v in dict(r).items():
        print(f"    {k}: {v:,}" if isinstance(v, int) else f"    {k}: {v}")
    await conn.close()

    return {
        "county": county,
        "skipped": False,
        "updated": updated_total,
        "total": r["total"],
        "canonical": r["canonical"],
    }


async def run(counties: list[tuple[str, str]]) -> int:
    """Run the backfill for each (county, jid) pair sequentially."""
    summary: list[dict[str, Any]] = []
    for county, jid in counties:
        try:
            res = await backfill_one(county, jid)
            summary.append(res)
        except Exception as exc:
            print(f"  [FAIL] {county} FAILED: {exc}")
            summary.append({"county": county, "error": str(exc), "updated": 0})

    print("\n========== FINAL SUMMARY ==========")
    for s in summary:
        if s.get("skipped"):
            print(f"  {s['county']:<10}  SKIPPED (already backfilled)")
        elif s.get("error"):
            print(f"  {s['county']:<10}  FAILED  ({s['error']})")
        else:
            pct = 100 * s.get("canonical", 0) / s.get("total", 1) if s.get("total") else 0
            print(f"  {s['county']:<10}  updated={s['updated']:>7,}  canonical={s.get('canonical',0):>7,}/{s.get('total',0):>7,} ({pct:.1f}%)")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--county", help="NJ county name (uppercase, matches NJOGIS COUNTY column, e.g. BERGEN, MORRIS)")
    p.add_argument("--jurisdiction-id", help="Override jurisdiction_id; defaults to lookup in NJ_COUNTIES registry")
    p.add_argument("--all-nj", action="store_true", help="Sweep all NJ counties needing backfill (per ALL_NJ_SWEEP)")
    return p.parse_args()


async def main() -> int:
    args = parse_args()

    if args.all_nj:
        pairs = [(c, NJ_COUNTIES[c]) for c in ALL_NJ_SWEEP]
    elif args.county:
        c = args.county.upper()
        jid = args.jurisdiction_id or NJ_COUNTIES.get(c)
        if not jid:
            print(f"  no jurisdiction_id for county={c}; pass --jurisdiction-id explicitly")
            return 2
        pairs = [(c, jid)]
    else:
        # Back-compat: no flags = original Bergen-only run.
        pairs = [("BERGEN", NJ_COUNTIES["BERGEN"])]

    return await run(pairs)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
