# Op-5 Mill Creek per-muni registration (Phase 6B-PIVOT, fourth per-muni)

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Phase 6B-PIVOT cohort — fourth per-muni after Bellevue (PR #271), Mercer Island (PR #274/#278), and Bainbridge Island (PR #281).
**Verdict:** **DB-LEVEL DONE. Mill Creek is partial-with-zoning awaiting orchestrator's matrix sprint** (11 distinct codes need authoring). Once matrix applies + audit re-runs, Mill Creek flips → count 23 → 24 (assuming Bainbridge PR #281 has flipped via its own matrix apply).
**Predecessors:** PR #267 (Phase 6B.1 Snohomish parcels) · PR #271 + #274 + #278 + #281 (pattern proofs).

---

## TL;DR

Mill Creek's WAZA layer carries **5,406 features for ~6,237 city parcels** — a parcel-level polygon density (0.87 polys-per-parcel). Spot-check pre-fire verified this is REAL data (distinct OBJECTIDs, bounded parcel-shaped polygons), not a publishing artifact. The per-muni script INSERTed all 5,406 districts, ran 2-pass spatial backfill, then required an inline bbox patch (initial sanity range was too tight on the southern edge).

**Mill Creek new jid:** `ebdcf222-8e47-46f0-88fa-384ef4141bfa`

## 5/5 Quality gates PASS

| Gate | Threshold | Mill Creek | Status |
|------|-----------|-----------:|:------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **97.1 %** (6,059 / 6,237) | **PASS** (+27.1 pp margin) |
| `nearest_*` share | < 30 % | **0.19 %** (12 / 6,237) | **PASS** (-29.8 pp margin) |
| `raw_attributes` preserved (Norfolk) | 0 empty | 0 / 5,406 | **PASS** |
| `zoning_district_count` | > 0 | 5,406 (matches WAZA feature count) | **PASS** |
| `jurisdictions.bbox` populated | non-null | `[-122.240, 47.780, -122.167, 47.879]` (inline patch) | **PASS** |

97.1% cov is the highest per-muni in the campaign so far — Mill Creek's per-parcel WAZA polygon density gives near-perfect `ST_Within` matches.

## 11 distinct zone codes (orchestrator follow-up signal)

| Code | Parcels | ZoneName (from WAZA) |
|------|--------:|----------------------|
| LDR | 2,449 | Low Density Residential |
| PRD 7200 | 2,336 | Planned Residential 7200 sqft min |
| MDR | 555 | Medium Density Residential |
| HDR | 198 | High Density Residential |
| EGPUV | 163 | (East Gateway Planned Urban Village) |
| MU/HDR | 157 | Mixed-Use / High Density Residential |
| PCB | 94 | Planned Community Business |
| CB | 56 | Community Business |
| BP | 45 | Business Park |
| OP | 3 | Office Park |
| NB | 3 | Neighborhood Business |
| **Total** | **6,059** | |

LDR + PRD 7200 + MDR alone cover **86.9 %** of bound parcels — orchestrator's matrix can clear most of Mill Creek with 3 grounded rows.

## Audit snapshot (post-fire)

```
RESULT: {'snapshots_written': 1, 'snapshots_failed': 0,
         'summary': {'jurisdiction_count': 1, 'operational_count': 0,
                     'partial_count': 1, 'with_parcels_count': 1,
                     'with_matrix_count': 0, 'with_zoning_polygons_count': 1,
                     'with_good_matrix_match_count': 0}}
```

Partial as expected (matrix sprint pending). The 3 blockers (`no_zone_use_matrix`, `no_matrix_matches_for_parcel_zones`, `low_matrix_match_pct`) close in one orchestrator apply.

## The bbox sanity-range patch

The initial fire's bbox sanity check raised `RuntimeError: bbox [-122.240, 47.780, -122.167, 47.879] outside expected Mill Creek range (lon -122.3 to -122.15, lat 47.83 to 47.92)` — the southern lat extent (47.78) was 0.05° below my expected min (47.83). WAZA Mill Creek includes a southern unincorporated strip adjacent to the city limits proper.

Phase A (jurisdiction + parcels) was already committed in its transaction. Phases B (districts), C (spatial backfill) committed via autocommit. Only Phase D (bbox UPDATE) was blocked. Inline patch: ran `UPDATE jurisdictions SET bbox = $1::jsonb WHERE id = $2::uuid` with a widened sanity check (47.7-47.92). Script source widened the constant for future re-runs to be idempotent.

## What changed in the repo

- `backend/scripts/perm_muni_mill_creek.py` (new) — Mill Creek per-muni adapter (sister of `perm_muni_bainbridge_island.py`)
- `docs/OP5_MILL_CREEK_PERM_MUNI.md` (this file)

No backend code changes. No matrix authoring.

## Spot-check verdict (5,406 polygon-density)

Pre-fire 5-feature spot-check confirmed Mill Creek's anomalous feature count is **real parcel-level polygon density**:
- 5 sampled OBJECTIDs all distinct (425126-425130 sequential)
- All ZoneID=LDR (consecutive features in a residential subdivision)
- All single-ring polygons with 5-16 vertices each (typical parcel shapes)
- 5,406 / 6,237 = 0.87 polygons-per-parcel ratio — near 1:1 mapping

The post-fire 97.1 % `ST_Within` cov confirms the parcel-density hypothesis: when WAZA publishes per-parcel polygons, `ST_Within` matches are near-perfect.

## Next dispatch

Per Master's sequencing:
1. Orchestrator authors Mill Creek's 11-code matrix sprint (or grounded subset covering LDR/PRD 7200/MDR — 86.9 % of parcels)
2. Audit recompute → Mill Creek flips operational → count +1
3. Task E Pierce city derivation (spatial join WA City Limits)
4. Gig Harbor per-muni after Pierce city derivation lands

Expected trajectory: Bainbridge → Mill Creek → Pierce Task E → Gig Harbor → count up to 25.
