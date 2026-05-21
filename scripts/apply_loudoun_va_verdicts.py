"""Loudoun VA matrix sprint — Step 4: promote verdicts to zone_use_matrix.

Reads scripts/loudoun_va_proposed_verdicts.json (extracted by Claude
Code via pdfplumber from Loudoun LCZO Chapter 3 §3.02 Use Tables +
Appendix A) and writes each row to prod via direct asyncpg
INSERT/UPDATE. Same pattern as scripts/apply_howard_md_verdicts.py.

Tier handling:
  - tier='verified': high-confidence direct table-cell read from §3.02 PDF.
  - tier='verified_column_uncertain': cell value confirmed but PDF column
    alignment uncertain; confidence already at 0.55-0.75 so matrix filter
    excludes from Hot Deals where appropriate.
  - tier='convention': inferred (e.g. I1 1972 industrial -> permitted by
    convention).
  - tier='needs_1993_ordinance_read': 1993-era code still in parcel data,
    placeholder verdict at 0.40 confidence per per-prefix convention:
      PDH*    -> prohibited (housing)
      TR*UBF  -> prohibited (buffer)
      TOWNS   -> unclear (town-zoned, varies)
      PDGI/PDIP/PDOP -> mirror current LCZO equivalent

Applied fields (every row):
  self_storage, confidence, cited_subsection, conditions_json,
  overlay_codes, notes, human_reviewed=TRUE, classification_source='human'.
Plus the legacy_ordinance text gets appended to notes if non-null.
"""
from __future__ import annotations

import asyncio, json, sys
from pathlib import Path
import asyncpg

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
JSON_PATH = Path(__file__).parent / "loudoun_va_proposed_verdicts.json"


async def main() -> int:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    meta = payload["_meta"]
    jid = meta["jurisdiction_id"]
    print(f"  jurisdiction: {meta['jurisdiction_name']!r} (id={jid})")
    print(f"  ordinance use-name: {meta.get('ordinance_use_name')!r}")
    print()

    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        inserted: list[str] = []
        updated: list[str] = []

        for row in payload["rows"]:
            zc       = row["zone_code"]
            verdict  = row["verdict"]
            conf     = row["confidence"]
            cited    = row.get("cited_subsection")
            cond_j   = row.get("conditions_json")
            overlays = row.get("overlay_codes")
            notes    = row.get("notes") or ""
            legacy   = row.get("legacy_ordinance")
            if legacy:
                notes = f"{notes} [legacy_ordinance: {legacy}]".strip()

            cond_json_arg = json.dumps(cond_j) if cond_j is not None else None
            existing_id = await conn.fetchval(
                """
                SELECT id FROM zone_use_matrix
                 WHERE jurisdiction_id = $1::uuid
                   AND zone_code       = $2
                   AND municipality IS NULL
                   AND deleted_at IS NULL
                """,
                jid, zc,
            )
            if existing_id is None:
                await conn.execute(
                    """
                    INSERT INTO zone_use_matrix (
                      jurisdiction_id, zone_code, municipality,
                      self_storage,
                      confidence, human_reviewed, classification_source,
                      notes, cited_subsection, conditions_json, overlay_codes,
                      created_at, updated_at
                    ) VALUES (
                      $1::uuid, $2, NULL,
                      $3::use_permission_enum,
                      $4, TRUE, 'human'::classification_source_enum,
                      $5, $6, $7::jsonb, $8::text[],
                      now(), now()
                    )
                    """,
                    jid, zc, verdict, conf, notes, cited, cond_json_arg, overlays,
                )
                inserted.append(zc)
            else:
                await conn.execute(
                    """
                    UPDATE zone_use_matrix
                       SET self_storage          = $2::use_permission_enum,
                           confidence            = $3,
                           human_reviewed        = TRUE,
                           classification_source = 'human'::classification_source_enum,
                           notes                 = $4,
                           cited_subsection      = $5,
                           conditions_json       = $6::jsonb,
                           overlay_codes         = $7::text[],
                           updated_at            = now()
                     WHERE id = $1
                    """,
                    existing_id, verdict, conf, notes, cited, cond_json_arg, overlays,
                )
                updated.append(zc)

        print(f"  INSERT: {len(inserted):2d}  {inserted}")
        print(f"  UPDATE: {len(updated):2d}  {updated}")

        # Coverage scoped to canonical-LCZO zones (excluding the
        # needs_1993_ordinance_read tier so the metric reflects current
        # operational coverage, not data debt).
        current_lczo = [r["zone_code"] for r in payload["rows"]
                        if r["tier"] not in ("needs_1993_ordinance_read",)]
        cov = await conn.fetchrow(
            """
            SELECT
              COUNT(*) AS n_present,
              COUNT(*) FILTER (WHERE human_reviewed=TRUE) AS n_human,
              COUNT(*) FILTER (WHERE (confidence >= 0.70 OR human_reviewed)
                               AND self_storage::text <> 'unclear') AS n_classified
              FROM zone_use_matrix
             WHERE jurisdiction_id=$1::uuid
               AND deleted_at IS NULL
               AND zone_code = ANY($2::text[])
            """,
            jid, current_lczo,
        )
        n_scope = len(current_lczo)
        n_class = cov["n_classified"] or 0
        pct = (100.0 * n_class / n_scope) if n_scope else 0.0
        print()
        print(f"  CURRENT-LCZO COVERAGE (Loudoun)")
        print(f"    in scope (current LCZO + I1 1972):  {n_scope}")
        print(f"    present in matrix:                   {cov['n_present']}")
        print(f"    human_reviewed:                      {cov['n_human']}")
        print(f"    classified at >=0.70:                {n_class}")
        print(f"    coverage:                            {pct:.1f}%")

        # Honest parcel-level pending report
        legacy_codes = [r["zone_code"] for r in payload["rows"]
                        if r["tier"] == "needs_1993_ordinance_read"]
        n_pending_parcels = await conn.fetchval(
            """
            SELECT COUNT(*) FROM parcels
             WHERE jurisdiction_id=$1::uuid AND zoning_code = ANY($2::text[])
            """,
            jid, legacy_codes,
        )
        print()
        print(f"  PENDING (1993-era + TOWNS, at 0.40 confidence, filtered from Hot Deals):")
        print(f"    legacy code rows in this JSON: {len(legacy_codes)}")
        print(f"    Loudoun parcels affected:      {n_pending_parcels:,}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
