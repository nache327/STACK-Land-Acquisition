# Op-5 Hennepin Minnetonka Phase 7A.3 — city zoning Class A ingest

**Owner:** Lane A
**Date:** 2026-06-18
**Sprint type:** Phase 7A.3 sibling of Edina (PR #295) + Plymouth (PR #304) + Eden Prairie (PR #303). Minnetonka is Hennepin wealth-band #3 at 20,911 parcels.
**Verdict:** **DB-LEVEL IN FLIGHT.** 17,529 zoning_districts being INSERTed under Minnetonka jid `3267204b-…` from ZoneCo direct GIS. Spatial backfill + bbox + 5-gate verdict pending fire completion at PR open time.
**Predecessors:** PR #294 Phase 7A.2 (Minnetonka jid registered, 20,911 parcels moved from Hennepin umbrella) · PR #295 Edina · PR #303 Eden Prairie · PR #304 Plymouth.

---

## TL;DR

ZoneCo (Minnetonka's planning consultant) publishes a parcel-density Feature Service named "Proposed Zoning". Field-level inspection confirms the substrate is current: `ZONING` field carries the existing zoning code, `Proposed_Zone` is a separate column for proposed changes. 17,571 source features → 17,529 zoning_districts INSERTed under Minnetonka jurisdiction. Spatial backfill expected to bind ~100 % via parcel-density `ST_Within` (Edina/Eden Prairie precedent).

## Substrate-vs-proposed risk — mitigated at field level

Master flagged Minnetonka as LOW Path B confidence due to ZoneCo's service-level name "Proposed Zoning" (vs Edina's clean "Existing Map" naming). Field probe confirmed:

| Field | Verdict |
|-------|---------|
| `ZONING` | **Existing/current authoritative code** (used as zone_code) |
| `Proposed_Zone` | Proposed change (NOT used; preserved in raw_attributes) |
| `LAND_USE` | Current land-use classification (passthrough only) |

The "Proposed Zoning" service name appears to be ZoneCo's branding for an active rezoning project. The fields themselves carry both states. Master's substrate-vs-proposed risk is materially mitigated at the field level.

## Source — ZoneCo Minnetonka

```
https://services3.arcgis.com/rNrGj3CxKnr9E71f/arcgis/rest/services/
20260521_Zoning_Map_Minnetonka/FeatureServer/0
```

- Publisher: **ZoneCo (Minnetonka planning consultant)** — vintage 2026-05-21
- Layer: `Proposed Zoning` (parcel-density — one polygon per parcel)
- SR: 102100 (Web Mercator); server-side reprojected via `outSR=4326`
- maxRecordCount: 2,000
- 17,571 source features
- 14-key bounded raw_attributes passthrough (OBJECTID, PID, AREA_, PERIMETER, ACRES, HOUSE_NUMB, STREET, ADDRESS, UNIT, ZIP, IM_ID, ZONING, Proposed_Zone, LAND_USE)

## 17 distinct codes (vs orchestrator's 14-row pre-stage)

Per preflight, source returns **17** distinct codes:

```
B-1, B-2, B-3, I-1, IN WAYZATA, PID, PUD, PURD,
R-1, R-1 PURD, R-2, R-2 PURD, R-3, R-3 PURD, R-4, R-4 PURD, R-5
```

Orchestrator pre-staged 14 codes (commit `5287ee4`, mixed 10 ArcGIS + 4 ordinance). **Drift: +3 codes** — likely the R-N PURD variants (planned unit redevelopment overlays). Orchestrator pre-stage was slightly conservative-low. Substrate-first catchall × 4 covers verdict gaps (per Master's discipline).

Codes flagged for substrate-first cleanup queue:
- **`I-1`** (Industrial) — Master pre-flagged in dispatch
- **`PID`** (Planned Industrial District) — same flag as Edina's PID code
- **`IN WAYZATA`** — cross-jurisdictional anomaly (parcels split between Minnetonka + Wayzata) — investigate post-flip

## Quality gates (verdict-pending at PR commit time)

| Gate | Threshold | Minnetonka |
|------|-----------|--------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | (running — Edina/EP/Plymouth precedent: ~100 %) |
| `nearest_*` share | < 30 % | (running — parcel-density expected <1 %) |
| `raw_attributes` preserved (Norfolk) | 0 empty | (running) |
| `zoning_district_count` | > 0 | **17,529** ✓ |
| `jurisdictions.bbox` populated inline (PR #261) | non-null + range | (running — sanity range lon -93.55 to -93.35 lat 44.88 to 45.00) |

PR description will be amended with final 5-gate verdict once spatial backfill completes.

## Patterns carried forward

This adapter incorporates:
- **PR #285 Pierce Task E** — emit each ring as separate polygon body in MULTIPOLYGON, let PostGIS reconstruct topology via `ST_Multi(ST_MakeValid(...))`
- **PR #303 Eden Prairie** — skip degenerate rings (<4 points)
- **PR #261** — inline jurisdictions.bbox UPDATE
- **PR #253** — skip prod ROLLBACK preflight at Class A scale
- **PR #233** — title-case discipline (Minnetonka)

## What's in the PR

- `backend/scripts/perm_muni_minnetonka_zoning_ingest.py` (new) — Minnetonka zoning adapter (parcel-density source)
- `docs/OP5_HENNEPIN_MINNETONKA_PHASE7A3.md` (this file)

## Hard rules honored

- raw_attributes preserved (Norfolk gate)
- municipality matches prod_city_value ('Minnetonka', title-case PR #233)
- Inline jurisdictions.bbox (PR #261)
- PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
- Skip prod ROLLBACK preflight (PR #253)
- Don't author matrix (orchestrator's 14-row pre-stage covers — Path A apply if drift acceptable, Path B re-author otherwise)
- Halt-and-report
- ONE refresh per phase

## Stack note

Branch off main (Phase 7A.2 PR #294 already merged into main).

## Next dispatch

1. Spatial backfill completes (in flight at PR open time) — PR amended with 5-gate verdict
2. Orchestrator decides Path A apply (14-row matrix sprint via `_upload-matrix-rows`, ~5-10 min) vs Path B re-author given +3 code drift
3. Audit recompute (direct-python until PR #280 deploys) — Minnetonka flips operational → count step up
4. Sibling PRs status:
   - **PR #295 Edina** — flipped 25 → 26 confirmed (matrix applied 2026-06-18T22:32:13Z)
   - **PR #304 Plymouth** — 5/5 PASS DB-level; awaiting orchestrator's 24-row apply
   - **PR #303 Eden Prairie** — 5/5 PASS DB-level; awaiting orchestrator's 28-row apply
   - **Minnetonka (this PR)** — awaiting spatial backfill verdict + orchestrator apply
5. **Wayzata** — deferred per Master's Option B (polygon-serviceable but not formally operational pending GeoPDF tooling; see `OP5_HENNEPIN_WAYZATA_DEFERRAL.md`)
6. **Maricopa Wave 2 (PR #305)** firing in parallel — independent
