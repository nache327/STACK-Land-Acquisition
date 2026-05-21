"""Alias normalization sprint -- APPLY step.

Reads alias_mappings where human_reviewed=TRUE and applies Strategy A
(rewrite parcels.zoning_code -> canonical) for each. Preserves the
original code in parcels.zoning_code_pre_normalization for rollback /
audit. Tombstones the now-redundant alias matrix row.

The reviewer is expected to have flipped human_reviewed=TRUE on the
approved mappings either by SQL UPDATE or via the JSON edit + propose
re-run. This script makes ZERO decisions about which mappings to
apply -- it just runs the approved ones.

Usage:
  py scripts/apply_aliases.py                   # all reviewed mappings, all jurisdictions
  py scripts/apply_aliases.py --jid <uuid>      # scope to one jurisdiction
  py scripts/apply_aliases.py --dry-run         # report what would change, no writes
"""
from __future__ import annotations

import asyncio, argparse, sys
import asyncpg

DB = "postgresql://postgres.bbvywbpxwsoyvdvygvyw:Teczmn3027$@aws-1-us-east-2.pooler.supabase.com:5432/postgres"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jid", help="Restrict to a single jurisdiction_id")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change, no writes")
    args = ap.parse_args()

    conn = await asyncpg.connect(DB, statement_cache_size=0)
    try:
        # Load approved mappings
        where_extra = ""
        bind = []
        if args.jid:
            where_extra = "AND jurisdiction_id = $1::uuid"
            bind = [args.jid]
        rows = await conn.fetch(
            f"""
            SELECT id, jurisdiction_id, alias_code, canonical_code,
                   alias_type, parcel_count, confidence, promoted_at
              FROM alias_mappings
             WHERE human_reviewed = TRUE
               AND promoted_at IS NULL
               {where_extra}
             ORDER BY jurisdiction_id, parcel_count DESC NULLS LAST
            """,
            *bind,
        )
        if not rows:
            print("  no approved+un-promoted alias_mappings rows; nothing to apply")
            return 0
        print(f"  {len(rows)} approved mappings to apply")

        # Pre-flight: for each unique jurisdiction, confirm the
        # canonical exists in zone_use_matrix (so the post-rewrite
        # parcels actually resolve to a verdict).
        by_jid = {}
        for r in rows:
            by_jid.setdefault(str(r["jurisdiction_id"]), []).append(r)

        for jid, mlist in by_jid.items():
            print(f"\n  jurisdiction: {jid}  ({len(mlist)} mappings)")
            canon_codes = list({m["canonical_code"] for m in mlist})
            existing = await conn.fetch(
                """
                SELECT zone_code FROM zone_use_matrix
                 WHERE jurisdiction_id=$1::uuid
                   AND deleted_at IS NULL
                   AND zone_code = ANY($2::text[])
                """,
                jid, canon_codes,
            )
            existing_set = set(r["zone_code"] for r in existing)
            missing = [c for c in canon_codes if c not in existing_set]
            if missing:
                print(f"  PRE-FLIGHT FAIL: canonicals not in matrix: {missing}")
                print(f"  aborting this jurisdiction; fix matrix first")
                continue

            total_rewrite = 0
            for m in mlist:
                # Rewrite parcels
                if args.dry_run:
                    n = await conn.fetchval(
                        "SELECT COUNT(*) FROM parcels "
                        "WHERE jurisdiction_id=$1::uuid AND zoning_code=$2",
                        jid, m["alias_code"],
                    )
                    print(f"    [DRY] {m['alias_code']:14s} -> {m['canonical_code']:14s} "
                          f"would rewrite {n:,} parcels")
                    continue
                result = await conn.execute(
                    """
                    UPDATE parcels
                       SET zoning_code_pre_normalization =
                             COALESCE(zoning_code_pre_normalization, zoning_code),
                           zoning_code = $3,
                           updated_at  = now()
                     WHERE jurisdiction_id = $1::uuid
                       AND zoning_code     = $2
                    """,
                    jid, m["alias_code"], m["canonical_code"],
                )
                try:
                    n = int(result.split()[-1])
                except Exception:
                    n = 0
                total_rewrite += n
                # Stamp + tombstone
                await conn.execute(
                    "UPDATE alias_mappings SET promoted_at=now() WHERE id=$1",
                    m["id"],
                )
                if n > 0:
                    await conn.execute(
                        """
                        UPDATE zone_use_matrix
                           SET deleted_at = now(),
                               updated_at = now(),
                               notes      = COALESCE(notes,'')
                                          || E'\\n[tombstoned 2026-05-21: alias '
                                          || $2 || ' normalized to '
                                          || $3 || ' via alias_mappings]'
                         WHERE jurisdiction_id = $1::uuid
                           AND zone_code       = $2
                           AND municipality IS NULL
                           AND deleted_at IS NULL
                        """,
                        jid, m["alias_code"], m["canonical_code"],
                    )
                print(f"    {m['alias_code']:14s} -> {m['canonical_code']:14s} "
                      f"rewrote {n:,} parcels  (type={m['alias_type']})")
            print(f"  total rewritten: {total_rewrite:,}")

        if args.dry_run:
            print("\n  DRY RUN -- no writes performed")
            return 0

        # Coverage re-snapshot
        print("\n=== POST-APPLY COVERAGE ===")
        for jid in by_jid.keys():
            n_total = await conn.fetchval(
                "SELECT COUNT(*) FROM parcels WHERE jurisdiction_id=$1::uuid AND zoning_code IS NOT NULL",
                jid,
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
                jid,
            )
            pct = (100.0 * n_op / n_total) if n_total else 0.0
            print(f"  {jid}: {n_op:,} / {n_total:,} = {pct:.1f}% operational")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
