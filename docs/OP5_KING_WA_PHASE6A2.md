# Op-5 King WA Phase 6A.2 — Class A zoning backfill (WAZA primary)

**Owner:** Lane A
**Date:** 2026-06-15
**Sprint type:** Phase 6A.2 — Class A spatial backfill via Washington State Zoning Atlas (WAZA) for King County, on parcels staged by PR #259.
**Verdict:** **Bellevue cleared all 4 + bbox gates (85.2% coverage, 3.31% nearest share). Mercer Island clears 3 gates + bbox; coverage 63.2% is sub-gate (WAZA's 48 polygons vs spec's 82 city polygons). PR #248 Diagnostic confirmed: Bellevue WAZA carries legacy R-5/R-10/GC vintage, NOT current LDR-2/MU-H city codes. Inline `jurisdictions.bbox` UPDATEd per PR #261 lesson. Bonus probe: all 4 Puget Sound counties pass strengthened Class A bbox primitive at 89.9-96.3% — one adapter clone unlocks 3 more Tier 2 counties.**
**Predecessors:** PR #259 (Phase 6A.1 parcels) · PR #261 (bbox-inline lesson) · PR #253 (Contra Costa Phase 5A.2 Class A pattern).

---

## Headline

| Muni | Districts | Parcels | Bound | Coverage | Near share | Gates |
|------|----------:|--------:|------:|---------:|-----------:|:-----:|
| **Bellevue** | 991 | 33,217 | **28,315** | **85.2 %** | 3.31 % | **✓ all PASS** |
| **Mercer Island** | 48 | 7,448 | 4,707 | **63.2 %** | 17.87 % | cov ✗ (sub-gate); 3 + bbox ✓ |

**+33,022 newly-bound King parcels** (Bellevue + Mercer Island combined) on the canonical Class A statewide source (WAZA).

## Quality gates

| Gate | Threshold | Bellevue | Mercer Island | Status |
|------|-----------|---------:|--------------:|:------:|
| Coverage ≥ 70 % | 70 % | **85.2 %** | **63.2 %** | Bellevue ✓ / Mercer ✗ (sub-gate by 6.8 pp) |
| `nearest_*` < 30 % | 30 % | **3.31 %** | **17.87 %** | ✓ both |
| `raw_attributes` preserved | 0 empty `{}` | **0 / 991** | **0 / 48** | ✓ both (Norfolk gate cleared) |
| `no_zoning_polygons` cleared | districts > 0 | **991 districts** | **48 districts** | ✓ both |
| **`jurisdictions.bbox` populated (NEW codified, PR #261)** | non-null | **`[-122.5360, 47.0836, -121.0876, 47.7804]`** | (same — county-level) | ✓ inline |

Bellevue clears all 5 gates. Mercer Island clears 4 of 5; coverage is sub-gate. See "Mercer Island sub-gate analysis" below.

## Three codified updates applied

### 1. Class A scale-out preflight (PR #253 lesson)

Phase 6A.2's `preflight` subcommand is **read-only pipeline shape validation only**. NO in-DB ROLLBACK transactional gate run — the PR #253 finding (in-txn rows aren't in GiST → sequential scans hang) makes that approach unviable at Class A scale. Phase 1 acquisition spec verification + this lightweight pipeline check substitute. Preflight ran cleanly; fire proceeded.

### 2. Inline `jurisdictions.bbox` UPDATE (PR #261 lesson)

The fire script's `_fire()` writes `jurisdictions.bbox` as part of the same transaction sequence (Phase 3, after districts + backfill complete). Computed extent `[-122.5360, 47.0836, -121.0876, 47.7804]` from `ST_Extent(parcels.geom)` over all 635,186 King parcels. Sanity-checked the bbox falls in WA Puget Sound lon/lat range before writing.

Going forward, the King WA audit will **not** fire `missing_bbox` (the residual gap that delayed Contra Costa's flip until PR #261).

### 3. Bellevue WAZA-vs-city code mismatch verification (PR #248 Diagnostic)

The fire script's verification phase compares `zoning_districts.zone_code` against known legacy (R-10 / GC) and modern (LDR-2 / MU-H) Bellevue code sets:

```
legacy (R-10 / GC) count : 86
modern (LDR-2 / MU-H) cnt: 0
→ WAZA uses LEGACY codes; current Bellevue city zoning has shifted to LDR-2/MU-H. Documented mismatch.
```

PR #248 Diagnostic CONFIRMED at scale. WAZA's Bellevue snapshot is frozen at the pre-2017-amendment vintage.

#### Bellevue zoning_code reality check (5 random parcels)

```
apn=033-2025059057  zoning='R-3.5'   binding=contained   addr=10210 NE 24TH ST
apn=033-1424059083  zoning='R-5'     binding=contained   addr=4655 161ST AVE SE
apn=033-4139490120  zoning='R-5'     binding=contained   addr=5817 176TH PL SE
apn=033-2785000080  zoning='R-3.5'   binding=contained   addr=120 128TH AVE SE
apn=033-3460300060  zoning='R-2.5'   binding=contained   addr=15126 SE 53RD PL
```

All 5 carry WAZA-vintage residential codes (R-2.5 / R-3.5 / R-5). Current Bellevue city zoning would re-classify most of these as LDR-1/LDR-2/MDR-1.

#### Bellevue top 15 zoning_code distribution

| Code | Count | Vintage |
|------|------:|---------|
| R-5 | 12,889 | WAZA legacy (single-family) |
| R-3.5 | 7,540 | WAZA legacy (single-family) |
| R-2.5 | 1,964 | WAZA legacy |
| R-4 | 1,815 | WAZA legacy |
| R-1.8 | 988 | WAZA legacy |
| R-10 | 467 | WAZA legacy (multi-family) |
| R-1 | 434 | WAZA legacy |
| R-20 | 376 | WAZA legacy (multi-family) |
| R-7.5 | 232 | WAZA legacy |
| O | 193 | (office) |
| R-30 | 164 | WAZA legacy (multi-family) |
| **DT-MU** | 116 | Modern downtown |
| **BR-CR** | 102 | Modern BelRed |
| R-15 | 102 | WAZA legacy |
| CB | 86 | (community business) |

**13 of 15** are WAZA legacy codes; **2 of 15** (DT-MU, BR-CR) are modern downtown / BelRed corridor codes. WAZA has been partially updated for the highest-priority modern overlays but the bulk single-family / multi-family residential coding is still pre-2017.

#### Authoritative-layer decision

**WAZA is what we have, and matrix work should target WAZA codes.** Orchestrator's King matrix sprint will author against the WAZA code namespace (R-5 / R-10 / etc), NOT the current Bellevue city namespace (LDR-2 / MU-H). When/if Bellevue's actual codes update WAZA, a re-fire would re-bind parcels to the new codes — at that point the matrix would need a re-author or alias table.

Documented for matrix sprint planning.

## Mercer Island sub-gate analysis

Mercer Island's WAZA layer has **48 polygons** vs the spec's **82 city polygons** at the source-of-record layer. The 48-feature subset doesn't fully tile the island — 36.8 % of parcels (2,741 of 7,448) sit outside any WAZA polygon, even at 50 m nearest fallback.

**Sub-gate cause**: WAZA's Mercer Island coverage is sparse — not a code-mismatch problem like Bellevue, but a **polygon-density** problem. The directory's fallback (`Mercer_Island_Planning_Layers/FeatureServer/2` with 82 polygons) would likely close the gap.

**Recommendation**: defer Mercer Island re-fire from city layer to a follow-up dispatch. Current state is partial-with-zoning at 63.2 % — orchestrator can still author matrix for the 12 WAZA codes (B, C-O, MF-2/2L/3, PBZ, PI, R-12/15/8.4 …) and reach customer-side verdicts on the bound 4,707 parcels.

## Multi-county Puget Sound carry — bonus probe

Per Master's bonus check, all 4 Puget Sound counties pass the **strengthened Class A bbox primitive** at ≥50 % overlap:

| County | parcel bbox | WAZA bbox | bbox overlap | Class A primitive |
|--------|-------------|-----------|--------------:|:-----------------:|
| King | `[-122.55, 47.07, -121.08, 47.79]` | `[-122.53, 47.08, -121.09, 47.81]` | **95.7 %** | **PASS** |
| Pierce | `[-122.85, 46.72, -121.44, 47.42]` | `[-122.84, 46.73, -121.37, 47.40]` | **96.3 %** | **PASS** |
| Snohomish | `[-122.44, 47.77, -120.95, 48.31]` | `[-122.40, 47.78, -120.91, 48.30]` | **93.3 %** | **PASS** |
| Kitsap | `[-123.05, 47.39, -122.45, 47.95]` | `[-123.02, 47.40, -122.47, 47.94]` | **89.9 %** | **PASS** |

**All 4 clear the 50 % gate by 40-46 pp.** Combined with Phase 6A.1's parcel-source carry (797,786 additional Puget Sound parcels under one adapter), this means **one adapter clone unlocks 3 more Tier 2 counties at near-zero rebuild cost**:

- Pierce: 339,590 parcels + 19,116 WAZA features × 22 jurisdictions
- Snohomish: 318,594 parcels + 34,705 WAZA features × 20 jurisdictions
- Kitsap: 139,602 parcels + 15,606 WAZA features × 5 jurisdictions

**Total Puget Sound multi-county carry: 1,432,978 parcels + 126,327 WAZA features × 86 jurisdictions under one tested adapter shape.** Documented for follow-up Tier 2 dispatches.

## Adapter design

`backend/scripts/ingest_king_wa_zoning.py` — Class A backfill mirroring Westchester per-muni pattern (PR #233 collision-fix preserved: `muni_name` for `raw_attributes` filter vs `prod_city_value` for `parcels.city` filter, separate params). Two subcommands: `preflight` (read-only pipeline shape) and `fire` (writes to prod, requires `--i-know-this-writes-to-prod`).

`backend/data/king_wa_zoning_directory.json` (pre-staged in PR #259) — 2 entries:
- **Bellevue**: WAZA primary (`Jurisdiction='Bellevue'`), Bellevue city zoning (`Zoning/FeatureServer/7`) as fallback. Used WAZA for this fire.
- **Mercer Island**: WAZA primary (`Jurisdiction='Mercer Island'`), Mercer Island city zoning (`Mercer_Island_Planning_Layers/FeatureServer/2`) as fallback. Used WAZA for this fire; city fallback recommended for re-fire to close coverage gate.

## Refresh status

`POST /api/admin/coverage/refresh?jurisdiction_id=1e65c053-…` fired once at 2026-06-15. Client timed out at 200 s (Railway proxy past 150 s ceiling). Did NOT retry per "ONE refresh per task" rule. DB-level numbers in this doc are authoritative; audit recompute will reconcile on next refresh cycle.

Expected post-refresh state for King WA: `parcel_zoning_code_coverage_pct ≈ 5.2 %` (33,022 / 635,186 — Bellevue + Mercer Island only out of full county), `matrix_zone_count = 0`, `blocking_gaps = ['low_matrix_match_pct', 'no_zone_use_matrix']`, `operational_readiness = partial`. **`missing_bbox` will NOT fire** because of the inline UPDATE (PR #261 lesson applied).

## What changed in the repo

- `backend/scripts/ingest_king_wa_zoning.py` (new) — Class A adapter
- `docs/OP5_KING_WA_PHASE6A2.md` (this file)
- `docs/PHASE2_PROGRESS.md` §15 — 2026-06-15 entry

No backend code changes. No matrix authoring (orchestrator's domain).

## Phase boundary

This PR is Phase 6A.2 → orchestrator-matrix rollback point. If Master accepts:
- Orchestrator's King WA matrix sprint authors against the WAZA code namespace (R-5 / R-10 / DT-MU / etc; NOT the post-2017 Bellevue city codes).
- Bellevue + Mercer Island flip operational once matrix coverage clears 90 % match.
- Follow-up dispatch options: (a) Mercer Island re-fire from city fallback, (b) Pierce/Snohomish/Kitsap clone dispatches.

## Operational state

Operational count unchanged: **20**. King moves `not_loaded` → **`partial`** (zoning binding live for Bellevue + Mercer Island; bbox populated inline; awaits matrix). When matrix lands, King flips operational → 21.
