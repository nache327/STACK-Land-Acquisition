# Op-5 Fairfield Greenwich Phase 7C.3 — city zoning Class A ingest

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** Phase 7C.3 second Fairfield fire after Stamford (PR #308 MERGED, applied via mercer-bainbridge-standby `4bd9c1e`). Greenwich PROMOTED from LOW Path B (PDF/web-map per Diagnostic PR #257) to HIGH Path A by Lane A's live GIS probe — Town of Greenwich publishes a public ArcGIS Feature Server.
**Verdict:** **DB-LEVEL DONE. 5/5 quality gates PASS @ 100.0 % cov + 0.1 % nearest.** Campaign's 6th consecutive 100 % ingest (Edina, Plymouth, Eden Prairie, Stamford, Minnetonka, Greenwich).
**Predecessors:** PR #307 Phase 7C.2 (Greenwich jid registered) · PR #308 Stamford (sibling pattern) · Diagnostic PR #257 (original LOW Path B verdict — overturned by live probe).

---

## 5 / 5 Quality gates PASS

| Gate | Status |
|------|:------:|
| `parcel_zoning_code_coverage_pct` (≥70 %) | **100.0 %** (18,040 / 18,042) — PASS |
| `nearest_*` share (<30 %) | **0.1 %** (24 / 18,042) — PASS |
| `raw_attributes` preserved (Norfolk) | **0 empty** — PASS |
| `zoning_district_count` (>0) | **285** — PASS |
| `jurisdictions.bbox` populated inline (PR #261) | `[-73.728, 40.981, -73.555, 41.144]` — PASS |

Cleanest Fairfield ingest result. Stamford precedent: 100.0 % @ 0.1 % nearest. Greenwich matches exactly.

## Path A promotion — LOW Path B verdict overturned

Diagnostic PR #257 had labeled Greenwich LOW Path B based on the publicly-visible Tiger-Bond hosting and ordinance-only paths. Lane A's 2026-06-19 live probe found the Town's authoritative ArcGIS Feature Server:

```
https://services2.arcgis.com/cYiUUgMhu4YB7W9G/arcgis/rest/services/
Zone_Boundaries/FeatureServer/0
```

- Publisher: **Daniel.Clark_greenwichgis** (greenwichgis.maps.arcgis.com org — official Town GIS)
- Powers the official Town Zoning Instant App (`dd08394df7544ef7862d946a2ad5d7a5`)
- 285 polygons
- Geom: Polygon, SR 102100 (Web Mercator) → outSR=4326
- Code field: `Layer` (15 char)
- Name field: `District` (long descriptions)
- Aux: `ZoneType` (Residential/Commercial/Waterfront/Planned), `Use_group`, `Hold`, `UseGroup`, `Conserv`
- 51 distinct codes (47 bound; 4 codes had no parcels — likely Conservation/Hold variants)

## HALT-and-fix: OBJECTID field name

First preflight returned 0 features — orderByFields=OBJECTID rejected by source. Layer actually uses `OBJECTID_1` (CAD-source artifact). Patched to `OBJECTID_1` throughout (orderByFields + RAW_PASSTHROUGH + error log). Second preflight clean: 285 features, 51 codes.

This is the discipline working: catch field-name drift before fire commits.

## Top 10 codes by parcel binding

| Code | Parcels | Share |
|------|--------:|------:|
| R-12 | 4,293 | 23.8 % |
| R-7 | 3,199 | 17.7 % |
| R-6 | 2,526 | 14.0 % |
| RA-1 | 2,296 | 12.7 % |
| RA-2 | 2,256 | 12.5 % |
| RA-4 | 1,322 | 7.3 % |
| R-20 | 996 | 5.5 % |
| LBR-2 | 180 | 1.0 % |
| CGBR | 161 | 0.9 % |
| CGB | 158 | 0.9 % |

Top 7 residential codes cover 94 % of parcels — Greenwich is densely residential. RA-1/RA-2 wealth band confirmed.

## What's in the PR

- `backend/scripts/perm_muni_greenwich_zoning_ingest.py` (new) — Greenwich zoning adapter (true-zoning-map source, Stamford-shape)
- `docs/OP5_FAIRFIELD_GREENWICH_PHASE7C3.md` (this file)

## Hard rules honored

- raw_attributes preserved (Norfolk gate)
- municipality matches prod_city_value ('Greenwich', title-case PR #228)
- Inline jurisdictions.bbox (PR #261)
- PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
- Skip prod ROLLBACK preflight (PR #253)
- Don't author matrix (Greenwich was LOW Path B citations-only in orchestrator's pre-stage — Path A promotion will trigger re-author at apply-time; orchestrator absorbs the upgrade)
- Halt-and-report (caught + fixed OBJECTID_1 field-name drift before fire)
- ONE refresh per phase

## Next dispatch

1. Orchestrator absorbs Path A promotion: applies 51-code Greenwich matrix (re-authored from citations-only LOW Path B pre-stage)
2. **Greenwich flips operational → count 31 → 32** (after PV applies first)
3. Westport / Darien / New Canaan remain DEFERRED (Vessel Technologies + Tighe-Bond + AxisGIS token-gated)

## Sibling status

- **Maricopa wave**: PV PR #310 5/5 → 31; Scottsdale 7B.2 + 7B.3 firing in parallel (this turn)
- **Fairfield wave**: Stamford 30 → Greenwich (this PR) → 32 (after PV at 31)
- **Hennepin wave**: 25 → 28 → 29 (complete; Minnetonka + Stamford pushed count → 30)
- **Oakland MI wave**: firing in parallel (this turn — Phase 7E.1 county + parcel ingest)
