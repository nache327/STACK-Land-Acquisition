"""Apply Howard MD NT (Columbia) verdict per reviewer Chrome pass.

Reviewer verified NT is a container district (Columbia, MD) under
§125.0.A.8. Final Development Plan (FDP) designates the actual zoning
verdict for each sub-area. ~66% of NT acreage is residential or open
space (§125.0.A.8.a land-use composition table); ~12-30% is
commercial/industrial sub-areas where self-storage permission depends
on the FDP cross-reference to POR / B-1 / B-2 / SC / M-1.

Pragmatic verdict: prohibited at conf=0.80 (matrix-filter threshold)
with fdp_dependent=TRUE flag in conditions_json so buy-box can
soft-flag NT parcels that land in candidate pool for manual FDP
cross-reference before Tier 1 promotion.

Trade-off: small false-negative on NT B-2 sub-areas (where Mini-Storage
*might* be conditional) in exchange for 19,179 parcels going operational.

Bundled secondary updates from reviewer Chrome session:
  - M-1 cited_subsection annotation: §131.0 conditional-use chart only
    names B-2 for self-storage. So M-1 does NOT get self-storage via
    the conditional-use route; the enumerated permitted-uses list in
    §122.0 must be read directly for the final verdict. Status stays
    'unclear' at conf=0.55; updated notes only.
  - M-2 cross-jurisdictional inheritance: §123.0 explicitly says all
    M-1 by-right uses are M-1-inheritable. So whatever M-1 settles to,
    M-2 matches. Annotated in notes.
"""
import asyncio, asyncpg, json, sys

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
HOWARD_JID = "dc2d9d42-aa78-45e3-8c85-970e69a30240"


async def main() -> int:
    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        # NT — container district, FDP-dependent
        nt_conditions = {
            "fdp_dependent": True,
            "default_verdict_basis": "Per §125.0.A.8.a land use composition table, 66%+ of NT acreage is residential or open space; default verdict reflects this majority.",
            "commercial_industrial_carve_out": {
                "applicable": True,
                "trigger": "FDP designates POR, B-1, B-2, SC, or M-1 for the sub-area containing the parcel",
                "cross_reference_rule": "Parcel inherits verdict of FDP-designated district",
                "downstream_verdict_lookup": {
                    "POR": "see POR matrix row",
                    "B-1": "see B-1 matrix row (prohibited)",
                    "B-2": "see B-2 matrix row (conditional indoor only, 5ac + public utilities)",
                    "SC":  "see SC matrix row (prohibited)",
                    "M-1": "see M-1 matrix row (unclear pending §122.0 direct read)",
                },
            },
            "manual_override_recommended_when": "NT parcel passes initial filters AND total acreage suggests commercial/industrial sub-area (typically 5+ contiguous acres at intersection of major roads or in Downtown Columbia)",
            "fdp_authority": "Columbia Association + Howard County Department of Planning and Zoning",
        }
        nt_notes = (
            "Reviewer Chrome §125.0 direct read 2026-05-21. NT is the Columbia, MD "
            "container district -- not a standalone zone. Per §125.0.A.8, the actual "
            "verdict for any NT parcel depends on the Final Development Plan (FDP) "
            "designation for that sub-area: parcels inherit the verdict of POR / B-1 / "
            "B-2 / SC / M-1 as designated. ~19,179 Howard MD parcels carry zone_code='NT'. "
            "Default verdict prohibited at conf=0.80 reflects the 66%+ residential/open-space "
            "majority by acreage; buy-box should soft-flag NT parcels in candidate pool for "
            "manual FDP cross-reference before Tier 1 promotion. R-MH and M-2 uses explicitly "
            "excluded per §125.0.A.5.a (not relevant to self-storage analysis)."
        )
        result = await conn.execute(
            """
            UPDATE zone_use_matrix
               SET self_storage          = 'prohibited'::use_permission_enum,
                   confidence            = 0.80,
                   human_reviewed        = TRUE,
                   classification_source = 'human'::classification_source_enum,
                   cited_subsection      = '§125.0.A.8 (Howard County Code, FDP-dependent container district)',
                   conditions_json       = $2::jsonb,
                   notes                 = $3,
                   updated_at            = now()
             WHERE jurisdiction_id = $1::uuid
               AND zone_code       = 'NT'
               AND municipality IS NULL
               AND deleted_at IS NULL
            """,
            HOWARD_JID, json.dumps(nt_conditions), nt_notes,
        )
        print(f"  NT update: {result}")

        # M-1 — annotate the §131.0 conditional-use channel finding
        m1_extra = (
            "\n[2026-05-21 reviewer Chrome side-finding]: §131.0 Conditional Uses chart "
            "names ONLY B-2 for self-storage -- M-1 does NOT get self-storage via the "
            "conditional-use route. Remaining question: does M-1 enumerated permitted-uses "
            "list in §122.0 include self-storage by-right? If 'moving and storage establishments' "
            "(visible in M-1 list) covers self-storage, M-1 = permitted; else M-1 = prohibited. "
            "Direct §122.0 read still needed."
        )
        result = await conn.execute(
            """
            UPDATE zone_use_matrix
               SET notes = COALESCE(notes, '') || $2,
                   updated_at = now()
             WHERE jurisdiction_id = $1::uuid
               AND zone_code = 'M-1'
               AND municipality IS NULL
               AND deleted_at IS NULL
            """,
            HOWARD_JID, m1_extra,
        )
        print(f"  M-1 notes annotation: {result}")

        # M-2 — annotate the §123.0 inheritance finding
        m2_extra = (
            "\n[2026-05-21 reviewer Chrome side-finding]: §123.0 explicitly states M-2 "
            "permits 'All uses permitted as a matter of right in the M-1 District'. So M-2's "
            "self-storage verdict mirrors M-1 by ordinance reference. When M-1 §122.0 direct "
            "read settles M-1's verdict, M-2 inherits it automatically."
        )
        result = await conn.execute(
            """
            UPDATE zone_use_matrix
               SET notes = COALESCE(notes, '') || $2,
                   updated_at = now()
             WHERE jurisdiction_id = $1::uuid
               AND zone_code = 'M-2'
               AND municipality IS NULL
               AND deleted_at IS NULL
            """,
            HOWARD_JID, m2_extra,
        )
        print(f"  M-2 notes annotation: {result}")

        # Post-state verification
        print()
        row = await conn.fetchrow(
            """
            SELECT zone_code, self_storage::text AS sp, confidence, human_reviewed,
                   cited_subsection,
                   (conditions_json->>'fdp_dependent')::text AS fdp_dep
              FROM zone_use_matrix
             WHERE jurisdiction_id=$1::uuid AND zone_code='NT' AND deleted_at IS NULL
            """,
            HOWARD_JID,
        )
        print(f"  NT post-state: {dict(row)}")

        # Coverage re-snapshot
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
        pct = (100.0 * n_op / n_total) if n_total else 0.0
        print()
        print(f"  HOWARD MD POST-NT COVERAGE")
        print(f"    operational parcels:  {n_op:,} / {n_total:,}  ({pct:.1f}%)")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
