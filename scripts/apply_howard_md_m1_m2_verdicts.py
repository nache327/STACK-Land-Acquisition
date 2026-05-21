"""Apply Howard MD M-1 + M-2 verdicts per reviewer Chrome §122.0 read.

Reviewer's definitive finding:
  §122.0.B.60 — M-1 (Manufacturing: Light) "Uses Permitted as a Matter
  of Right" enumerated list, item 60:
    "Self storage facilities."
  Standalone entry. M-1 PERMITS self-storage by-right.

  §123.0.B.1 — M-2 (Manufacturing: Heavy): "All uses permitted as a
  matter of right in the M-1 District." M-2 inherits M-1's by-right
  list wholesale, including §122.0.B.60. M-2 ALSO PERMITS self-storage
  by-right at equivalent confidence.

Why my earlier verification got M-1 wrong (and why the reviewer's
Chrome read settled it definitively): the §122.0.B by-right list runs
items 1-68. Search snippets in the original Chrome pass surfaced
adjacent storage-related items (18 contractor storage, 36 vehicle
towing, 67 moving and storage establishments) but NOT item 60.
Concluded 'absence from snippets = absence from ordinance' which was
the wrong inference for long enumerated lists.

Conditions_json carries `inherits_from: 'M-1'` on M-2 -- captures the
§123.0.B.1 ordinance reference structurally so future M-1 verdict
changes cascade to M-2.
"""
import asyncio, asyncpg, json, sys

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
HOWARD_JID = "dc2d9d42-aa78-45e3-8c85-970e69a30240"


async def main() -> int:
    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        m1_cond = {
            "approval_path": "P",
            "by_right": True,
            "verification_note": (
                "Explicitly listed as item 60 in M-1 §122.0.B by-right uses. "
                "Distinct from item 18 (contractor storage), 36 (motor vehicle towing/storage), "
                "57 (school bus/boat/RV storage), 67 (warehouses/truck terminals/moving and "
                "storage establishments), 68 (wholesale building materials storage). The "
                "ordinance treats self-storage as its own use class."
            ),
        }
        m2_cond = {
            "approval_path": "P",
            "by_right": True,
            "inherits_from": "M-1",
            "verification_note": (
                "§123.0.B.1 explicitly says 'All uses permitted as a matter of right in the "
                "M-1 District.' M-2 inherits M-1's §122.0.B.60. Update will cascade "
                "automatically if M-1 verdict ever changes (encoded in inherits_from)."
            ),
        }
        m1_notes = (
            "Reviewer Chrome §122.0 direct read 2026-05-21. Item 60 in the 68-item M-1 "
            "by-right list reads 'Self storage facilities' as a standalone use. Distinct "
            "from adjacent storage-type uses (items 18, 36, 57, 67, 68 -- different use classes). "
            "M-1 is now the headline by-right self-storage zone in Howard MD alongside POR. "
            "Promoted from 'unclear' to 'permitted' at 0.95."
        )
        m2_notes = (
            "Reviewer Chrome §123.0 direct read 2026-05-21. §123.0.B.1 inherits all M-1 "
            "by-right uses wholesale, including §122.0.B.60 self-storage. M-2 PERMITS "
            "self-storage by-right. inherits_from='M-1' encoded so any future M-1 verdict "
            "change cascades to M-2 automatically."
        )

        r1 = await conn.execute(
            """
            UPDATE zone_use_matrix
               SET self_storage          = 'permitted'::use_permission_enum,
                   confidence            = 0.95,
                   human_reviewed        = TRUE,
                   classification_source = 'human'::classification_source_enum,
                   cited_subsection      = '§122.0.B.60 (Howard County Code, M-1 by-right uses, item 60: Self storage facilities)',
                   conditions_json       = $2::jsonb,
                   notes                 = $3,
                   updated_at            = now()
             WHERE jurisdiction_id = $1::uuid
               AND zone_code       = 'M-1'
               AND municipality IS NULL
               AND deleted_at IS NULL
            """,
            HOWARD_JID, json.dumps(m1_cond), m1_notes,
        )
        print(f"  M-1 update: {r1}")

        r2 = await conn.execute(
            """
            UPDATE zone_use_matrix
               SET self_storage          = 'permitted'::use_permission_enum,
                   confidence            = 0.95,
                   human_reviewed        = TRUE,
                   classification_source = 'human'::classification_source_enum,
                   cited_subsection      = '§123.0.B.1 (M-2 inherits all M-1 by-right uses) + §122.0.B.60',
                   conditions_json       = $2::jsonb,
                   notes                 = $3,
                   updated_at            = now()
             WHERE jurisdiction_id = $1::uuid
               AND zone_code       = 'M-2'
               AND municipality IS NULL
               AND deleted_at IS NULL
            """,
            HOWARD_JID, json.dumps(m2_cond), m2_notes,
        )
        print(f"  M-2 update: {r2}")

        # Post-state
        print()
        for zc in ("M-1", "M-2"):
            row = await conn.fetchrow(
                """
                SELECT zone_code, self_storage::text AS sp, confidence,
                       conditions_json->>'approval_path' AS ap,
                       conditions_json->>'inherits_from' AS inherits
                  FROM zone_use_matrix
                 WHERE jurisdiction_id=$1::uuid AND zone_code=$2 AND deleted_at IS NULL
                """,
                HOWARD_JID, zc,
            )
            print(f"  {zc} post-state: {dict(row)}")

        # Parcel count for M-1, M-2 (and the hyphen-stripped M1, M2 if they
        # still exist post alias-norm — they shouldn't, but check).
        m1_n = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code='M-1'",
            HOWARD_JID,
        )
        m2_n = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code='M-2'",
            HOWARD_JID,
        )
        print()
        print(f"  Howard MD parcel counts on these zones:")
        print(f"    M-1: {m1_n:,} parcels (now PERMITTED by-right)")
        print(f"    M-2: {m2_n:,} parcels (now PERMITTED by-right via §123.0.B.1 inheritance)")

        # Full Howard MD coverage re-snapshot
        n_total = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL",
            HOWARD_JID,
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
            HOWARD_JID,
        )
        # Permitted-only subset
        n_permit = await conn.fetchval(
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
            HOWARD_JID,
        )
        pct = (100.0 * n_op / n_total) if n_total else 0.0
        print()
        print(f"  HOWARD MD POST-M1/M2 COVERAGE")
        print(f"    operational parcels:        {n_op:,} / {n_total:,}  ({pct:.1f}%)")
        print(f"    permitted-by-right parcels: {n_permit:,}  <-- Tier 1 candidates")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
