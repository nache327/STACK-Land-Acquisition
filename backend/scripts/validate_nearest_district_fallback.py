"""Op-5 Dispatch J validation harness.

Captures before/after coverage and binding-method distribution for one
jurisdiction, runs `backfill_parcel_zoning_from_districts` with a given
`nearest_within_meters` radius, and re-captures. Intended for Master to
run against the Supabase preview branch (bbvywbpxwsoyvdvygvyw) — point
DATABASE_URL at the preview branch before invoking.

Usage:
    DATABASE_URL=postgresql+asyncpg://...preview... \
      python backend/scripts/validate_nearest_district_fallback.py \
        --jurisdiction-name "Fort Lee" \
        --radius-meters 50

    # Re-run with 200m for comparison:
    DATABASE_URL=... python backend/scripts/validate_nearest_district_fallback.py \
        --jurisdiction-name "Fort Lee" \
        --radius-meters 200

Prints a JSON snapshot at each phase: pre, post-pass1 (contained only),
and post-pass2 (contained + nearest). Safe to re-run because pass 1 is
idempotent (re-binds parcels already contained) and pass 2 only touches
parcels with zone_binding_method IS NULL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.services.spatial_backfill import backfill_parcel_zoning_from_districts


SNAPSHOT_SQL = text(
    """
    SELECT
        j.id::text AS jurisdiction_id,
        j.name,
        COUNT(*)::bigint AS parcel_count,
        COUNT(*) FILTER (
            WHERE p.zoning_code IS NOT NULL AND btrim(p.zoning_code) <> ''
        )::bigint AS with_zoning_code,
        COUNT(*) FILTER (
            WHERE p.zone_binding_method = 'contained'
        )::bigint AS contained,
        COUNT(*) FILTER (
            WHERE p.zone_binding_method LIKE 'nearest_%'
        )::bigint AS nearest,
        COUNT(*) FILTER (
            WHERE p.zone_binding_method IS NULL
        )::bigint AS unbound
    FROM jurisdictions j
    LEFT JOIN parcels p ON p.jurisdiction_id = j.id
    WHERE lower(j.name) = lower(:name)
    GROUP BY j.id, j.name
    """
)


def _pct(num: int, denom: int) -> float:
    return round(num / denom * 100, 1) if denom else 0.0


async def _snapshot(conn, name: str) -> dict:
    result = await conn.execute(SNAPSHOT_SQL, {"name": name})
    row = result.one_or_none()
    if row is None:
        raise SystemExit(f"jurisdiction '{name}' not found")
    parcels = int(row.parcel_count)
    return {
        "jurisdiction_id": row.jurisdiction_id,
        "name": row.name,
        "parcel_count": parcels,
        "with_zoning_code": int(row.with_zoning_code),
        "binding_method": {
            "contained": int(row.contained),
            "nearest": int(row.nearest),
            "unbound": int(row.unbound),
        },
        "coverage_pct": {
            "with_zoning_code": _pct(int(row.with_zoning_code), parcels),
            "contained": _pct(int(row.contained), parcels),
            "nearest": _pct(int(row.nearest), parcels),
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jurisdiction-name", required=True)
    parser.add_argument(
        "--radius-meters",
        type=float,
        default=50.0,
        help="ST_DWithin radius for the nearest-fallback pass",
    )
    args = parser.parse_args()

    settings = Settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.connect() as conn:
        pre = await _snapshot(conn, args.jurisdiction_name)
    print(json.dumps({"phase": "pre", **pre}, indent=2, sort_keys=True))

    jurisdiction_id = pre["jurisdiction_id"]

    # The backfill opens its own raw asyncpg connection; we just need an
    # AsyncSession to satisfy the signature for the pre-count.
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        updated = await backfill_parcel_zoning_from_districts(
            jurisdiction_id, session, nearest_within_meters=args.radius_meters
        )

    async with engine.connect() as conn:
        post = await _snapshot(conn, args.jurisdiction_name)

    print(json.dumps(
        {
            "phase": "post",
            "radius_meters": args.radius_meters,
            "rows_updated": updated,
            "delta": {
                "with_zoning_code": post["with_zoning_code"] - pre["with_zoning_code"],
                "contained": post["binding_method"]["contained"] - pre["binding_method"]["contained"],
                "nearest": post["binding_method"]["nearest"] - pre["binding_method"]["nearest"],
            },
            **post,
        },
        indent=2,
        sort_keys=True,
    ))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
