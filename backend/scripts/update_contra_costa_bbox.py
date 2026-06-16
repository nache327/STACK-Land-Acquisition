"""Free-flip helper — populate jurisdictions.bbox for Contra Costa County, CA.

Background: PR #258 orchestrator's matrix sprint cleared 3 of 4 Contra
Costa blockers (no_zone_use_matrix, no_matrix_matches_for_parcel_zones,
low_matrix_match_pct). Only `missing_bbox` is residual — a missing
`jurisdictions.bbox` metadata value, not a real coverage problem.

Per `app.services.spatial_backfill.refresh_jurisdiction_bbox` (already
in the codebase since pre-Phase-2), the bbox is stored as
`[minLng, minLat, maxLng, maxLat]` in `jurisdictions.bbox` (JSONB). The
audit's `missing_bbox` check (audit_zoning_coverage.py:467-468) fires
when this column is null.

This script computes ST_Extent over Contra Costa's 387,492 parcels and
writes it. Mirrors the existing helper's SQL verbatim. Standalone (no
SQLAlchemy import chain — Python 3.9 compat per prior dispatch pattern).

After this UPDATE, an audit refresh should flip Contra Costa from
`partial` (`blocking_gaps=['missing_bbox']`) → `operational`
(`blocking_gaps=[]`), incrementing the operational count 19 → 20.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import asyncpg
import dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv.load_dotenv(_REPO_ROOT / ".env")
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in environment")

logger = logging.getLogger("contra_costa_bbox")

CONTRA_COSTA_JID = "7ad622d4-0d36-4fe5-ad8b-53352bdac162"


def _session_db_url() -> str:
    return DATABASE_URL.replace(":6543/", ":5432/").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


async def main() -> int:
    conn = await asyncpg.connect(
        _session_db_url(), statement_cache_size=0, command_timeout=600,
    )
    try:
        await conn.execute("SET statement_timeout = 0")

        # Before state
        before = await conn.fetchrow(
            "SELECT name, bbox FROM jurisdictions WHERE id = $1::uuid",
            CONTRA_COSTA_JID,
        )
        print(f"Before: {before['name']!r} bbox={before['bbox']!r}")

        if before["bbox"] is not None:
            print("\nbbox already populated — nothing to do.")
            return 0

        # Compute extent (mirrors refresh_jurisdiction_bbox)
        ext = await conn.fetchrow(
            """
            SELECT
                ST_XMin(ST_Extent(geom)) AS minx,
                ST_YMin(ST_Extent(geom)) AS miny,
                ST_XMax(ST_Extent(geom)) AS maxx,
                ST_YMax(ST_Extent(geom)) AS maxy,
                COUNT(*) AS parcel_count
            FROM parcels
            WHERE jurisdiction_id = $1::uuid AND geom IS NOT NULL
            """,
            CONTRA_COSTA_JID,
        )
        if ext is None or ext["minx"] is None:
            print("HALT: no parcel geometry to compute bbox from", file=sys.stderr)
            return 2
        bbox = [
            float(ext["minx"]), float(ext["miny"]),
            float(ext["maxx"]), float(ext["maxy"]),
        ]
        print(f"Computed bbox from {ext['parcel_count']:,} parcel geoms:")
        print(f"  [minLng, minLat, maxLng, maxLat] = {bbox}")

        # Sanity check the bbox looks like WA-CA-county-scale coordinates
        # (Contra Costa is around lon=-122, lat=37.7-38.1 per the
        # acquisition spec).
        if not (-130 <= bbox[0] <= -110 and 30 <= bbox[1] <= 45):
            print(
                f"HALT: bbox doesn't look like a CA county "
                f"(expected lon ~-122, lat ~37-38): {bbox}",
                file=sys.stderr,
            )
            return 3

        # Write
        await conn.execute(
            "UPDATE jurisdictions SET bbox = $2::jsonb WHERE id = $1::uuid",
            CONTRA_COSTA_JID, json.dumps(bbox),
        )

        # Confirm
        after = await conn.fetchrow(
            "SELECT name, bbox FROM jurisdictions WHERE id = $1::uuid",
            CONTRA_COSTA_JID,
        )
        print(f"\nAfter:  {after['name']!r} bbox={after['bbox']!r}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(asyncio.run(main()))
