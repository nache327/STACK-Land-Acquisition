# St. George UT — Duplicate Jurisdiction Cleanup Proposal

**Date:** 2026-06-11
**Status:** Diagnosis only. **Awaiting Master authorization before any DB write.**
**Origin:** Surfaced during the 2026-06-09 ingestion-blocked bucket enumeration (`/tmp/ingestion_blocked_bucket_2026_06_11.md`).

---

## TL;DR

Prod `/api/admin/coverage` returns **two** jurisdiction rows for St. George, UT — only the name punctuation and parcel count differ. The `035356fd` record is an orphaned empty shell; the `86792c7c` record is the canonical operational one carrying all matrix + parcel work.

**Recommend DELETE `035356fd` after a pre-flight audit-history check (Master's caveat).** Do NOT execute without authorization — orphan jurisdictions can have non-obvious audit / refresh / sourcing attachments that need verification before destructive cleanup.

---

## Side-by-side comparison

| field | **CANONICAL (keep)** | **DUPLICATE (orphan)** |
|---|---|---|
| jurisdiction_id | `86792c7c-76dd-45f8-a382-409097147a8f` | `035356fd-8fba-4df2-ab8e-57d708dedfe6` |
| jurisdiction_name | `St. George, UT` (with period) | `St George, UT` (no period) |
| state | UT | UT |
| county | `Washington County` | `Washington` |
| coverage_level | partial | parcels_only |
| captured_at | 2026-05-19T21:28:02 | 2026-05-12T20:51:13 |
| parcel_count | **49,584** | **49,676** (Δ +92) |
| parcel_with_zoning_code_count | 49,548 | **0** |
| parcel_zoning_code_coverage_pct | 99.9% | **0.0%** |
| zoning_district_count | 0 | 0 |
| matrix_zone_count | 44 | **0** |
| operational_readiness | **operational** | partial |
| blocking_gaps | `[]` | `['no_parcel_zoning_codes', 'no_zone_use_matrix', 'no_zoning_polygons']` |
| self_storage_classified_parcel_pct | 100.0% | 0.0% |
| municipality_breakdown | `{"St. George": {parcels: 49584, zoning_overlays: 49548, parcels_with_zoning: 49548}}` | None |

---

## Likely origin

The `035356fd` record was created first (early ingest used the abbreviated name "St George" and county "Washington"). The canonical `86792c7c` record was later created with the punctuated name "St. George" and the full county name "Washington County"; parcel ingest + zoning matrix work all happened on the canonical record. The `035356fd` was orphaned but never cleaned up.

Parcel count differs by 92 (49,676 vs 49,584). Probable causes:
- The two records have slightly different parcel boundaries from independent imports
- OR the older record was loaded from a snapshot 92 parcels different from the current import

Either way, the `86792c7c` record holds the WORK (matrix, zoning_codes populated, classifications) while `035356fd` is empty.

---

## Pre-flight audit-history check (Master's caveat)

Before any DELETE, verify the orphan has no non-obvious attachments. Master's concern (verbatim): "duplicate jurisdiction rows have audit/historical attachments that need a quick check before destructive cleanup."

Recommend these inspections run by Lane A / DBA in a read-only session:

```sql
-- 1. Parcels with FK to the orphan?
SELECT COUNT(*) FROM parcels WHERE jurisdiction_id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';

-- 2. zone_use_matrix rows with FK to the orphan?
SELECT COUNT(*) FROM zone_use_matrix WHERE jurisdiction_id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';

-- 3. zoning_districts with FK to the orphan?
SELECT COUNT(*) FROM zoning_districts WHERE jurisdiction_id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';

-- 4. Any audit history rows / snapshot history attached?
SELECT COUNT(*) FROM jurisdiction_audit_history WHERE jurisdiction_id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';

-- 5. Any source documents / ingest job records pointing at it?
SELECT COUNT(*) FROM ingest_jobs WHERE jurisdiction_id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';
SELECT COUNT(*) FROM source_documents WHERE jurisdiction_id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';
```

(Table names are approximate — Lane A should adapt to actual schema. Audit-history and ingest-job tables especially worth checking; the orphan's older captured_at and presence in `coverage.failures` suggests at least some refresh-side history exists.)

Outcome decision tree:

| pre-flight result | recommended path |
|---|---|
| All 0 rows | Straight DELETE (Option A below) — no migration needed |
| Parcels FK to orphan but NOT to canonical | Migrate parcels first, then delete (Option B) |
| Parcels FK to BOTH (overlap) | Investigate parcel-row duplication; dedup before migrate/delete |
| Audit history / ingest jobs present | Decide on archival approach (rename + retire vs cascade-delete) |

---

## Cleanup options

### Option A — DELETE the duplicate (recommended if pre-flight is clean)

```sql
-- Only after pre-flight confirms no FK references:
DELETE FROM jurisdictions WHERE id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';
```

**Risk:** if any non-NULL FK reference exists, the delete will fail (or cascade incorrectly). Pre-flight is mandatory.

### Option B — MERGE: migrate parcels first, then delete

```sql
-- Migrate parcels from orphan to canonical
UPDATE parcels SET jurisdiction_id = '86792c7c-76dd-45f8-a382-409097147a8f'
WHERE jurisdiction_id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';

-- Then delete the empty record
DELETE FROM jurisdictions WHERE id = '035356fd-8fba-4df2-ab8e-57d708dedfe6';
```

**Risk:** doubled parcel count on canonical record (49,584 + 49,676 = 99,260) — would need a follow-up dedup of parcels by parcel_id, GIS centroid, or address.

### Option C — DO NOTHING

Leave both. The duplicate doesn't affect operational state of the canonical record. It just inflates the prod coverage list count by 1 and adds noise to the ingestion-blocked bucket enumeration.

**Cost:** +1 entry in coverage tracker, slight confusion in audit/diagnostics tooling. Acceptable but untidy.

---

## Recommendation

**Option A (pre-flight then DELETE)** is the cleanest path IF pre-flight inspections come back empty. The orphan's audit profile (captured_at older than the canonical, no parcels-with-zoning, no matrix, no district data) suggests it never had real work attached.

Steps for Lane A / DBA dispatch (when Master authorizes):
1. Run the 5 pre-flight inspection queries above on a read-only session.
2. If all return 0 / NULL: execute `DELETE FROM jurisdictions WHERE id = '035356fd...'`.
3. If any return non-zero: surface findings, do NOT delete, escalate for Master decision on migration path.
4. Verify `/api/admin/coverage` returns 1 St. George row (not 2) post-delete.

Estimated effort: **15-30 min** if pre-flight is clean; **1-2 hours** if parcel migration is needed.

---

## Hard-rule compliance

- ✅ Read-only diagnostic; no prod DB writes performed.
- ✅ Cleanup options documented, not executed.
- ✅ Pre-flight audit-history check added per Master's caveat.
- ✅ Master authorization required before any destructive action.

---

## STOP for Master decision

Awaiting:
1. Authorize the 5 pre-flight inspection queries via Lane A / DBA dispatch?
2. Pre-confirm: if pre-flight is clean, autopilot the Option A DELETE, OR require a second authorization?
3. If pre-flight shows non-trivial attachments: which migration path (Option B variants)?
