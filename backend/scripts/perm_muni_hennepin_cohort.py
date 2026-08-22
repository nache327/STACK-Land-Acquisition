"""Phase 7A.2 PIVOT — Hennepin wealth-band per-muni registration.

Same pattern as PR #271 Bellevue/Mercer re-jurisdictioning, scaled to 5
Hennepin munis. Registers each muni as its own prod jurisdiction and
moves parcels from Hennepin umbrella → per-muni jurisdiction.

Per Master's Phase 7A.2 dispatch (after PR #293 Phase 7A.1):
  - PATH 1 transparent pattern from Bellevue (parcels move via
    `UPDATE jurisdiction_id`, raw_attributes untouched).
  - Inline jurisdictions.bbox per muni (PR #261 codified).
  - 5 quality gates per muni.
  - NO zoning_districts work this dispatch — Hennepin has no city-zoning
    ingest yet. Phase 7A.3 (per-muni zoning publisher discovery + ingest)
    is a separate sprint per muni.
  - Don't author matrix (orchestrator's chain-pre-author covers Edina
    today + Wayzata/Plymouth/Eden Prairie/Minnetonka follow).

Munis (per Diagnostic PR #255 + Phase 7A.1 preflight counts):

  Edina         21,343 parcels — wealth-band #1, orchestrator Path-A ready
  Wayzata        1,992          — wealth-band #2, smallest/quickest flip
  Minnetonka    20,911          — wealth-band #3
  Plymouth      29,204          — wealth-band #4, largest in cohort
  Eden Prairie  22,956          — wealth-band #5

Hard rules:
  - raw_attributes preserved verbatim (Norfolk gate) — UPDATE only
    touches `jurisdiction_id` + `updated_at`; raw column untouched.
  - municipality matches prod_city_value EXACTLY (title-case from
    PR #233 → 'Edina' not 'EDINA').
  - Inline bbox UPDATE per muni; sanity range Twin Cities metro.
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

logger = logging.getLogger("hennepin_perm_muni")

HENNEPIN_JID = "39a8a612-e0af-4730-a661-2bad1b12f2f7"

# Twin Cities metro range covering all 5 munis. Per-muni bbox falls
# strictly within this envelope; if the computed bbox is outside,
# something has gone wrong (e.g. picked up a stray non-Hennepin row).
BBOX_LON_RANGE = (-93.85, -93.15)
BBOX_LAT_RANGE = (44.75, 45.30)

MUNIS = [
    # name, expected parcel count (per Phase 7A.1 preflight)
    {"name": "Edina, MN",        "city": "Edina",        "county": "Hennepin", "expect": 21343},
    {"name": "Wayzata, MN",      "city": "Wayzata",      "county": "Hennepin", "expect": 1992},
    {"name": "Minnetonka, MN",   "city": "Minnetonka",   "county": "Hennepin", "expect": 20911},
    {"name": "Plymouth, MN",     "city": "Plymouth",     "county": "Hennepin", "expect": 29204},
    {"name": "Eden Prairie, MN", "city": "Eden Prairie", "county": "Hennepin", "expect": 22956},
]


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _process_muni(conn: asyncpg.Connection, muni: dict) -> dict:
    print(f"\n=== {muni['name']} (expected {muni['expect']:,} parcels) ===")

    # Pre-move snapshot
    p_before = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
            WHERE jurisdiction_id = $1::uuid AND city = $2""",
        HENNEPIN_JID, muni["city"],
    )
    print(f"  Pre-move under Hennepin (city='{muni['city']}'): {p_before:,}")
    if p_before == 0:
        print(f"  HALT: 0 parcels match — possible title-case drift "
              f"(expected '{muni['city']}'). Aborting muni.")
        return {"name": muni["name"], "status": "halt", "moved": 0}
    if p_before != muni["expect"]:
        print(f"  WARNING: pre-move count {p_before} != expected "
              f"{muni['expect']} (Δ={p_before - muni['expect']:+d}); proceeding")

    # Per-muni atomic transaction
    async with conn.transaction():
        await conn.execute("SET LOCAL statement_timeout = 0")

        # 1. Idempotent jurisdiction find/create
        existing = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE name=$1 AND state='MN'",
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
                VALUES ($1::uuid, $2, 'MN', $3)
                """,
                str(new_jid), muni["name"], muni["county"],
            )
            print(f"  Registered new jurisdiction: {new_jid}")

        # 2. Move parcels
        status = await conn.execute(
            """
            UPDATE parcels
               SET jurisdiction_id = $2::uuid, updated_at = NOW()
             WHERE jurisdiction_id = $1::uuid AND city = $3
            """,
            HENNEPIN_JID, str(new_jid), muni["city"],
        )
        try:
            n_moved = int(status.split()[-1])
        except (ValueError, IndexError):
            n_moved = -1
        print(f"  Moved parcels: {n_moved}")

        # 3. Inline bbox UPDATE (PR #261 codified)
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
                f"{muni['name']}: bbox {bbox} outside Twin Cities envelope "
                f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(new_jid), json.dumps(bbox),
        )
        print(f"  Inline bbox UPDATEd: {bbox}")

    # Post-move verify
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

        # Hennepin roll-up after all moves
        print("\n=== Hennepin County, MN umbrella roll-up (post-moves) ===")
        hp = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid",
            HENNEPIN_JID,
        )
        print(f"  parcels (residual, unincorporated + non-cohort munis): {hp:,}")

        # Summary
        print("\n=== Phase 7A.2 SUMMARY ===")
        total_moved = sum(r["moved"] for r in results if r["status"] == "ok")
        print(f"  Munis processed     : {len(results)}")
        print(f"  Total parcels moved : {total_moved:,}")
        print(f"  Hennepin residual   : {hp:,}")
        print(f"  HALTs               : {sum(1 for r in results if r['status']=='halt')}")
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
