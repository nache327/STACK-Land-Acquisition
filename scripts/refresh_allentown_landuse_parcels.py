"""Targeted spatial refresh: replace PA-land-use-code zoning_code values
on Allentown parcels with the real zone via ST_Within against the 250
already-ingested zoning_districts polygons.

Why a custom script vs another _backfill-zoning call:
  - The standard backfill spatial-join uses
      zoning_code = COALESCE(NULLIF(p.zoning_code, ''), ranked.zone_code)
    -- it only fills NULL/empty codes. The PA-land-use-code parcels
    have zoning_code='110.0' (non-empty) so the join skipped them in
    the May 5 backfill run.
  - This script explicitly OVERRIDES the code where it matches the
    PA Act 43 pattern (^[0-9]+\\.[0-9]+$).
  - Preserves original in parcels.zoning_code_pre_normalization
    (added in Alembic 0033) so rollback is trivial.

Rollback SQL (if needed):
  UPDATE parcels
     SET zoning_code = zoning_code_pre_normalization,
         zoning_code_pre_normalization = NULL,
         updated_at = now()
   WHERE jurisdiction_id = '8e7992d0-4d2f-42e9-b371-1c59c7767a33'::uuid
     AND zoning_code_pre_normalization IS NOT NULL
     AND zoning_code_pre_normalization ~ '^[0-9]+\\.[0-9]+$';

Per spatial-backfill memory: raw asyncpg + session-mode port 5432 +
statement_timeout=0 (Supabase pgbouncer transaction-mode 6543 would
kill the join mid-run on >1K rows).
"""
import asyncio, asyncpg, sys

# Session-mode port 5432 (not transaction-mode 6543) for the spatial join
DB_SESSION = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
ALLENTOWN_JID = "8e7992d0-4d2f-42e9-b371-1c59c7767a33"


async def main() -> int:
    conn = await asyncpg.connect(DB_SESSION, statement_cache_size=0, command_timeout=600)
    try:
        await conn.execute("SET statement_timeout = 0")

        # Pre-flight: count how many parcels will get overridden
        n_candidates = await conn.fetchval(
            """
            SELECT COUNT(*) FROM parcels p
              JOIN zoning_districts zd
                ON zd.jurisdiction_id = p.jurisdiction_id
               AND p.geom IS NOT NULL
               AND zd.geom IS NOT NULL
               AND ST_Within(ST_Centroid(p.geom), zd.geom)
             WHERE p.jurisdiction_id = $1::uuid
               AND p.zoning_code ~ '^[0-9]+\.[0-9]+$'
            """,
            ALLENTOWN_JID,
        )
        n_orphan = await conn.fetchval(
            """
            SELECT COUNT(*) FROM parcels p
             WHERE p.jurisdiction_id = $1::uuid
               AND p.zoning_code ~ '^[0-9]+\.[0-9]+$'
               AND NOT EXISTS (
                 SELECT 1 FROM zoning_districts zd
                  WHERE zd.jurisdiction_id = p.jurisdiction_id
                    AND p.geom IS NOT NULL
                    AND zd.geom IS NOT NULL
                    AND ST_Within(ST_Centroid(p.geom), zd.geom)
               )
            """,
            ALLENTOWN_JID,
        )
        print(f"  PRE-FLIGHT")
        print(f"    PA-land-use-code parcels w/ matching district: {n_candidates:,}")
        print(f"    PA-land-use-code parcels w/ NO match (orphan):  {n_orphan:,}")
        print(f"    these orphans stay on land-use codes; usually centroid outside city polygons or NULL geom")

        # The UPDATE: only PA-land-use-code parcels, override with district zone
        # ROW_NUMBER picks one district per parcel (in case of overlap).
        result = await conn.execute(
            """
            WITH ranked AS (
                SELECT p.id AS parcel_id,
                       zd.zone_code,
                       ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY zd.id) AS rn
                  FROM parcels p
                  JOIN zoning_districts zd
                    ON zd.jurisdiction_id = p.jurisdiction_id
                   AND p.geom IS NOT NULL
                   AND zd.geom IS NOT NULL
                   AND ST_Within(ST_Centroid(p.geom), zd.geom)
                 WHERE p.jurisdiction_id = $1::uuid
                   AND p.zoning_code ~ '^[0-9]+\.[0-9]+$'
            )
            UPDATE parcels p
               SET zoning_code_pre_normalization =
                     COALESCE(p.zoning_code_pre_normalization, p.zoning_code),
                   zoning_code = ranked.zone_code,
                   updated_at = now()
              FROM ranked
             WHERE p.id = ranked.parcel_id
               AND ranked.rn = 1
            """,
            ALLENTOWN_JID,
        )
        print()
        print(f"  RESULT: {result}")

        # Post-state
        n_landuse_remaining = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code ~ '^[0-9]+\\.[0-9]+$'",
            ALLENTOWN_JID,
        )
        n_with_pre = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code_pre_normalization IS NOT NULL",
            ALLENTOWN_JID,
        )

        # Coverage re-snapshot
        n_total = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL",
            ALLENTOWN_JID,
        )
        n_op = await conn.fetchval(
            """
            SELECT COUNT(*) FROM parcels p
             WHERE p.jurisdiction_id = $1::uuid
               AND EXISTS (
                 SELECT 1 FROM zone_use_matrix z
                  WHERE z.jurisdiction_id = p.jurisdiction_id
                    AND z.zone_code       = p.zoning_code
                    AND z.municipality IS NULL
                    AND z.deleted_at IS NULL
                    AND z.human_reviewed  = TRUE
                    AND z.confidence     >= 0.70
                    AND z.self_storage::text <> 'unclear'
               )
            """,
            ALLENTOWN_JID,
        )
        pct = (100.0 * n_op / n_total) if n_total else 0.0
        print()
        print(f"  POST-REFRESH STATE")
        print(f"    parcels still on PA land-use codes:      {n_landuse_remaining:,}  (down from 7,986)")
        print(f"    parcels w/ pre_normalization audit:      {n_with_pre:,}")
        print(f"    operational parcels:                     {n_op:,} / {n_total:,}  ({pct:.1f}%)")

        # Distribution of post-refresh zoning_code
        rows = await conn.fetch(
            """
            SELECT zoning_code, COUNT(*) AS n
              FROM parcels
             WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL
             GROUP BY 1 ORDER BY n DESC LIMIT 25
            """,
            ALLENTOWN_JID,
        )
        print()
        print(f"  TOP zoning_code values post-refresh:")
        for r in rows:
            print(f"    {r['zoning_code']:14s} n={r['n']:>7,}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
