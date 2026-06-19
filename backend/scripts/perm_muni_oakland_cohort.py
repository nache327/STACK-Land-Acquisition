"""Phase 7E.2 — Oakland MI wealth-band per-muni registration.

Wave 4 cohort after Phase 7E.1 (PR #314). Same PATH 1 transparent pattern
from Bellevue/Hennepin/Fairfield/Maricopa/Allegheny, scaled to 5 Oakland
munis. CVTTAXDESCRIPTION exact-equality filter (UPPERCASE + political-
entity prefix preserved verbatim by Phase 7E.1 adapter).

Munis (per Diagnostic PR #260 + 7E.1 post-ingest verification):

  CITY OF BIRMINGHAM            9,778 parcels — PRIMARY 57-list
  CITY OF BLOOMFIELD HILLS      1,833 parcels
  CHARTER TOWNSHIP OF BLOOMFIELD 18,224 parcels
  VILLAGE OF FRANKLIN           1,312 parcels
  VILLAGE OF BEVERLY HILLS      4,174 parcels

Per Master's Phase 7E.2 dispatch (2026-06-19):
  - PATH 1 transparent pattern
  - Inline jurisdictions.bbox per muni (PR #261 codified)
  - 5 quality gates per muni
  - CVTTAXDESCRIPTION verbatim (UPPERCASE + 'CITY OF'/'VILLAGE OF'/
    'CHARTER TOWNSHIP OF' prefix)

Per Diagnostic PR #260: use CVTTAXDESCRIPTION not SITECITY (postal noise
over-selects Bloomfield-area).

Hard rules:
  - raw_attributes preserved verbatim (Norfolk gate) — UPDATE only touches
    `jurisdiction_id` + `updated_at`; raw column untouched.
  - CVTTAXDESCRIPTION exact-equality
  - Per-muni transaction for atomicity
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

logger = logging.getLogger("oakland_perm_muni")

OAKLAND_JID = "1f8dbc98-098a-42d1-a2b8-6dd80b6a658f"

# Oakland County MI envelope (Detroit metro).
BBOX_LON_RANGE = (-83.8, -83.0)
BBOX_LAT_RANGE = (42.3, 43.0)

MUNIS = [
    # (jurisdictions.name, parcels.city CVTTAXDESCRIPTION verbatim, expected count)
    {"name": "Birmingham, MI",          "city": "CITY OF BIRMINGHAM",             "expected": 9778},
    {"name": "Bloomfield Hills, MI",    "city": "CITY OF BLOOMFIELD HILLS",       "expected": 1833},
    {"name": "Bloomfield Township, MI", "city": "CHARTER TOWNSHIP OF BLOOMFIELD", "expected": 18224},
    {"name": "Franklin, MI",            "city": "VILLAGE OF FRANKLIN",            "expected": 1312},
    {"name": "Beverly Hills, MI",       "city": "VILLAGE OF BEVERLY HILLS",       "expected": 4174},
]


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _process_muni(conn: asyncpg.Connection, muni: dict) -> dict:
    print(f"\n=== {muni['name']} (city='{muni['city']}', expected {muni['expected']:,}) ===")

    p_before = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
            WHERE jurisdiction_id = $1::uuid AND city = $2""",
        OAKLAND_JID, muni["city"],
    )
    print(f"  Pre-move: {p_before:,}")
    if p_before == 0:
        print(f"  HALT: 0 parcels match. Aborting muni.")
        return {"name": muni["name"], "status": "halt", "moved": 0}

    async with conn.transaction():
        await conn.execute("SET LOCAL statement_timeout = 0")

        existing = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE name=$1 AND state='MI'",
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
                VALUES ($1::uuid, $2, 'MI', 'Oakland')
                """,
                str(new_jid), muni["name"],
            )
            print(f"  Registered new jurisdiction: {new_jid}")

        status = await conn.execute(
            """
            UPDATE parcels
               SET jurisdiction_id = $2::uuid, updated_at = NOW()
             WHERE jurisdiction_id = $1::uuid AND city = $3
            """,
            OAKLAND_JID, str(new_jid), muni["city"],
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
                f"{muni['name']}: bbox {bbox} outside Oakland envelope"
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
    print(f"  Post-move: parcels={p_after:,} with_geom={with_geom:,} "
          f"empty_raw={empty_raw}")
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
        print("Refusing without --i-know-this-writes-to-prod", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=1800,
    )
    results = []
    try:
        await conn.execute("SET statement_timeout = 0")
        for muni in MUNIS:
            r = await _process_muni(conn, muni)
            results.append(r)

        print("\n=== Oakland County, MI umbrella roll-up ===")
        op = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid",
            OAKLAND_JID,
        )
        print(f"  parcels (residual, non-cohort): {op:,}")

        print("\n=== Phase 7E.2 5-MUNI SUMMARY ===")
        total_moved = sum(r["moved"] for r in results if r["status"] == "ok")
        print(f"  Munis processed     : {len(results)}")
        print(f"  Total parcels moved : {total_moved:,}")
        print(f"  Oakland residual    : {op:,}")
        print(f"  HALTs               : {sum(1 for r in results if r['status']=='halt')}")

        print("\n=== Per-muni JIDs (for Phase 7E.3 dispatch) ===")
        for r in results:
            if r["status"] == "ok":
                print(f"  {r['name']:25s} {r['new_jid']}")
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
