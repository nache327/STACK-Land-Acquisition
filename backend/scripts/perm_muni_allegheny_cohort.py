"""Phase 7F.2 — Allegheny PA wealth-band per-muni registration.

Wave 5 final-wedge cohort after Phase 7F.1 (PR #315 MERGED). Same Bellevue/
Hennepin/Fairfield/Maricopa PATH 1 transparent pattern, scaled to 5
Allegheny munis. Parcels were ingested with `city` already set to LABEL
verbatim (title-case + Borough/Township suffix + apostrophe-stripped) by
ingest_allegheny_pa_parcels.py, so per-muni filter is exact-equality on city.

Munis (per Allegheny LABEL canonical format):

  Fox Chapel Borough          ~2,179 parcels — PRIMARY 57-list (MUNICODE=868)
  O Hara Township             adjacent (MUNICODE=931, apostrophe-stripped)
  Aspinwall Borough           adjacent small (MUNICODE=801)
  Sewickley Borough           Ohio River wealth (MUNICODE=851)
  Sewickley Heights Borough   Ord. No. 294 PDF flagged (MUNICODE=869)

Per Master's Phase 7F.2 dispatch (2026-06-19):
  - PATH 1 transparent pattern from Bellevue/Hennepin/Fairfield/Maricopa
  - Inline jurisdictions.bbox per muni (PR #261 codified)
  - 5 quality gates per muni
  - LABEL case discipline preserved verbatim
  - NO zoning_districts work this dispatch — Phase 7F.3 follows once
    Diagnostic verdict on live FeatureServer probes returns (Greenwich
    precedent: LOW Path B → HIGH Path A promotion possible)

Hard rules:
  - raw_attributes preserved verbatim (Norfolk gate) — UPDATE only touches
    `jurisdiction_id` + `updated_at`; raw column untouched.
  - LABEL exact-equality (e.g. 'Fox Chapel Borough', 'O Hara Township')
  - Per-muni transaction for atomicity (jurisdiction insert + parcel
    UPDATE + bbox in one tx)
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

logger = logging.getLogger("allegheny_perm_muni")

ALLEGHENY_JID = "2a6a5d52-58c4-4e36-a5bd-45fc8d3e76c7"

# Allegheny County PA envelope (per ingest_allegheny_pa_parcels.py bbox check).
BBOX_LON_RANGE = (-80.5, -79.5)
BBOX_LAT_RANGE = (40.1, 40.8)

MUNIS = [
    # name, label (= parcels.city set by 7F.1), municode (for reference)
    {"name": "Fox Chapel, PA",        "city": "Fox Chapel Borough",        "municode": 868, "muni_type": "borough"},
    {"name": "O'Hara, PA",            "city": "O Hara Township",           "municode": 931, "muni_type": "township"},
    {"name": "Aspinwall, PA",         "city": "Aspinwall Borough",         "municode": 801, "muni_type": "borough"},
    {"name": "Sewickley, PA",         "city": "Sewickley Borough",         "municode": 851, "muni_type": "borough"},
    {"name": "Sewickley Heights, PA", "city": "Sewickley Heights Borough", "municode": 869, "muni_type": "borough"},
]


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _process_muni(conn: asyncpg.Connection, muni: dict) -> dict:
    print(f"\n=== {muni['name']} (city='{muni['city']}', MUNICODE={muni['municode']}) ===")

    p_before = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels
            WHERE jurisdiction_id = $1::uuid AND city = $2""",
        ALLEGHENY_JID, muni["city"],
    )
    print(f"  Pre-move: {p_before:,}")
    if p_before == 0:
        print(f"  HALT: 0 parcels match. Possible LABEL drift "
              f"(expected '{muni['city']}'). Aborting muni.")
        return {"name": muni["name"], "status": "halt", "moved": 0}

    async with conn.transaction():
        await conn.execute("SET LOCAL statement_timeout = 0")

        existing = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE name=$1 AND state='PA'",
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
                VALUES ($1::uuid, $2, 'PA', 'Allegheny')
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
            ALLEGHENY_JID, str(new_jid), muni["city"],
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
                f"{muni['name']}: bbox {bbox} outside Allegheny envelope "
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

        print("\n=== Allegheny County, PA umbrella roll-up ===")
        ap = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid",
            ALLEGHENY_JID,
        )
        print(f"  parcels (residual, non-cohort): {ap:,}")

        print("\n=== Phase 7F.2 5-MUNI SUMMARY ===")
        total_moved = sum(r["moved"] for r in results if r["status"] == "ok")
        print(f"  Munis processed     : {len(results)}")
        print(f"  Total parcels moved : {total_moved:,}")
        print(f"  Allegheny residual  : {ap:,}")
        print(f"  HALTs               : {sum(1 for r in results if r['status']=='halt')}")

        print("\n=== Per-muni JIDs (for Phase 7F.3 dispatch) ===")
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
