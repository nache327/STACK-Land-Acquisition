"""Phase 7B.2 — Paradise Valley AZ per-muni registration (direct PropertyCity).

Wave 2 first per-muni Phase 7B.2 fire after Maricopa Phase 7B.1 (PR #305).
Per Master's differentiated Phase 7B.2 strategy (2026-06-19): use direct
PropertyCity for Paradise Valley (no city-limits prefilter). PV is a tiny
incorporated enclave; Master's call is to trust raw PropertyCity='PARADISE
VALLEY' even though the city-limits prefilter showed 1,990 parcels with
PV postal but centroid in Phoenix proper (likely East Phoenix sharing
PV postal delivery).

Filters on `raw->>'PropertyCity'='PARADISE VALLEY'` (immune to the prior
city-limits prefilter rewrites — raw_attributes preserves the original
verbatim PropertyCity value).

Per Master's 2026-06-19 dispatch:
  - Scottsdale uses city-limits prefilter (already done — 149,911 parcels)
  - Paradise Valley uses direct PropertyCity (this script — 9,847 parcels)
  - Cave Creek / Fountain Hills / Carefree: probe PropertyCity sanity first,
    then decide direct vs prefilter (separate scripts)

Side-effect: city column is RESET to 'PARADISE VALLEY' on all moved rows
(restores the 1,990 rows the prefilter UPDATEd to 'PHOENIX' so post-move
state is consistent: jurisdiction=Paradise Valley + city='PARADISE VALLEY').

Per Diagnostic PR #232 spec:
  Paradise Valley     ~10,071 parcels
  Bbox PASSES the 50% Class A primitive (no prefilter required)
  427 nonblank ZONECLASS in town zoning layer (Phase 7B.3 target)

Per Master's expected outcome:
  After PV Phase 7B.2 opens + 5/5 gates: orchestrator's pre-stage 9af5827
  (PV 10 rows LOW Path B ordinance) applies → +1 → 31.

Hard rules:
  - raw_attributes preserved verbatim (Norfolk gate)
  - municipality matches case-discipline: UPPERCASE 'PARADISE VALLEY'
  - Inline bbox UPDATE per muni (PR #261 codified)
  - Per-muni atomic transaction
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

logger = logging.getLogger("maricopa_pv_phase7b2")

MARICOPA_JID = "eb8a2fc8-c0a6-4155-a4d3-d49bf46d44a6"
JUR_NAME = "Paradise Valley, AZ"
JUR_STATE = "AZ"
JUR_COUNTY = "Maricopa"
PROPERTY_CITY = "PARADISE VALLEY"
EXPECTED_COUNT = 9847  # from raw PropertyCity probe 2026-06-19

# Paradise Valley bbox sanity range (per PR #232 spec).
BBOX_LON_RANGE = (-112.05, -111.85)
BBOX_LAT_RANGE = (33.48, 33.60)


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def main(confirm: bool) -> int:
    if not confirm:
        print("Refusing to fire without --i-know-this-writes-to-prod",
              file=sys.stderr)
        return 2

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=1800,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        print(f"\n=== {JUR_NAME} (raw PropertyCity='{PROPERTY_CITY}') ===")

        p_before = await conn.fetchval(
            """SELECT COUNT(*) FROM parcels
                WHERE jurisdiction_id = $1::uuid AND raw->>'PropertyCity' = $2""",
            MARICOPA_JID, PROPERTY_CITY,
        )
        print(f"  Pre-move under Maricopa "
              f"(raw->>'PropertyCity'='{PROPERTY_CITY}'): {p_before:,}")
        if p_before == 0:
            print(f"  HALT: 0 parcels match. raw_attributes may not preserve "
                  f"PropertyCity? Check ingest_maricopa_az_parcels.py "
                  f"RAW_PASSTHROUGH.")
            return 1
        if abs(p_before - EXPECTED_COUNT) > 100:
            print(f"  WARNING: pre-move count {p_before} differs from "
                  f"expected {EXPECTED_COUNT} by {p_before - EXPECTED_COUNT:+d}")

        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout = 0")

            # 1. Idempotent jurisdiction find/create
            existing = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
                JUR_NAME, JUR_STATE,
            )
            if existing:
                new_jid = existing["id"]
                print(f"  Found existing jurisdiction: {new_jid}")
            else:
                new_jid = uuid.uuid4()
                await conn.execute(
                    """
                    INSERT INTO jurisdictions (id, name, state, county)
                    VALUES ($1::uuid, $2, $3, $4)
                    """,
                    str(new_jid), JUR_NAME, JUR_STATE, JUR_COUNTY,
                )
                print(f"  Registered new jurisdiction: {new_jid}")

            # 2. Move parcels by raw PropertyCity + RESET city
            # (restores city column for parcels prefilter UPDATEd to other values)
            status = await conn.execute(
                """
                UPDATE parcels
                   SET jurisdiction_id = $2::uuid,
                       city = $3,
                       updated_at = NOW()
                 WHERE jurisdiction_id = $1::uuid
                   AND raw->>'PropertyCity' = $3
                """,
                MARICOPA_JID, str(new_jid), PROPERTY_CITY,
            )
            try:
                n_moved = int(status.split()[-1])
            except (ValueError, IndexError):
                n_moved = -1
            print(f"  Moved parcels (jurisdiction_id + city reset): {n_moved}")

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
                raise RuntimeError(f"{JUR_NAME}: no parcel geometry post-move")
            bbox = [float(ext["minx"]), float(ext["miny"]),
                    float(ext["maxx"]), float(ext["maxy"])]
            lon_lo, lon_hi = BBOX_LON_RANGE
            lat_lo, lat_hi = BBOX_LAT_RANGE
            if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
                raise RuntimeError(
                    f"{JUR_NAME}: bbox {bbox} outside expected range "
                    f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi})"
                )
            await conn.execute(
                "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
                str(new_jid), json.dumps(bbox),
            )
            print(f"  Inline bbox UPDATEd: {bbox}")

        # Post-move verification (5 gates)
        print("\n=== 5-GATE VERDICT ===")
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
        city_consistent = await conn.fetchval(
            """SELECT COUNT(*) FROM parcels
                WHERE jurisdiction_id = $1::uuid AND city = $2""",
            str(new_jid), PROPERTY_CITY,
        )
        print(f"GATE 1 parcels moved match expected: {n_moved:,} "
              f"({'PASS' if abs(n_moved - EXPECTED_COUNT) <= 100 else 'FAIL'})")
        print(f"GATE 2 raw_attributes empty: {empty_raw} (Norfolk) "
              f"{'PASS' if empty_raw == 0 else 'FAIL'}")
        print(f"GATE 3 parcels.geom non-null: {with_geom:,} / {p_after:,} "
              f"({'PASS' if with_geom == p_after else 'FAIL'})")
        print(f"GATE 4 jurisdictions.bbox: populated {bbox} "
              f"{'PASS' if bbox else 'FAIL'}")
        print(f"GATE 5 city='{PROPERTY_CITY}' consistency: "
              f"{city_consistent:,} / {p_after:,} "
              f"({'PASS' if city_consistent == p_after else 'FAIL'})")
        print(f"\n  new_jid: {new_jid}")

        # Maricopa umbrella roll-up
        print("\n=== Maricopa County, AZ umbrella roll-up ===")
        mp = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid",
            MARICOPA_JID,
        )
        print(f"  Maricopa residual (post-PV-move): {mp:,}")
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
