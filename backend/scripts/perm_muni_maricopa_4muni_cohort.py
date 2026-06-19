"""Phase 7B.2 — Maricopa 4-muni cohort registration (Scottsdale + CC + FH + Carefree).

Wave 2 second batch after Paradise Valley (PR #310). Differentiated strategy
per Master's 2026-06-19 dispatch:

  - SCOTTSDALE     : city-limits prefilter result (city='SCOTTSDALE' set
                     by ingest_maricopa_az_city_limits.py, authoritative
                     dissolved-by-CityName polygons). 149,911 parcels.
  - CAVE CREEK     : raw->>'PropertyCity'='CAVE CREEK' (Master's call —
                     <3% postal-vs-geographic delta, PropertyCity trusted).
                     ~16,566 parcels.
  - FOUNTAIN HILLS : raw->>'PropertyCity'='FOUNTAIN HILLS' (same logic,
                     <2% delta). ~15,971 parcels.
  - CAREFREE       : raw->>'PropertyCity'='CAREFREE' (default — Master
                     offered prefilter result 3,352 as alternative but
                     direct PropertyCity 2,993 for simplicity). ~2,993
                     parcels.

Per Master's Wave 2 second-batch dispatch (2026-06-19):
  - Scottsdale is the campaign's BIGGEST single per-muni flip (149,911
    parcels, 249-row orchestrator pre-stage 20dacfc HIGH Path A)
  - CC/FH/Carefree are LOW Path B (orchestrator pre-stage 9af5827 covers
    10+24+8 = 42 rows ordinance-derived)
  - All 4 fire in parallel via per-muni atomic transactions

Per-muni JIDs surfaced for Phase 7B.3 (Scottsdale) + Path B applies (3).

Hard rules:
  - raw_attributes preserved verbatim (Norfolk gate) — UPDATE touches
    jurisdiction_id + city + updated_at only
  - municipality matches case-discipline: UPPERCASE per AZ codification
  - Inline jurisdictions.bbox UPDATE per muni (PR #261 codified)
  - Per-muni atomic transaction (insert + UPDATE + bbox in one tx)
  - city column RESET to match new jurisdiction (for Scottsdale,
    already correct from prefilter; for CC/FH/Carefree, SET city =
    raw->>'PropertyCity' value for consistency)
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

logger = logging.getLogger("maricopa_4muni_phase7b2")

MARICOPA_JID = "eb8a2fc8-c0a6-4155-a4d3-d49bf46d44a6"

# Maricopa County envelope per PR #232: [-113.354, 32.687, -111.076, 34.044]
BBOX_LON_RANGE = (-113.5, -111.0)
BBOX_LAT_RANGE = (32.5, 34.5)

MUNIS = [
    {
        "name": "Scottsdale, AZ",
        "city": "SCOTTSDALE",
        "filter_kind": "city",  # use parcels.city (set by prefilter)
        "expected": 149_911,
        "muni_type": "city",
    },
    {
        "name": "Cave Creek, AZ",
        "city": "CAVE CREEK",
        "filter_kind": "raw_property_city",  # raw->>'PropertyCity'
        "expected": 16_566,
        "muni_type": "town",
    },
    {
        "name": "Fountain Hills, AZ",
        "city": "FOUNTAIN HILLS",
        "filter_kind": "raw_property_city",
        "expected": 15_971,
        "muni_type": "town",
    },
    {
        "name": "Carefree, AZ",
        "city": "CAREFREE",
        "filter_kind": "raw_property_city",
        "expected": 2_993,
        "muni_type": "town",
    },
]


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _process_muni(conn: asyncpg.Connection, muni: dict) -> dict:
    name = muni["name"]
    city = muni["city"]
    filter_kind = muni["filter_kind"]
    expected = muni["expected"]
    print(f"\n=== {name} (expected {expected:,}, filter={filter_kind}) ===")

    if filter_kind == "city":
        p_before_query = """
            SELECT COUNT(*) FROM parcels
                WHERE jurisdiction_id = $1::uuid AND city = $2
        """
    elif filter_kind == "raw_property_city":
        p_before_query = """
            SELECT COUNT(*) FROM parcels
                WHERE jurisdiction_id = $1::uuid
                  AND raw->>'PropertyCity' = $2
        """
    else:
        raise ValueError(f"unknown filter_kind: {filter_kind}")

    p_before = await conn.fetchval(p_before_query, MARICOPA_JID, city)
    print(f"  Pre-move: {p_before:,}")
    if p_before == 0:
        print(f"  HALT: 0 parcels match — aborting muni.")
        return {"name": name, "status": "halt", "moved": 0}

    async with conn.transaction():
        await conn.execute("SET LOCAL statement_timeout = 0")

        existing = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE name=$1 AND state='AZ'",
            name,
        )
        if existing:
            new_jid = existing["id"]
            print(f"  Found existing jurisdiction: {new_jid}")
        else:
            new_jid = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO jurisdictions (id, name, state, county)
                VALUES ($1::uuid, $2, 'AZ', 'Maricopa')
                """,
                str(new_jid), name,
            )
            print(f"  Registered new jurisdiction: {new_jid}")

        # Move parcels via filter_kind
        if filter_kind == "city":
            update_sql = """
                UPDATE parcels
                   SET jurisdiction_id = $2::uuid,
                       updated_at = NOW()
                 WHERE jurisdiction_id = $1::uuid AND city = $3
            """
        else:  # raw_property_city
            update_sql = """
                UPDATE parcels
                   SET jurisdiction_id = $2::uuid,
                       city = $3,
                       updated_at = NOW()
                 WHERE jurisdiction_id = $1::uuid
                   AND raw->>'PropertyCity' = $3
            """
        status = await conn.execute(
            update_sql, MARICOPA_JID, str(new_jid), city,
        )
        try:
            n_moved = int(status.split()[-1])
        except (ValueError, IndexError):
            n_moved = -1
        print(f"  Moved parcels: {n_moved}")

        # Inline bbox UPDATE
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
            raise RuntimeError(f"{name}: no parcel geometry post-move")
        bbox = [float(ext["minx"]), float(ext["miny"]),
                float(ext["maxx"]), float(ext["maxy"])]
        lon_lo, lon_hi = BBOX_LON_RANGE
        lat_lo, lat_hi = BBOX_LAT_RANGE
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(
                f"{name}: bbox {bbox} outside Maricopa envelope"
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
    print(f"  Post-move: parcels={p_after:,} with_geom={with_geom:,} "
          f"empty_raw={empty_raw}")
    return {
        "name": name,
        "city": city,
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

        print("\n=== Maricopa County, AZ umbrella roll-up ===")
        mp = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid",
            MARICOPA_JID,
        )
        print(f"  parcels (residual, non-cohort): {mp:,}")

        print("\n=== Phase 7B.2 4-MUNI SUMMARY ===")
        total_moved = sum(r["moved"] for r in results if r["status"] == "ok")
        print(f"  Munis processed     : {len(results)}")
        print(f"  Total parcels moved : {total_moved:,}")
        print(f"  Maricopa residual   : {mp:,}")
        print(f"  HALTs               : {sum(1 for r in results if r['status']=='halt')}")

        print("\n=== Per-muni JIDs (for Phase 7B.3 + orchestrator apply) ===")
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
