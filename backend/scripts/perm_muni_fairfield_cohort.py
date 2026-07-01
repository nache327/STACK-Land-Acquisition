"""Phase 7C.2 — Fairfield CT wealth-band per-muni registration.

Wave 3 dispatch — Master's Fairfield CT cohort sprint after Hennepin wave
demonstrated peak Lane A throughput. Phase 7C.1 SKIP (parcels already
ingested + city populated via PR #228 with 261k Fairfield CT parcels).

Same PATH 1 transparent pattern from Bellevue (PR #271) and Hennepin
Phase 7A.2 (PR #294), scaled to 5 Fairfield CT munis:

  Stamford      25,524 parcels — wealth-band #1, HIGH Path A
                  (orchestrator's 42-row pre-stage 9c5cee9, direct ArcGIS)
  Greenwich     18,042         — wealth-band #2, LOW Path B (PDF/web-map)
  Westport       9,947         — wealth-band #3, LOW Path B (AxisGIS + enCodePlus)
  New Canaan     7,386         — wealth-band #4, LOW Path B (eCode360 + PDF)
  Darien         5,831         — wealth-band #5, LOW Path B (PDF-only)

Total cohort: 66,730 parcels (~25.6 % of Fairfield County's 261k).

Per Master's Phase 7C dispatch:
  - PATH 1 transparent pattern from Bellevue/Hennepin precedents.
  - Inline jurisdictions.bbox per muni (PR #261 codified).
  - 5 quality gates per muni.
  - Title-case discipline matches PR #228 (Town_Name → city = 'Greenwich' not 'GREENWICH').
  - NO zoning_districts work this dispatch — Phase 7C.3 (per-muni zoning
    ingest) follows for each muni; Stamford fires immediately under HIGH
    Path A confidence.
  - Don't author matrix (orchestrator's chain-pre-author covers).

Hard rules:
  - raw_attributes preserved verbatim (Norfolk gate) — UPDATE only touches
    `jurisdiction_id` + `updated_at`; raw column untouched.
  - municipality matches prod_city_value EXACTLY ('Stamford' not 'STAMFORD').
  - Inline bbox UPDATE per muni; sanity range Fairfield County extent.
  - Per-muni transaction for atomicity (jurisdiction insert + parcel
    UPDATE + bbox in one tx).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path

import asyncpg
import dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("fairfield_perm_muni")

FAIRFIELD_JID = "66230887-aabe-4d62-aebb-856939ba77bb"

# Fairfield County CT envelope. Per-muni bbox falls strictly within;
# outside-envelope = stray non-Fairfield row → halt.
BBOX_LON_RANGE = (-73.75, -73.05)
BBOX_LAT_RANGE = (40.95, 41.55)  # Greenwich/Westport coastline dips slightly south of 41.0 at Long Island Sound

MUNIS = [
    # name, city (PR #228 title-case), expected parcel count
    {"name": "Stamford, CT",    "city": "Stamford",    "county": "Fairfield", "expect": 25524},
    {"name": "Greenwich, CT",   "city": "Greenwich",   "county": "Fairfield", "expect": 18042},
    {"name": "Westport, CT",    "city": "Westport",    "county": "Fairfield", "expect": 9947},
    {"name": "New Canaan, CT",  "city": "New Canaan",  "county": "Fairfield", "expect": 7386},
    {"name": "Darien, CT",      "city": "Darien",      "county": "Fairfield", "expect": 5831},
]


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _process_muni(conn: asyncpg.Connection, muni: dict) -> dict:
    print(f"\n=== {muni['name']} (expected {muni['expect']:,} parcels) ===")

    p_before = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
            WHERE jurisdiction_id = $1::uuid AND city = $2""",
        FAIRFIELD_JID, muni["city"],
    )
    print(f"  Pre-move under Fairfield (city='{muni['city']}'): {p_before:,}")
    if p_before == 0:
        print(f"  HALT: 0 parcels match — possible title-case drift "
              f"(expected '{muni['city']}'). Aborting muni.")
        return {"name": muni["name"], "status": "halt", "moved": 0}
    if p_before != muni["expect"]:
        print(f"  WARNING: pre-move count {p_before} != expected "
              f"{muni['expect']} (Δ={p_before - muni['expect']:+d}); proceeding")

    async with conn.transaction():
        await conn.execute("SET LOCAL statement_timeout = 0")

        existing = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE name=$1 AND state='CT'",
            muni["name"],
        )
        if existing:
            new_jid = existing["id"]
            print(f"  Found existing jurisdiction: {new_jid}")
        else:
            new_jid = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO jurisdictions (id, name, state, county)
                VALUES ($1::uuid, $2, 'CT', $3)
                """,
                str(new_jid), muni["name"], muni["county"],
            )
            print(f"  Registered new jurisdiction: {new_jid}")

        status = await conn.execute(
            """
            UPDATE parcels
               SET jurisdiction_id = $2::uuid, updated_at = NOW()
             WHERE jurisdiction_id = $1::uuid AND city = $3
            """,
            FAIRFIELD_JID, str(new_jid), muni["city"],
        )
        try:
            n_moved = int(status.split()[-1])
        except (ValueError, IndexError):
            n_moved = -1
        print(f"  Moved parcels: {n_moved}")

        ext = await conn.fetchrow(
            """
            SELECT ST_XMin(ST_Extent(geom)) AS minx,
                   ST_YMin(ST_Extent(geom)) AS miny,
                   ST_XMax(ST_Extent(geom)) AS maxx,
                   ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            str(new_jid),
        )
        if ext is None or ext["minx"] is None:
            raise RuntimeError(f"{muni['name']}: no parcel geometry post-move")
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        lon_lo, lon_hi = BBOX_LON_RANGE
        lat_lo, lat_hi = BBOX_LAT_RANGE
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(
                f"{muni['name']}: bbox {bbox} outside Fairfield envelope "
                f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(new_jid), json.dumps(bbox),
        )
        print(f"  Inline bbox UPDATEd: {bbox}")

    p_after = await conn.fetchval(
        "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid",
        str(new_jid),
    )
    empty_raw = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
            WHERE jurisdiction_id = $1::uuid
              AND (raw IS NULL OR raw = '{}'::jsonb)""",
        str(new_jid),
    )
    with_geom = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
            WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL""",
        str(new_jid),
    )
    print(f"  Post-move under {muni['name']}: parcels={p_after:,} "
          f"with_geom={with_geom:,} empty_raw={empty_raw}")
    print(f"  new_jid: {new_jid}")
    return {
        "name": muni["name"],
        "city": muni["city"],
        "status": "ok",
        "new_jid": str(new_jid),
        "moved": n_moved,
        "bbox": bbox,
        "empty_raw": empty_raw,
        "with_geom": with_geom,
    }


async def main(confirm: bool) -> int:
    if not confirm:
        print("Refusing to fire without --i-know-this-writes-to-prod",
              file=sys.stderr)
        return 2

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=900,
    )
    results = []
    try:
        await conn.execute("SET statement_timeout = 0")
        for muni in MUNIS:
            r = await _process_muni(conn, muni)
            results.append(r)

        print("\n=== Fairfield County, CT umbrella roll-up (post-moves) ===")
        fp = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid",
            FAIRFIELD_JID,
        )
        print(f"  parcels (residual, non-cohort munis): {fp:,}")

        print("\n=== Phase 7C.2 SUMMARY ===")
        total_moved = sum(r["moved"] for r in results if r["status"] == "ok")
        print(f"  Munis processed     : {len(results)}")
        print(f"  Total parcels moved : {total_moved:,}")
        print(f"  Fairfield residual  : {fp:,}")
        print(f"  HALTs               : {sum(1 for r in results if r['status']=='halt')}")

        print("\n=== Per-muni JIDs (for Phase 7C.3 dispatch) ===")
        for r in results:
            if r["status"] == "ok":
                print(f"  {r['name']:22s} {r['new_jid']}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--i-know-this-writes-to-prod", action="store_true",
        help="Confirmation flag.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(main(args.i_know_this_writes_to_prod)))
