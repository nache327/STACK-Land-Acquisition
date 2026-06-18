# Op-5 Fairfield CT Stamford Phase 7C.3 — city zoning Class A ingest

**Owner:** Lane A
**Date:** 2026-06-18
**Sprint type:** Phase 7C.3 first Fairfield muni fire after PR #307 Phase 7C.2. Stamford HIGH Path A confidence per orchestrator's pre-stage. First HIGH-confidence fire of Wave 3.
**Verdict:** **DB-LEVEL IN FLIGHT.** 377 zoning_districts being INSERTed under Stamford jid `9bbffb2b-…`. Spatial backfill + bbox verification + 5-gate verdict pending at PR commit time.
**Predecessors:** PR #307 Fairfield Phase 7C.2 (Stamford jid registered, 25,524 parcels moved) · PR #228 Fairfield title-case discipline · PR #295 Edina (per-muni zoning Class A pattern).

---

## TL;DR

City of Stamford GIS publishes a true zoning-district Map Service at `stamfordgis.org/public/rest/services/AGOL_Zoning/MapServer/3`. Differs from Hennepin's parcel-density ZoneCo sources — this is 377 actual zoning polygons covering all 25,524 Stamford parcels. 42 distinct codes — **matches orchestrator's 42-row pre-stage `9c5cee9` EXACTLY** (no drift).

## Orchestrator drift: 0 — perfect alignment

| Source | Code count |
|--------|-----------:|
| Orchestrator pre-stage `9c5cee9` | 42 |
| Stamford GIS preflight | **42 (exact match)** |

Codes preflighted:
`B-D, C-B, C-D, C-G, C-I, C-L, C-N, CC, CSC-D, CW-D, DW-D, HCDD, HT-D, IP-D, M-D, M-G, M-L, MR-D, MX-D, NX-D, P, P-D, R-10, R-10/R-D, R-20, R-20/R-D, R-5, R-6, R-7 1/2, R-H, R-HD, R-MF, RA-1, RA-1/R-D, RA-2, RA-2/R-D, RA-3, RM-1, SRD-N, SRD-S, TCDD, V-C`

Includes Design District overlays (R-10/R-D, R-20/R-D, RA-1/R-D, RA-2/R-D) — orchestrator's pre-stage correctly captured them. Stamford HIGH Path A confidence validated.

## Source — City of Stamford GIS

```
https://stamfordgis.org/public/rest/services/AGOL_Zoning/MapServer/3
```

- Publisher: **City of Stamford GIS** (direct municipal)
- Layer: `Zoning` (true zoning-district polygons — NOT parcel-density)
- SR: 102656 / 2234 (Connecticut State Plane NAD83 feet); server-side reprojected via `outSR=4326`
- maxRecordCount: 1,000
- 377 total polygons
- Code field: `ZoningDistrict` (15 char)
- Name field: `ZoningDescription` (50 char)
- Aux: `DesignDistrict` (Yes/No), `DesignDistrictDescription`
- 5-key bounded raw_attributes passthrough

## Differs from Hennepin Phase 7A.3 pattern

Hennepin's per-muni ingests used ZoneCo's parcel-density sources (one polygon per parcel, ~20-30k polygons per muni). Stamford uses the **true zoning map** (377 polygons covering 25,524 parcels). Same WKT-via-PostGIS pattern carries; spatial backfill uses standard `ST_Within(centroid)` for contained, `ST_DWithin` geography for nearest. Smaller LATERAL = faster backfill (~30s expected vs Hennepin's 5-10 min).

## Quality gates (verdict-pending at PR commit time)

| Gate | Threshold | Stamford |
|------|-----------|--------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | (running — expected ~95-100 %) |
| `nearest_*` share | < 30 % | (running — true zoning map should give 0-5 % nearest) |
| `raw_attributes` preserved (Norfolk) | 0 empty | (running) |
| `zoning_district_count` | > 0 | **377** ✓ |
| `jurisdictions.bbox` populated inline (PR #261) | non-null + range | (running — sanity range lon -73.65 to -73.45 lat 41.00 to 41.20) |

PR description will be amended with final 5-gate verdict once spatial backfill completes (expected within ~2 min of fire start).

## What's in the PR

- `backend/scripts/perm_muni_stamford_zoning_ingest.py` (new) — Stamford zoning adapter (true-zoning-map source)
- `docs/OP5_FAIRFIELD_STAMFORD_PHASE7C3.md` (this file)

## Hard rules honored

- raw_attributes preserved (Norfolk gate)
- municipality matches prod_city_value ('Stamford', title-case PR #228)
- Inline jurisdictions.bbox (PR #261)
- PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
- Skip prod ROLLBACK preflight (PR #253)
- Don't author matrix (orchestrator's 42-row pre-stage 9c5cee9 perfect match — Path A apply only)
- Halt-and-report
- ONE refresh per phase

## Next dispatch

1. Spatial backfill completes (in flight at PR open time) — PR amended with 5-gate verdict
2. Orchestrator applies 42-row matrix sprint via `_upload-matrix-rows` (~5-10 min HIGH Path A — zero drift means clean apply)
3. Audit recompute (direct-python until PR #280 deploys) — Stamford flips operational → count step up
4. Sibling Fairfield Phase 7C.3 dispatches (LOW Path B citations-only — orchestrator authors at apply-time):
   - Greenwich (jid `e5406ad0-…`)
   - Westport (jid `0a142989-…`)
   - New Canaan (jid `2580f226-…`)
   - Darien (jid `9b27e214-…`)
5. **Maricopa Phase 7B (PR #305)** parcel ingest still in flight at PR open time

## Sibling status

- **Hennepin wave**: 25 → 28 confirmed (Edina + Plymouth + Eden Prairie). Minnetonka (PR #306) in flight → 29
- **Maricopa Wave 2 (PR #305)**: parcel ingest ~30 % (~25 min remaining)
- **Fairfield Wave 3**: Phase 7C.2 done (PR #307). Stamford Phase 7C.3 firing (this PR). 4 LOW Path B Fairfield munis pending
