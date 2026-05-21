"""Allentown PA 2025-ordinance verdicts + vocabulary_aliases seeding.

Reviewer Chrome pass against eCode360 (codification dated 2026-04-15)
on Table 660-4 (§660-34.A) and §660-37M. Findings:

  Allentown's exact term: 'Self-Service Storage' (capitalized, hyphen,
  'Service' singular). Not 'Self-Storage' (returns 0 hits) or
  'Mini-Warehouse' (0 hits) or 'self-storage miniwarehouse' (0 hits --
  the Lehigh Valley Planning PDF that suggested that term was a
  different jurisdiction or older).

  Table 660-4 row for Self-Service Storage across all 18 zones:
    GX-C, IG  -> SE (special exception, conditional)
    All other 16 zones -> prohibited
  Symbol legend (§660-34.B):
    ●  permitted as-of-right
    ○  special exception (requires §660-115 approval)
    —  prohibited
  Self-Service Storage uses the plain ○ symbol (no corridor restriction).

  §660-37M.1 use-category definition implies these conditions on any
  self-service storage facility regardless of zone:
    enclosed (no outdoor storage units allowed)
    climate-controlled
    small-scale
    individual rental (not commercial/bulk)
    non-commercial vehicles only

CONFLICT WITH EXISTING MATRIX: the existing IG row carries the 2015
verdict 'permitted' (conf 0.85, 119 parcels). The 2025 ordinance
treats IG as SE conditional. Reviewer's explicit recommendation is
to apply the new verdict via DO UPDATE so the matrix reflects the
current ordinance reality. Downside: 119 parcels currently on IG
flip from Tier 1 (permitted by-right) to Tier 2 (conditional). That's
the correct direction (false-negative is safer than false-positive
when the new ordinance is more restrictive).

NEW codes that don't conflict with any current 2015 matrix row get
straight INSERT. The 17 new codes (MX-D/C/S/N, GX-D/C/N, N, NX, N1-N5,
IX, IM, P1, P2) all have no 2015 equivalent in the matrix.

Vocabulary aliases (three-witness moment):
  Howard MD:  'Self-Storage Facilities'   (§131.0)
  Loudoun VA: 'Mini-Warehouse'             (§4.06.06)
  Allentown PA: 'Self-Service Storage'    (§660-37M)
All map to canonical 'self_storage_facility'.
"""
import asyncio, asyncpg, json, sys

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
ALLENTOWN = "8e7992d0-4d2f-42e9-b371-1c59c7767a33"
HOWARD    = "dc2d9d42-aa78-45e3-8c85-970e69a30240"
LOUDOUN   = "8ebaf814-11f9-4e18-89de-d8b947660174"

SE_CONDITIONS = {
    "approval_path": "SE",
    "enclosed_required": True,
    "climate_controlled_required": True,
    "small_scale_required": True,
    "individual_rental_only": True,
    "no_commercial_vehicles": True,
    "use_specific_standard": "§660-37M",
    "approval_authority": "§660-115 (Special Exception process)",
    "verification_note": (
        "All conditions implicit in §660-37M.1 use-category definition. "
        "Apply to any self-service storage facility regardless of zone."
    ),
}

# Conditional zones (SE) under 2025 ordinance
CONDITIONAL_2025 = ["GX-C", "IG"]

# Prohibited zones under 2025 ordinance (everything else in Table 660-4)
PROHIBITED_2025 = [
    "MX-D", "MX-C", "MX-S", "MX-N",
    "GX-D", "GX-N",
    "N", "NX",
    "N1", "N2", "N3", "N4", "N5",
    "IX", "IM",
    "P1", "P2",
]


async def main() -> int:
    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        # 1. Create vocabulary_aliases table + indexes (Alembic 0034 mirror)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary_aliases (
                id                          SERIAL PRIMARY KEY,
                canonical_use_name          TEXT NOT NULL,
                jurisdiction_specific_term  TEXT NOT NULL,
                jurisdiction_id             UUID NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
                source                      TEXT,
                notes                       TEXT,
                created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        # Postgres UNIQUE constraints don't allow expressions; use a UNIQUE INDEX instead.
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_vocab_aliases_canonical_term_jur
              ON vocabulary_aliases (
                canonical_use_name,
                lower(jurisdiction_specific_term),
                COALESCE(jurisdiction_id, '00000000-0000-0000-0000-000000000000'::uuid)
              )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_vocab_aliases_canonical ON vocabulary_aliases (canonical_use_name)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_vocab_aliases_term_lower ON vocabulary_aliases (lower(jurisdiction_specific_term))")
        print("  vocabulary_aliases table ready")

        # 2. Seed vocabulary aliases (three-witness)
        seed = [
            ("self_storage_facility", "Self-Service Storage",   ALLENTOWN, "§660-37M (Allentown 2025 Zoning Ordinance)",
             "Allentown's term -- capitalized, hyphen, 'Service' singular. NOT 'Self-Storage', 'Mini-Warehouse', or 'self-storage miniwarehouse'."),
            ("self_storage_facility", "Mini-Warehouse",          LOUDOUN,   "§4.06.06 (Loudoun LCZO)",
             "Loudoun's term -- capitalized, hyphen-Warehouse. Distinct from 'Industrial Storage' (different use class)."),
            ("self_storage_facility", "Self-Storage Facilities", HOWARD,    "§131.0(D)(4) (Howard MD Zoning)",
             "Howard MD term -- 'Self-Storage' with hyphen, plural 'Facilities'. B-2 conditional rule attaches: indoor only, 5+ ac, public water/sewer required."),
            ("self_storage_facility", "self storage",            None,      "convention",
             "Lowercase generic search term -- accepts variants like 'self-storage', 'selfstorage'."),
            ("self_storage_facility", "mini-warehouse",          None,      "convention",
             "Lowercase generic -- variants of mini-warehouse / mini warehouse."),
        ]
        for canonical, term, jid, src, notes in seed:
            await conn.execute(
                """
                INSERT INTO vocabulary_aliases (canonical_use_name, jurisdiction_specific_term, jurisdiction_id, source, notes)
                VALUES ($1, $2, $3::uuid, $4, $5)
                ON CONFLICT (canonical_use_name, (lower(jurisdiction_specific_term)),
                             (COALESCE(jurisdiction_id, '00000000-0000-0000-0000-000000000000'::uuid))) DO NOTHING
                """,
                canonical, term, jid, src, notes,
            )
        n_vocab = await conn.fetchval("SELECT COUNT(*) FROM vocabulary_aliases")
        print(f"  vocabulary_aliases rows: {n_vocab}")

        # 3. Apply 2025 ordinance verdicts to Allentown matrix.
        # Use SELECT-then-INSERT/UPDATE since uq_zone_matrix is a partial
        # unique index (not a constraint), so ON CONFLICT ON CONSTRAINT
        # can't reference it directly.

        async def upsert_zone(zc: str, verdict: str, conf: float,
                              cited: str, conds, notes: str,
                              clobber_existing: bool):
            existing_id = await conn.fetchval(
                """
                SELECT id FROM zone_use_matrix
                 WHERE jurisdiction_id = $1::uuid
                   AND zone_code       = $2
                   AND municipality IS NULL
                   AND deleted_at IS NULL
                """,
                ALLENTOWN, zc,
            )
            cond_arg = json.dumps(conds) if conds else None
            if existing_id is None:
                await conn.execute(
                    """
                    INSERT INTO zone_use_matrix (
                      jurisdiction_id, zone_code, municipality,
                      self_storage, confidence, human_reviewed, classification_source,
                      cited_subsection, conditions_json, notes, created_at, updated_at
                    ) VALUES (
                      $1::uuid, $2, NULL,
                      $3::use_permission_enum, $4,
                      TRUE, 'human'::classification_source_enum,
                      $5, $6::jsonb, $7, now(), now()
                    )
                    """,
                    ALLENTOWN, zc, verdict, conf, cited, cond_arg, notes,
                )
                return "INSERT"
            elif clobber_existing:
                await conn.execute(
                    """
                    UPDATE zone_use_matrix
                       SET self_storage          = $2::use_permission_enum,
                           confidence            = $3,
                           human_reviewed        = TRUE,
                           classification_source = 'human'::classification_source_enum,
                           cited_subsection      = $4,
                           conditions_json       = $5::jsonb,
                           notes                 = $6,
                           updated_at            = now()
                     WHERE id = $1
                    """,
                    existing_id, verdict, conf, cited, cond_arg, notes,
                )
                return "UPDATE (clobber)"
            else:
                return "SKIP (existing row preserved)"

        # Conditional (SE) zones — clobber existing (per reviewer for IG)
        n_actions = {"INSERT": 0, "UPDATE (clobber)": 0, "SKIP (existing row preserved)": 0}
        for zc in CONDITIONAL_2025:
            cited = "§660-37M (use category) + Table 660-4 (§660-34.A) [Allentown 2025 ordinance, effective 2026-01-01]"
            note = (
                "[2026-05-21 reviewer Chrome 2025 ordinance verification] "
                f"Zone {zc} under Allentown 2025 ordinance permits Self-Service Storage "
                "via Special Exception (§660-115 process). Conditions per §660-37M.1: "
                "enclosed, climate-controlled, small-scale, individual rental, "
                "non-commercial vehicles only."
                + (" NOTE: OVERRIDES prior IG=permitted (2015 ordinance era). ~119 "
                   "parcels currently carrying IG (from May 5 ArcGIS ingest, still on "
                   "2015 codes) flip Tier 1 permitted-by-right -> Tier 2 conditional. "
                   "Correct direction -- 2025 ordinance is more restrictive."
                   if zc == 'IG' else "")
            )
            action = await upsert_zone(zc, "conditional", 0.95, cited, SE_CONDITIONS, note, clobber_existing=True)
            n_actions[action] += 1
            print(f"    {zc:6s} -> {action}")

        # Prohibited zones — DON'T clobber (preserves any pre-existing
        # 2015-era verdict for the same code; new codes get inserted)
        for zc in PROHIBITED_2025:
            cited = "§660-37M + Table 660-4 (§660-34.A): Self-Service Storage row blank (—) for this zone [Allentown 2025 ordinance, effective 2026-01-01]"
            note = (
                f"[2026-05-21 reviewer Chrome 2025 ordinance verification] {zc} prohibits "
                "Self-Service Storage by absence in Table 660-4. Inserted only if no "
                "pre-existing 2015-era verdict exists (preserves prior state)."
            )
            action = await upsert_zone(zc, "prohibited", 0.95, cited, None, note, clobber_existing=False)
            n_actions[action] += 1
        print()
        print(f"  Summary: {n_actions}")

        # Verify
        print()
        n_inserted = await conn.fetchval(
            """
            SELECT COUNT(*) FROM zone_use_matrix
             WHERE jurisdiction_id=$1::uuid
               AND zone_code = ANY($2::text[])
               AND deleted_at IS NULL
            """,
            ALLENTOWN, CONDITIONAL_2025 + PROHIBITED_2025,
        )
        print(f"  2025-code matrix rows present (active): {n_inserted} / {len(CONDITIONAL_2025) + len(PROHIBITED_2025)} expected")

        # Show IG specifically since it's the conflict case
        ig = await conn.fetchrow(
            """
            SELECT zone_code, self_storage::text AS sp, confidence,
                   cited_subsection
              FROM zone_use_matrix
             WHERE jurisdiction_id=$1::uuid AND zone_code='IG' AND deleted_at IS NULL
            """,
            ALLENTOWN,
        )
        print(f"  IG post-state: {dict(ig)}")

        # Parcel impact on IG flip
        n_ig_parcels = await conn.fetchval(
            "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code='IG'",
            ALLENTOWN,
        )
        print(f"  IG parcels affected by verdict flip: {n_ig_parcels}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
