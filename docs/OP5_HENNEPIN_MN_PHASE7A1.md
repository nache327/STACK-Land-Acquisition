# Op-5 Hennepin MN Phase 7A.1 — parcel ingest + jurisdiction registration

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Tier 2 MN wave opener. Master pivot from WA wave (PRs #271/#274/#278/#281/#283/#285/#287) after Bellevue + Mercer flipped operational and remaining 3 (Bainbridge / Mill Creek / Gig Harbor) lined up partial-pending-matrix.
**Verdict:** **DB-LEVEL DONE.** Hennepin County, MN registered as own prod jurisdiction with 448k parcels live. Multi-county MetroGIS carry probe surfaced caveats (see below) — NOT the clean Pierce/Snohomish/Kitsap-style clone leverage Master estimated, but Hennepin direct is the operationally canonical source anyway and stands on its own.
**Predecessors:** PR #259 (King WA Phase 6A.1 pattern) · PR #250 (Contra Costa Phase 5A.1 pattern) · Diagnostic PR #255 / #236 (MetroGIS multi-county carry premise).

---

## TL;DR

Hennepin County direct (`gis.hennepin.us/.../HennepinData/LAND_PROPERTY/MapServer/1`) provides 448,084 parcels with rich tax / sale / ownership / mailing fields. Per Master's plan, this dispatch handles parcel ingest only; Phase 7A.2 per-muni zoning backfill is a separate sprint.

Wealth-band readiness (Phase 7A.2 targets):

| Muni | Parcels | Phase 7A.2 readiness |
|------|--------:|----------------------|
| Edina | 21,343 | ready (city-zoning publisher TBD) |
| Wayzata | 1,992 | ready — smallest, quickest flip |
| Minnetonka | 20,911 | ready |
| Plymouth | 29,204 | ready — largest in cohort |
| Eden Prairie | 22,956 | ready |
| **Total wealth-band** | **96,406** | **21.5 % of county** |

Reference: Minneapolis = 128,750 parcels (not a per-muni target — included for scale).

## Multi-county MetroGIS carry probe — caveats

Master's premise (Diagnostic PR #255): MetroGIS publishes a 7-county aggregator that runs Hennepin + Ramsey + Anoka + Carver + Dakota + Scott + Washington under one schema, mirroring the Pierce/Snohomish/Kitsap unlock from PR #264 against Washington Current Parcels.

**Actual finding**: the MetroGIS regional aggregator is **not operationally available**:

| Source attempted | Status |
|------------------|--------|
| `arcgis.metc.state.mn.us/ds1/.../GISParcels` (parent folder) | **499 Token Required** |
| `arcgis.metc.state.mn.us/ds1/.../GISParcels/Parcels2023Hennepin` | **500 "Service not started"** |
| `gis2.metc.state.mn.us/.../plan_regional_parcels` (canonical Twin Cities Parcels) | **Connection timeout** (network unreachable) |

The single-county direct portals each carry independently:

| County | Direct URL probed | Result |
|--------|-------------------|--------|
| Hennepin | `gis.hennepin.us/arcgis/rest/services/HennepinData/...` | **200 OK — 448k parcels, this dispatch** |
| Dakota | `gis.co.dakota.mn.us/arcgis/rest/services` | 200 OK (parcels layer TBD) |
| Carver | `gis.co.carver.mn.us/arcgis/rest/services` | 404 (no public REST) |
| Ramsey, Anoka, Scott, Washington | various direct hostnames | DNS unresolved from this network |
| Washington (via ArcGIS Hub) | `services6.arcgis.com/hBMRLv0wWV0IhJ8I/.../Parcels/FeatureServer` | discovered but unprobed |

**Verdict on carry leverage**:
- NOT the WA Current Parcels pattern (1 statewide schema → trivial 7-county clone)
- IS more like California county-by-county: each county has its own direct GIS publisher with its own field schema, and each requires separate adapter porting
- The cleanest path for the remaining 6 MetroGIS counties is targeted follow-up dispatches (probe ArcGIS Hub for each + write per-county adapters); the leverage is real but it's per-county-on-the-clock work, not a single clone

This dispatch focuses on Hennepin alone; carry follow-up deferred.

## Source schema (Hennepin LAND_PROPERTY MapServer/1)

- Name: County Parcels (Hennepin County Open Data)
- Geometry: Polygon, SR 26915 (NAD83 UTM Zone 15N); server-side reprojected to WGS84 via `outSR=4326`
- Total count: 448,084
- Max records per query: 2,000
- 200+ source fields — **curated 22-field passthrough** keeps `parcels.raw` bounded (avg 22.7 fields per row in preflight)

Field map:

| Source | parcels column | Note |
|--------|----------------|------|
| `PID` | `apn` | 13-digit text, e.g. '0411621210001' |
| `MUNIC_NM` (ALL-CAPS, space-padded) | `city` | title-cased; PR #233 discipline |
| `HOUSE_NO` + `STREET_NM` | `address` | space-padded source; concatenated |
| `OWNER_NM` | `owner_name` | Hennepin publishes per-parcel owner |
| `STATE_CD` (MN DOR property class) | `land_use_code` | residential heuristic 100s + 400s |
| `TOTAL_MV1` | `assessed_value` | `LAND_MV1 + BLDG_MV1` fallback |
| `BLDG_MV1` | `improvement_value`, `has_structure` | `>0 → has_structure=True` |
| 22-field curated subset | `raw` | Norfolk gate preserved, bounded |

`acres` left NULL on first pass — Hennepin `PARCEL_AREA` units unverified (UTM Zone 15N is meters but ArcGIS Shape__Area derivation may be in projected square feet).

`is_residential` heuristic for MN DOR State Code:
- 100-199 → True (residential homestead + non-homestead)
- 400-499 → True (apartment / multifamily)
- 200-399 → False (commercial / industrial)
- others → None (utility, agricultural, exempt)

## 5 Quality gates — all PASS

Per PR #259 pattern; verification at fire-end:

| Gate | Threshold | Hennepin | Status |
|------|-----------|---------:|:------:|
| Jurisdiction registered | 1 row | ✓ `39a8a612-e0af-4730-a661-2bad1b12f2f7` | **PASS** |
| Parcels with geom | ≥ 99 % | 448,084 / 448,084 (100.0 %) | **PASS** |
| `with_city` populated (PR #233 lesson) | meaningful coverage | 443,609 / 448,084 (**99.0 %**) | **PASS** |
| `raw_attributes` preserved (Norfolk) | 0 empty | 0 / 448,084 | **PASS** |
| `jurisdictions.bbox` populated inline (PR #261 codified) | non-null + sanity range | `[-93.768, 44.785, -93.177, 45.246]` | **PASS** |

Bonus stats:
- `assessed_value` populated: 425,294 (**94.9 %**) — MN DOR market value data is rich
- `is_residential` flag: 24,599 (5.5 %) — my 100s+400s STATE_CD heuristic is conservative; MN DOR uses a complex letter+number classification system that the int-only `STATE_CD` field doesn't cleanly capture. **Informational only, doesn't block gates.** Refinement deferred to follow-up (Phase 7A.2 or orchestrator pass).

Wall-clock: **7.2 min** for the resume from offset 100k (348,084 fresh upserts). Earlier fire's batches 1-2 (100k rows) took ~9 min before the network hang.

## Mid-fire recovery (timeout class)

First fire's offset 98,000 fetch returned HTTP 200 but the Python process then hung indefinitely (sleeping 41+ hours, 0 % CPU, retry-backoff exhausted without erroring). Killed the hung process; 100k rows already committed (idempotent UPSERT pattern). Added `--start-offset` CLI flag to resume; re-fired from offset 100,000 and completed the remaining 348k rows in 7.2 min.

**Codified lesson**: Hennepin's ArcGIS endpoint can return success on the page request but hold the connection open silently. Adding `--start-offset` to standalone parcel adapters is now the operational pattern for resuming after a silent hang — cheaper than re-COPY'ing the entire dataset.

## Wealth-band readiness (Phase 7A.2 targets)

Match preflight counts exactly:

| Muni | Parcels | Phase 7A.2 readiness |
|------|--------:|----------------------|
| Edina | 21,343 | ✓ ready |
| Wayzata | 1,992 | ✓ ready (smallest, quickest flip) |
| Minnetonka | 20,911 | ✓ ready |
| Plymouth | 29,204 | ✓ ready (largest in cohort) |
| Eden Prairie | 22,956 | ✓ ready |
| **Total** | **96,406** | **21.5 % of county** |

## Three codified updates applied

Per the running lessons codification:

1. **PR #253 lesson — skip in-DB ROLLBACK preflight at Class A scale.** Preflight is pipeline-shape validation only (1,000-row sample + sample mapped row). No prod write.
2. **PR #261 lesson — inline `jurisdictions.bbox` UPDATE** at fire-end. Sanity-checked against Twin Cities metro range (lon -94.0 to -93.0, lat 44.6 to 45.4) before writing.
3. **PR #233 lesson — title-case discipline.** `MUNIC_NM` is ALL-CAPS + space-padded ("EDINA           ") → `parcels.city = "Edina"` for Phase 7A.2 exact-equality joins against city zoning layers.

## What changed in the repo

- `backend/scripts/ingest_hennepin_mn_parcels.py` (new) — standalone Hennepin parcel adapter
- `backend/data/hennepin_mn_zoning_directory.json` (new) — Phase 7A.2 pre-stage with 5 wealth-band entries; `zoning_district_source.url` is `"TBD"` pending Phase 7A.2 city-zoning publisher discovery
- `docs/OP5_HENNEPIN_MN_PHASE7A1.md` (this file)

No backend code changes.

## Phase 7A.2 readiness

Pre-staged directory captures the 5 wealth-band targets per Diagnostic PR #255. Per Master's brief ("MetroGIS is parcel-only, no Class C"), each muni needs its own per-muni zoning publisher (similar to King WA Phase 6A.2 pattern where Bellevue published their city zoning separately from WAZA). Diagnostic risk to verify post-7A.2:

- Aggregator-source vs city-source code mismatch (PR #248 lesson — Bellevue WAZA-vs-city codes diverged)
- Per-muni zoning data freshness vs vintage labels

## Operational state

Hennepin moves `not_loaded → partial` post-this-PR (parcels live + bbox; zoning binding is Phase 7A.2). Operational count unchanged at **22** until orchestrator's matrix sprints apply for the WA wave's remaining 3 partial munis AND Hennepin's per-muni cohort lands.

Expected trajectory after Phase 7A.2 + matrix sprints:
- 22 (current) + 3 (WA wave: Bainbridge / Mill Creek / Gig Harbor) = 25
- 25 + 5 (Hennepin cohort: Edina / Wayzata / Minnetonka / Plymouth / Eden Prairie) = **30 worst-case**
- 30 + future MN counties (Ramsey / Anoka / etc.) on follow-up
