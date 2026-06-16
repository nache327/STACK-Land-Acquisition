"""Phase 6B-PIVOT — Move Bellevue + Mercer Island from King County → own jurisdictions.

Per Master's plan revision after PR #267 surfaced the county-wide
parcel_zoning_code_coverage_pct gate: for massive-county-with-tiny-wealth-pocket
targets (WA, AZ, MI, MN), the operational unit is per-muni, not per-county.

This script:
  1. Registers two new jurisdictions: "Bellevue, WA" and "Mercer Island, WA"
  2. Moves matching parcels, zoning_districts, and zone_use_matrix rows
     from King County (1e65c053-…) → the new per-muni jurisdiction_ids
  3. Inline jurisdictions.bbox UPDATE per new jurisdiction (PR #261 codified)
  4. Transaction per muni for atomicity (parcels + districts + matrix in one tx)

After this lands + ONE refresh per new jurisdiction:
  - Bellevue: cov 85.2% (clears 70% gate), matrix already authored
    by PR #266 → projected operational, count 20 → 21
  - Mercer Island: cov 63.2% (sub-gate), matrix authored, stays partial
    until Task E city-fallback re-fire lifts coverage

King County retains:
  - 635,186 - 33,217 - 7,448 = 594,521 parcels
  - 9,933 (Phase 6A.2) - 991 - 48 = 8,894 districts (none yet; WAZA only
    loaded for these 2 munis)
  - Wait — Phase 6A.2 only loaded WAZA for Bellevue + Mercer. So after
    the move, King has 0 zoning_districts and 0 matrix rows. That's
    correct: King's county-wide ingest is incomplete (the wedge insight
    from PR #266's footnote).
  - bbox NOT recomputed (still covers full King county geography minus
    the 2 munis' bboxes; this is fine for the audit's missing_bbox
    check — has_bbox stays True).

Hard rules honored:
  - raw_attributes preserved verbatim (just an UPDATE on jurisdiction_id;
    raw column untouched)
  - Inline jurisdictions.bbox per new jurisdiction (PR #261)
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

logger = logging.getLogger("rejurisdiction")

KING_JID = "1e65c053-da54-4733-9d77-ca9aa3b27a7b"

MUNIS = [
    {
        "name": "Bellevue, WA",
        "state": "WA",
        "county": "King",
        "parcels_city": "Bellevue",
        "districts_muni_name": "Bellevue",
        "matrix_municipality": "Bellevue",
        # Bellevue parcel extent inside King — sanity-check before
        # writing the inline bbox. Per spec: bbox WGS84
        # [-122.2511546, 47.5284504, -122.0843964, 47.6617612].
        "bbox_lon_range": (-122.35, -122.00),
        "bbox_lat_range": (47.45, 47.75),
    },
    {
        "name": "Mercer Island, WA",
        "state": "WA",
        "county": "King",
        "parcels_city": "Mercer Island",
        "districts_muni_name": "Mercer Island",
        "matrix_municipality": "Mercer Island",
        # Mercer Island parcel extent per spec WGS84
        # [-122.2547522, 47.5240329, -122.1999567, 47.5966780].
        "bbox_lon_range": (-122.35, -122.15),
        "bbox_lat_range": (47.45, 47.65),
    },
]


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def _process_muni(conn: asyncpg.Connection, muni: dict) -> None:
    print(f"\n=== {muni['name']} ===")

    # Idempotent jurisdiction find/create
    existing = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE name=$1 AND state=$2",
        muni["name"], muni["state"],
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
            str(new_jid), muni["name"], muni["state"], muni["county"],
        )
        print(f"  Registered new jurisdiction: {new_jid}")

    # Pre-move snapshot
    p_before = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid AND city = $2""",
        KING_JID, muni["parcels_city"],
    )
    d_before = await conn.fetchval(
        """
        SELECT COUNT(*) FROM zoning_districts
        WHERE jurisdiction_id = $1::uuid
          AND raw_attributes->>'muni_name' = $2
        """,
        KING_JID, muni["districts_muni_name"],
    )
    m_before = await conn.fetchval(
        """
        SELECT COUNT(*) FROM zone_use_matrix
        WHERE jurisdiction_id = $1::uuid
          AND municipality = $2
        """,
        KING_JID, muni["matrix_municipality"],
    )
    print(f"  Pre-move in King: parcels={p_before:,} districts={d_before} matrix={m_before}")

    # Transaction per muni — atomic move of all three asset types.
    async with conn.transaction():
        await conn.execute("SET LOCAL statement_timeout = 0")

        # Move parcels
        status = await conn.execute(
            """
            UPDATE parcels
               SET jurisdiction_id = $2::uuid, updated_at = NOW()
             WHERE jurisdiction_id = $1::uuid AND city = $3
            """,
            KING_JID, str(new_jid), muni["parcels_city"],
        )
        try:
            n_p = int(status.split()[-1])
        except (ValueError, IndexError):
            n_p = -1
        print(f"  Moved parcels: {n_p}")

        # Move zoning_districts (filter via raw_attributes->>'muni_name')
        status = await conn.execute(
            """
            UPDATE zoning_districts
               SET jurisdiction_id = $2::uuid
             WHERE jurisdiction_id = $1::uuid
               AND raw_attributes->>'muni_name' = $3
            """,
            KING_JID, str(new_jid), muni["districts_muni_name"],
        )
        try:
            n_d = int(status.split()[-1])
        except (ValueError, IndexError):
            n_d = -1
        print(f"  Moved zoning_districts: {n_d}")

        # Move zone_use_matrix
        status = await conn.execute(
            """
            UPDATE zone_use_matrix
               SET jurisdiction_id = $2::uuid
             WHERE jurisdiction_id = $1::uuid
               AND municipality = $3
            """,
            KING_JID, str(new_jid), muni["matrix_municipality"],
        )
        try:
            n_m = int(status.split()[-1])
        except (ValueError, IndexError):
            n_m = -1
        print(f"  Moved zone_use_matrix: {n_m}")

        # Inline bbox UPDATE (PR #261 codified pattern).
        ext = await conn.fetchrow(
            """
            SELECT
                ST_XMin(ST_Extent(geom)) AS minx,
                ST_YMin(ST_Extent(geom)) AS miny,
                ST_XMax(ST_Extent(geom)) AS maxx,
                ST_YMax(ST_Extent(geom)) AS maxy
            FROM parcels WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            str(new_jid),
        )
        if ext is None or ext["minx"] is None:
            raise RuntimeError(f"{muni['name']}: no parcel geometry post-move; aborting tx")
        bbox = [
            float(ext["minx"]), float(ext["miny"]),
            float(ext["maxx"]), float(ext["maxy"]),
        ]
        lon_lo, lon_hi = muni["bbox_lon_range"]
        lat_lo, lat_hi = muni["bbox_lat_range"]
        if not (lon_lo <= bbox[0] <= lon_hi and lat_lo <= bbox[1] <= lat_hi):
            raise RuntimeError(
                f"{muni['name']}: bbox {bbox} outside expected range "
                f"(lon {lon_lo}-{lon_hi}, lat {lat_lo}-{lat_hi}); aborting tx"
            )
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            str(new_jid), json.dumps(bbox),
        )
        print(f"  Inline bbox UPDATEd: {bbox}")

    # Post-move verify
    p_after = await conn.fetchval(
        """SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid""",
        str(new_jid),
    )
    d_after = await conn.fetchval(
        """SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid""",
        str(new_jid),
    )
    m_after = await conn.fetchval(
        """SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id = $1::uuid""",
        str(new_jid),
    )
    print(f"  Post-move in new jurisdiction: parcels={p_after:,} districts={d_after} matrix={m_after}")
    print(f"  new_jid: {new_jid}")


async def main(confirm: bool) -> int:
    if not confirm:
        print("Refusing to fire without --i-know-this-writes-to-prod", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=900,
    )
    try:
        await conn.execute("SET statement_timeout = 0")
        for muni in MUNIS:
            await _process_muni(conn, muni)

        # King roll-up after both moves
        print("\n=== King County, WA roll-up (post-moves) ===")
        kp = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = $1::uuid", KING_JID,
        )
        kd = await conn.fetchval(
            "SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = $1::uuid", KING_JID,
        )
        km = await conn.fetchval(
            "SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id = $1::uuid", KING_JID,
        )
        print(f"  parcels         : {kp:,}")
        print(f"  zoning_districts: {kd}")
        print(f"  matrix rows     : {km}")
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
