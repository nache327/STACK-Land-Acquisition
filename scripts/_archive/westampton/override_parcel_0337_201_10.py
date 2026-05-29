"""ARCHIVED 2026-05-29 — see scripts/_archive/westampton/README.md.

One-shot manual override: parcel 0337_201_10 (Rancocas Bypass,
Westampton, NJ) — unblock deal evaluation by setting zoning_code='B-1'
and city='Westampton township' so the Burlington-jurisdiction matrix
row (municipality='Westampton township', zone_code='B-1',
self_storage='permitted') resolves.

Why a manual override: Westampton publishes zoning as a PDF only — no
ArcGIS feature service. The proper fix (PDF -> block->zone CSV ->
parcels_zoning_proposed staging table) is the next sprint. This SQL
just unblocks the in-flight B-1 deal so the team can evaluate it now.

Note on data: parcels.land_use_code='2' (NJ MOD-IV Residential) for
this parcel, which conflicts with the human-verified B-1 zoning. The
MOD-IV class is what the NJOGIS composite reported; the actual zoning
ordinance places this parcel in B-1. zoning_code wins (matrix lookup
prefers explicit zoning_code over the MOD-IV fallback).

Idempotent: WHERE clause is parcel-specific. Re-run is a no-op once
the row has the target values.

Of the two columns this script wrote, parcels.city is now also
produced systemically by the _backfill-nj-parcel-city admin job
(TIGER MCD spatial join → 'Westampton township' for the same row).
parcels.zoning_code = 'B-1' is NOT reproducible by any current
automation — Westampton's zoning is PDF-only — which is why this file
is preserved as a replay artifact rather than deleted. If the DB is
ever rebuilt from scratch, delete the `raise SystemExit` below and
re-run.
"""
raise SystemExit(
    "Archived — see scripts/_archive/westampton/README.md. "
    "Remove this guard only if you've read the README and confirmed "
    "a replay is what you actually want."
)

import asyncio, asyncpg, sys  # noqa: E402,F401

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
APN = "0337_201_10"
BURL = "d316fb43-d0e6-4359-aa47-6475fa99cc0f"
TARGET_ZONE = "B-1"
TARGET_CITY = "Westampton township"  # matches TIGER MCD NAME

async def main() -> int:
    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        # Pre-state
        pre = await conn.fetchrow(
            "SELECT zoning_code, city, land_use_code, address FROM parcels "
            "WHERE apn=$1 AND jurisdiction_id=$2::uuid",
            APN, BURL,
        )
        if pre is None:
            print(f"  parcel {APN} not found in Burlington jurisdiction")
            return 1
        print(f"  pre:  zoning_code={pre['zoning_code']!r}  city={pre['city']!r}  "
              f"land_use_code={pre['land_use_code']!r}")

        # The UPDATE
        result = await conn.execute(
            """
            UPDATE parcels
               SET zoning_code = $3,
                   city        = $4,
                   updated_at  = now()
             WHERE apn             = $1
               AND jurisdiction_id = $2::uuid
            """,
            APN, BURL, TARGET_ZONE, TARGET_CITY,
        )
        print(f"  {result}")

        # Post-state
        post = await conn.fetchrow(
            "SELECT zoning_code, city FROM parcels "
            "WHERE apn=$1 AND jurisdiction_id=$2::uuid",
            APN, BURL,
        )
        print(f"  post: zoning_code={post['zoning_code']!r}  city={post['city']!r}")

        # Verify the matrix lookup will resolve
        match = await conn.fetchrow(
            """
            SELECT zone_code, municipality, self_storage::text AS self_storage
              FROM zone_use_matrix
             WHERE jurisdiction_id = $1::uuid
               AND zone_code       = $2
               AND municipality    = $3
               AND deleted_at IS NULL
            """,
            BURL, TARGET_ZONE, TARGET_CITY,
        )
        print()
        if match:
            print(f"  matrix row resolves: zone_code={match['zone_code']}  "
                  f"municipality={match['municipality']!r}  "
                  f"self_storage={match['self_storage']!r}")
            print("  >> deal evaluation unblocked")
        else:
            print(f"  WARNING: no matrix row found for "
                  f"(jur={BURL}, zone={TARGET_ZONE}, muni={TARGET_CITY!r}). "
                  "Apply scripts/apply_westampton_zoning_v2.py first.")
            return 2
        return 0
    finally:
        await conn.close()

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
