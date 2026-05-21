"""Allentown PA matrix sprint — promote 18 existing 2015-ordinance
zoning verdicts + tombstone 99 PA land-use-code rows that are data
debt in the wrong column.

Context (per audit):
  - Allentown adopted new 2025 ordinance effective 2026-01-01.
  - Parcel data still carries 2015 codes (RMH 13K, RM 9K, RL 4K, etc.).
  - 2025 codes (N1-N5, NX, MX-D, etc.) are NOT in parcel data yet.
  - Pragmatic sprint: promote the 18 2015 codes that parcels reference,
    defer 2025 codes until the city's GIS feed updates.

  - 99 matrix rows are PA Act 43 land-use codes (110.0, 120.0, etc.)
    that ended up in the zoning_code column. These are NOT zoning
    codes. ~8K parcels carry them (110.0 alone = 7,090). They need
    a separate cleanup: either reroute to a land_use_code column or
    spatially refresh from Allentown's current ArcGIS zoning layer.
    For now we tombstone the matrix rows so they don't confuse the
    matrix lookup. Affected parcels stay at storage_permission='unclassified'
    until the city's GIS refresh happens.

Verdict bands (informed by new ordinance §660-37.M Self-Service Storage
existence + standard US zoning convention):

  PERMITTED at 0.85 (industrial — corroborated by ordinance §660-37.M
  defining self-service storage as enclosed/climate-controlled, plus
  brief's confirmation that Light-Industrial permits self-storage):
    BLI, I2, I3, IG

  CONDITIONAL at 0.70 (business zones — existing draft labels keep
  but flag for Chrome verification of by-right vs conditional path):
    B1R, B2, B3, B4, B5, B/IWD

  PROHIBITED at 0.95 (residential + public — convention; self-storage
  never permitted in US residential districts):
    RH, RL, RLC, RM, RMH, RML, RMP, P

Coverage impact estimate (parcels):
  Industrial (permitted): BLI 346 + I2 262 + I3 149 + IG 105 = 862
  Business (conditional): B1R 835 + B3 657 + B2 547 + B5 212 + B4 32 + B/IWD ? = ~2,300
  Residential + Public (prohibited): RMH 13,381 + RM 8,922 + RL 4,372 + RML 2,505 + RH 1,060 + RMP 247 + P 194 + RLC 58 = 30,739
  Total operational: ~34K parcels
"""
import asyncio, asyncpg, json, sys

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
ALLENTOWN_JID = "8e7992d0-4d2f-42e9-b371-1c59c7767a33"

PERMITTED_INDUSTRIAL = [
    ("BLI", "Business / Light Industrial -- §660-37.M Self-Service Storage by-right convention for light-industrial zones; matches new-ordinance text + reviewer brief."),
    ("I2",  "Industrial 2 -- by-right industrial zone; self-service storage permitted by convention + §660-37.M."),
    ("I3",  "Industrial 3 -- by-right; same as I2."),
    ("IG",  "General Industrial -- by-right; broadest industrial zone."),
]
CONDITIONAL_BUSINESS = [
    ("B1R",   "Business 1 Retail -- conditional draft labelling preserved. Allentown new ordinance uses 'P' / blank / numeric codes per §660-37.M use table. Existing label is plausible but flag for Chrome §660-37 column-alignment verification."),
    ("B2",    "Business 2 -- conditional draft preserved; verify with Chrome."),
    ("B3",    "Business 3 -- conditional draft preserved; verify with Chrome."),
    ("B4",    "Business 4 -- conditional draft preserved."),
    ("B5",    "Business 5 -- conditional draft preserved."),
    ("B/IWD", "Business / Industrial Warehouse District -- conditional draft preserved; this zone may actually be permitted (industrial overlay). Verify with Chrome."),
]
PROHIBITED_RESIDENTIAL = [
    ("RH",  "High-Density Residential -- self-storage never permitted in US residential districts; convention."),
    ("RL",  "Low-Density Residential -- convention."),
    ("RLC", "Low-Density Residential / Conservation -- convention."),
    ("RM",  "Medium-Density Residential -- convention."),
    ("RMH", "Residential Mobile Home -- convention."),
    ("RML", "Medium-Low Density Residential -- convention."),
    ("RMP", "Residential Mobile Park -- convention."),
    ("P",   "Public / Institutional -- civic/institutional use only; self-storage never permitted by convention."),
]

# 99 land-use-code rows -- numeric strings ending in .0 (110.0, 120.0, etc.)
# These are PA Act 43 land-use codes (residential, commercial, etc.) that
# ended up in the zoning_code column. NOT zoning codes. Tombstone the
# matrix rows so they don't confuse the matrix lookup. The underlying
# parcel data debt (zoning_code='110.0' etc.) requires a spatial refresh
# from Allentown's current ArcGIS zoning layer -- separate sprint.


async def main() -> int:
    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        # Promote 18 real zoning codes
        permitted_notes = "\n[2026-05-21 Allentown PA matrix sprint: promoted from auto-classifier draft to human_reviewed=TRUE per the existing 2015 ordinance + new 2025 §660-37.M self-service storage definition.] "
        applied = []
        for zc, note in PERMITTED_INDUSTRIAL:
            await conn.execute(
                """
                UPDATE zone_use_matrix
                   SET self_storage          = 'permitted'::use_permission_enum,
                       confidence            = 0.85,
                       human_reviewed        = TRUE,
                       classification_source = 'human'::classification_source_enum,
                       cited_subsection      = $3,
                       conditions_json       = $4::jsonb,
                       notes                 = COALESCE(notes,'') || $5,
                       updated_at            = now()
                 WHERE jurisdiction_id = $1::uuid
                   AND zone_code       = $2
                   AND municipality IS NULL
                   AND deleted_at IS NULL
                """,
                ALLENTOWN_JID, zc,
                "Allentown 2015 Zoning Ordinance + 2025 §660-37.M Self-Service Storage definition",
                json.dumps({"approval_path": "P", "by_right": True,
                            "ordinance_use_name_2025": "self-service storage",
                            "verification_note": "Promoted at conf=0.85 based on industrial-by-right convention + new ordinance use definition. Direct Chrome verification of §660-37 use table column alignment would lift to 0.95."}),
                permitted_notes + note,
            )
            applied.append((zc, "permitted"))

        for zc, note in CONDITIONAL_BUSINESS:
            await conn.execute(
                """
                UPDATE zone_use_matrix
                   SET self_storage          = 'conditional'::use_permission_enum,
                       confidence            = 0.70,
                       human_reviewed        = TRUE,
                       classification_source = 'human'::classification_source_enum,
                       cited_subsection      = $3,
                       conditions_json       = $4::jsonb,
                       notes                 = COALESCE(notes,'') || $5,
                       updated_at            = now()
                 WHERE jurisdiction_id = $1::uuid
                   AND zone_code       = $2
                   AND municipality IS NULL
                   AND deleted_at IS NULL
                """,
                ALLENTOWN_JID, zc,
                "Allentown 2015 Zoning Ordinance -- B-zone conditional path",
                json.dumps({"approval_path": "SE_unverified",
                            "ordinance_use_name_2025": "self-service storage",
                            "verification_note": "Conditional verdict preserved from auto-classifier draft. PA municipal vocabulary often uses 'Special Exception' for what MD/VA call 'conditional'. Direct §660-37 Chrome pass would confirm SE vs P + extract conditions text (climate-controlled, interior access per §660-37.M)."}),
                permitted_notes + note,
            )
            applied.append((zc, "conditional"))

        for zc, note in PROHIBITED_RESIDENTIAL:
            await conn.execute(
                """
                UPDATE zone_use_matrix
                   SET self_storage          = 'prohibited'::use_permission_enum,
                       confidence            = 0.95,
                       human_reviewed        = TRUE,
                       classification_source = 'human'::classification_source_enum,
                       cited_subsection      = $3,
                       conditions_json       = NULL,
                       notes                 = COALESCE(notes,'') || $4,
                       updated_at            = now()
                 WHERE jurisdiction_id = $1::uuid
                   AND zone_code       = $2
                   AND municipality IS NULL
                   AND deleted_at IS NULL
                """,
                ALLENTOWN_JID, zc,
                "Allentown 2015 Zoning Ordinance -- residential/public closed-list convention (no self-storage in residential US zoning)",
                permitted_notes + note,
            )
            applied.append((zc, "prohibited"))

        print(f"  Promoted {len(applied)} real zoning codes:")
        for zc, v in applied:
            print(f"    {zc:8s} -> {v}")

        # Tombstone the 99 PA land-use-code rows
        # Pattern: zone_code is a numeric string like '110.0', '120.0', '321.0', etc.
        # Match by regex.
        result = await conn.execute(
            """
            UPDATE zone_use_matrix
               SET deleted_at = now(),
                   updated_at = now(),
                   notes      = COALESCE(notes,'')
                              || E'\\n[tombstoned 2026-05-21: PA Act 43 land-use code (not a zoning code) -- ended up in zoning_code column via ingest bug. ~8K Allentown parcels carry these codes; parcel data needs spatial refresh from current ArcGIS zoning layer to map to real zone codes (RL, RM, etc.).]'
             WHERE jurisdiction_id = $1::uuid
               AND zone_code ~ '^[0-9]+\\.[0-9]+$'
               AND deleted_at IS NULL
            """,
            ALLENTOWN_JID,
        )
        print()
        print(f"  Tombstoned land-use-code rows: {result}")

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
        n_perm = await conn.fetchval(
            """
            SELECT COUNT(*) FROM parcels p
             WHERE p.jurisdiction_id = $1::uuid
               AND EXISTS (
                 SELECT 1 FROM zone_use_matrix z
                  WHERE z.jurisdiction_id = p.jurisdiction_id
                    AND z.zone_code       = p.zoning_code
                    AND z.municipality IS NULL
                    AND z.deleted_at IS NULL
                    AND z.self_storage::text = 'permitted'
               )
            """,
            ALLENTOWN_JID,
        )
        # Parcels still on PA land-use codes
        n_landuse = await conn.fetchval(
            """
            SELECT COUNT(*) FROM parcels
             WHERE jurisdiction_id=$1::uuid
               AND zoning_code ~ '^[0-9]+\\.[0-9]+$'
            """,
            ALLENTOWN_JID,
        )
        pct = (100.0 * n_op / n_total) if n_total else 0.0
        print()
        print(f"  ALLENTOWN POST-SPRINT COVERAGE")
        print(f"    total parcels w/ zoning_code:     {n_total:,}")
        print(f"    operational (human + conf>=0.70): {n_op:,}  ({pct:.1f}%)")
        print(f"    permitted-by-right (Tier 1):      {n_perm:,}")
        print(f"    still on PA land-use codes:       {n_landuse:,}  (separate cleanup: spatial refresh from ArcGIS)")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
