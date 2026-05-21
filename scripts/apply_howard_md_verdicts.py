"""Howard MD matrix sprint — Step 4: promote verified verdicts to
zone_use_matrix.

Reads scripts/howard_md_proposed_verdicts.json (which has been spot-
checked against Municode by the reviewer) and writes each row to
prod via direct asyncpg INSERT/UPDATE (the existing zone_use_matrix
PATCH API doesn't accept the new structured columns yet — those
came in via Alembic 0030 this session and the Pydantic schema hasn't
been updated).

Per-row behavior:
  - tier='overlay_defer' (SW): SKIP. SW is an overlay, modeled in
    overlay_codes TEXT[] on affected parcels, not as a base row.
  - tier='tombstone_candidate' (CCT): tombstone iff zero Howard MD
    parcels carry that zone_code; otherwise apply the verdict.
  - everything else: UPSERT. If a row exists for (jurisdiction_id,
    zone_code, municipality IS NULL, deleted_at IS NULL) -> UPDATE.
    Else -> INSERT.

All applied rows get:
  - self_storage           = <verdict>
  - confidence             = <confidence>
  - cited_subsection       = <cited_subsection>     (new column, 0030)
  - conditions_json        = <conditions_json>      (new column, 0030)
  - overlay_codes          = <overlay_codes>        (new column, 0030)
  - notes                  = <notes>
  - human_reviewed         = TRUE
  - classification_source  = 'human'
  - updated_at             = now()

Idempotent. Tombstone protection via the partial unique index on
(jurisdiction_id, zone_code, COALESCE(municipality, '')) WHERE
deleted_at IS NULL (Alembic 0029).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import asyncpg

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
JSON_PATH = Path(__file__).parent / "howard_md_proposed_verdicts.json"


async def main() -> int:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    meta = payload["_meta"]
    jid = meta["jurisdiction_id"]
    print(f"  jurisdiction: {meta['jurisdiction_name']!r} (id={jid})")
    print(f"  verified_by:  {meta.get('verified_by', '(none)')}")
    print()

    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        skipped: list[str] = []
        tombstoned: list[str] = []
        inserted: list[str] = []
        updated: list[str] = []

        for row in payload["rows"]:
            zc       = row["zone_code"]
            verdict  = row["verdict"]
            conf     = row["confidence"]
            tier     = row["tier"]
            cited    = row.get("cited_subsection")
            cond_j   = row.get("conditions_json")
            overlays = row.get("overlay_codes")
            notes    = row.get("notes")

            # SW = overlay only, do not write as a base row.
            if tier == "overlay_defer":
                skipped.append(f"{zc} (overlay_defer)")
                continue

            # CCT — tombstone iff no parcels carry the code.
            if tier == "tombstone_candidate":
                n_parcels = await conn.fetchval(
                    "SELECT COUNT(*) FROM parcels "
                    "WHERE jurisdiction_id=$1::uuid AND zoning_code=$2",
                    jid, zc,
                )
                if (n_parcels or 0) == 0:
                    # Tombstone any existing row.
                    n_tomb = await conn.execute(
                        """
                        UPDATE zone_use_matrix
                           SET deleted_at = now(),
                               updated_at = now(),
                               notes      = COALESCE(notes,'')
                                           || E'\\n[tombstoned 2026-05-21: zone not in current Municode TOC; zero Howard MD parcels carry this code]'
                         WHERE jurisdiction_id = $1::uuid
                           AND zone_code       = $2
                           AND municipality IS NULL
                           AND deleted_at IS NULL
                        """,
                        jid, zc,
                    )
                    tombstoned.append(f"{zc} (n_parcels=0, {n_tomb})")
                    continue
                # else: parcels exist, apply the verdict like normal.
                print(f"  {zc}: {n_parcels} parcels carry this code; applying verdict instead of tombstoning")

            # Upsert path.
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
                    jid, zc,
                    verdict,
                    conf, notes, cited, cond_json_arg, overlays,
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

        # Summary
        print()
        print(f"  INSERT: {len(inserted):2d}  {inserted}")
        print(f"  UPDATE: {len(updated):2d}  {updated}")
        print(f"  TOMB.:  {len(tombstoned):2d}  {tombstoned}")
        print(f"  SKIP:   {len(skipped):2d}  {skipped}")

        # Coverage re-snapshot
        cov = await conn.fetchrow(
            """
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE human_reviewed = TRUE)        AS human,
              COUNT(*) FILTER (WHERE confidence >= 0.70)           AS conf_70_plus,
              COUNT(*) FILTER (WHERE (confidence >= 0.70 OR human_reviewed = TRUE)
                               AND self_storage::text <> 'unclear') AS classified_at_threshold
              FROM zone_use_matrix
             WHERE jurisdiction_id = $1::uuid AND deleted_at IS NULL
            """,
            jid,
        )
        total = cov["total"]
        classified = cov["classified_at_threshold"]
        pct = (100.0 * classified / total) if total else 0.0
        print()
        print(f"  POST-SPRINT COVERAGE (Howard MD)")
        print(f"    matrix rows (active):    {total}")
        print(f"    human-reviewed:          {cov['human']}")
        print(f"    confidence >= 0.70:      {cov['conf_70_plus']}")
        print(f"    classified at threshold: {classified}  ({pct:.1f}%)")
        print(f"    target:                  >= 95%")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
