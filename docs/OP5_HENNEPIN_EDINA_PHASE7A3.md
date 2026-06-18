# Op-5 Hennepin Edina Phase 7A.3 — city zoning Class A ingest

**Owner:** Lane A
**Date:** 2026-06-18
**Sprint type:** Phase 7A.3 — first Hennepin per-muni zoning ingest after Phase 7A.2 (PR #294) registered Edina jurisdiction + moved 21,343 parcels.
**Verdict:** **DB-LEVEL DONE. 5 / 5 quality gates PASS with 100 % parcel_zoning_code_coverage_pct** — the cleanest per-muni result of the campaign. Edina flips operational once orchestrator's 37-row matrix sprint applies. Operational count steps 25 → **26**.
**Predecessors:** PR #294 Phase 7A.2 (Edina jurisdiction registered, jid `2b08fa13-…`) · PR #287 Gig Harbor pattern (per-muni zoning Class A) · PR #285 Pierce Task E (WKT-via-PostGIS pattern).

---

## TL;DR

ZoneCo (Edina's planning consultant) publishes a parcel-density "Existing Map" Feature Service. One polygon per Edina parcel, joined to `PID`, with `E_Zoning` carrying the authoritative current zoning code. 21,515 features INSERTed as `zoning_districts`. Spatial backfill bound **every Edina parcel via contained ST_Within** (21,333 contained + 10 nearest_50m = 21,343 / 21,343 = **100.0 %**).

## 5 / 5 Quality gates PASS

| Gate | Threshold | Edina | Status |
|------|-----------|------:|:------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **100.0 %** (21,343 / 21,343) | **PASS** (+30 pp margin) |
| `nearest_*` share | < 30 % | **0.0 %** (10 / 21,343) | **PASS** (-30 pp margin) |
| `raw_attributes` preserved (Norfolk) | 0 empty | 0 / 21,515 | **PASS** |
| `zoning_district_count` | > 0 | 21,515 | **PASS** |
| `jurisdictions.bbox` populated inline (PR #261) | non-null + sanity range | `[-93.402, 44.860, -93.319, 44.931]` | **PASS** |

100 % cov is the cleanest per-muni result of the campaign so far (vs Mill Creek 97.1 %, Bellevue 85.2 %, Gig Harbor 82.4 %, Mercer 79.6 %, Bainbridge 70.9 %).

## Source — ZoneCo Existing Map

```
https://services3.arcgis.com/rNrGj3CxKnr9E71f/arcgis/rest/services/
2026_04_13_Existing_Map_Edina_WFL1/FeatureServer/1
```

- Publisher: **ZoneCo** (Edina's planning consultant — vintage 2026-04-13)
- Layer: `Base Zoning Districts` (parcel-density — one polygon per parcel)
- Geometry: Polygon, SR 102100 (Web Mercator); server-side reprojected via `outSR=4326`
- Code field: `E_Zoning` (Existing Zoning, authoritative)
- Cross-ref field: `PID` (joins back to Hennepin LAND_PROPERTY parcels)
- Bounded raw_attributes passthrough (18 keys): OBJECTID_1, PID, HOUSE_NO, STREET_NM, MAILING__1, ZIP_CD, E_Zoning, P_Zoning, LotSizeSubarea, HeightOverlay + source provenance

## 37 distinct codes (vs orchestrator pre-stage of 39)

Per Master: orchestrator pre-staged 39 Edina codes. Source returns **37** — orchestrator was slightly conservative-high. Surplus matrix rows for non-binding codes are no-op (no harm to audit gates).

Top 10 codes by parcel binding:

| Code | Parcels | Share |
|------|--------:|------:|
| R-1 | 13,233 | 62.0 % |
| PRD-3 | 2,516 | 11.8 % |
| PRD-4 | 2,130 | 10.0 % |
| MDD-5 | 935 | 4.4 % |
| MDD-6 | 679 | 3.2 % |
| R-2 | 500 | 2.3 % |
| PSR-4 | 349 | 1.6 % |
| MDD-4 | 175 | 0.8 % |
| **PID** | **133** | **0.6 %** ← cleanup-queue candidate |
| PCD-3 | 128 | 0.6 % |

R-1 + PRD-3 + PRD-4 + MDD-5 + MDD-6 + R-2 cover **94.7 %** of bound parcels — orchestrator's matrix sprint can clear majority of Edina with 6 grounded rows.

PUD-1 through PUD-25 are highly granular planned developments (1-21 parcels each, total ~64 parcels = 0.3 %). Orchestrator's pre-stage covers them.

`PID` code = Edina's "Planned Industrial District" — added to cleanup queue (per Master's substrate-first catchall × 4 discipline, queued for verdict-truth review post-ingest).

## Path A confidence — HIGH validated

Per Master's brief Edina was rated HIGH Path A confidence. Verified true:
- ArcGIS-direct paginated cleanly (21,529 features in single fetch session)
- 37 codes matches orchestrator's pre-stage within 2-row tolerance
- Spatial backfill perfect: 21,333 contained + 10 nearest_50m fallback (Edina's PID-bound polygons cover effectively all parcels via centroid containment)

## What changed in the repo

- `backend/scripts/perm_muni_edina_zoning_ingest.py` (new) — standalone Edina zoning adapter
- `docs/OP5_HENNEPIN_EDINA_PHASE7A3.md` (this file)

No backend code changes. raw_attributes preserved on parcels (Phase 7A.1's rich raw kept); NEW raw_attributes on zoning_districts from source (18 keys including ZoneCo publisher + vintage provenance).

## WKT-via-PostGIS pattern carried forward

Used the PR #285 Pierce Task E pattern: emit each ring as separate polygon body in MULTIPOLYGON, delegate topology to `ST_Multi(ST_MakeValid(...))`. Avoids the ring-winding heuristic. Worked perfectly on Edina's polygon geometry.

## Next dispatch

Per Master's sequencing:
1. **Orchestrator applies 37-row matrix sprint** via `_upload-matrix-rows` (~5-10 min Path A)
2. **Audit recompute** — once PR #280 (audit CTE scoping) merges, HTTP refresh returns in seconds; until then, direct-python invocation per Mercer PR #278 pattern
3. **Edina flips operational** → count **25 → 26**

**Plymouth + Eden Prairie Phase 7A.3** fire in parallel (next dispatch — HIGH Path A confidence per Master).
