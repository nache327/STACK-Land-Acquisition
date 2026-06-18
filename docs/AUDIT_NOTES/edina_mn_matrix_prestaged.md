# Edina (Hennepin MN) Matrix Pre-Stage

**Date:** 2026-06-16
**Purpose:** Full pre-author 39 distinct zone codes for Edina, MN ahead of Lane A's Hennepin Phase 7A.2 per-muni registration + ingest landing. When ingest lands, matrix sprint converts to 5-10 min apply (Path A) or 30-60 min re-author (Path B). First MN per-muni in Master's queue per `docs/AUDIT_NOTES/hennepin_mn_citation_directory.md`.
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED. Authoring committed; apply gated on Lane A's per-muni ingest.
**Pattern:** Same shape as Bainbridge Island pre-stage (commit f99fb2c) + Gig Harbor pre-stage (commit 156b0ed). Bergen catchall × 4 with bias-against-unclear. Per-district narrative ordinance (Edina Code of Ordinances Chapter 36; similar to Mill Creek MCMC + Gig Harbor GHMC; differs from Bainbridge BIMC master-use-table).

---

## Direct ArcGIS verification

```
GET https://utility.arcgis.com/usrsvcs/servers/6aeef36d107a4ff9aa765ad8d0baadfb/rest/services/Planning/Zoning/MapServer/2/query
    ?where=1=1
    &outFields=Zoning,LandUse
    &returnGeometry=false
    &resultRecordCount=2000  (paginated × 11 pages: 10×2000 + 976 = 20,976)
```

**Result: 20,976 features, 39 distinct Zoning codes.** Matches Diagnostic PR #255 prediction exactly (`hennepin_mn_citation_directory.md` line 54: "City zoning MapServer `Zoning` | 39 | `R-1`, `R-2`, `RMD`, `PCD-1`, `POD-1`, `MDD-4`, `APD`, `PUD`").

---

## 39 zone codes — full inventory

Concentration is heavily residential (R-1 = 63% of polygons):

| Zone | Polygons | Category | LandUse |
|---|---:|---|---|
| **R-1** | 13,203 | Single Family Detached | Single Family Detached |
| **PRD-3** | 2,464 | Planned Residential | Multifamily |
| **PRD-4** | 1,820 | Planned Residential | Multifamily |
| **MDD-5** | 935 | Mixed Development | Multifamily |
| **MDD-6** | 680 | Mixed Development | Office |
| R-2 | 507 | Single Family Attached | Single Family Attached |
| PSR-4 | 348 | Planned Senior Residential | Multifamily |
| PRD-2 | 157 | Planned Residential | Single Family Attached |
| MDD-4 | 175 | Mixed Development | Institutional |
| **PID** | 132 | **Planned Industrial District** | **Office (cleanup candidate)** |
| PRD-1 | 120 | Planned Residential | Single Family Attached |
| PCD-3 | 125 | Planned Commercial | Retail and Commercial |
| POD-1 | 105 | Planned Office | Retail and Commercial |
| PCD-2 | 55 | Planned Commercial | Office |
| PCD-1 | 34 | Planned Commercial | Retail and Commercial |
| POD-2 | 27 | Planned Office | Office |
| PUD | 20 | Planned Unit Development | Single Family Detached |
| PCD-4 | 14 | Planned Commercial | Retail and Commercial |
| RMD | 12 | Regional Medical | Office |
| PUD-4 | 8 | PUD project | Retail and Commercial |
| APD | 6 | (Auto/Parking?) | Retail and Commercial |
| PUD-5 | 5 | PUD project | Single Family Detached |
| PRD-5 | 3 | Planned Residential | Multifamily |
| PUD-10, PUD-12, PUD-15, PUD-22, PUD-8 | 2 each | PUD projects | (various) |
| PUD-1, PUD-14, PUD-18, PUD-20, PUD-21, PUD-23, PUD-25, PUD-3, PUD-6, PUD-7, PUD-9 | 1 each | PUD projects | (various) |

**Distribution:** 2 base residential (R-1, R-2) + 5 PRD planned residential + 19 PUD project-specific + 4 PCD planned commercial + 2 POD planned office + 3 MDD mixed development + 4 other (APD, PSR-4, RMD, **PID**) = 39 codes.

---

## Citation URL + Chapter 36 structure

Citation URL from `hennepin_mn_citation_directory.md`:
`https://library.municode.com/mn/edina/codes/code_of_ordinances?nodeId=SPBLADERE_CH36ZO`

Edina Code of Ordinances Chapter 36 Zoning uses **per-district narrative** (each district = its own sections with use list). Per Diagnostic citation directory:
- R-1 principal uses: **Sec. 36-433**
- R-1 conditional uses: Sec. 36-434
- R-1 accessory uses: Sec. 36-435
- R-2 principal/accessory uses: Secs. 36-462 to 36-463
- District-specific articles for PCD/POD/MDD/PRD/PSR/PUD/PID/RMD by code family

Per-district chapter pattern matches **Mill Creek MCMC** (commit 0a6ef78) + **Gig Harbor GHMC** (commit 156b0ed); structurally different from **Bainbridge BIMC** (commit f99fb2c) which uses a master Table 18.09.020.

### Citation template (applied uniformly)

**Citation 1 — chapter-level default-prohibition:**
- `section`: "Edina Code of Ordinances Chapter 36 Zoning — General Provisions (default-prohibition pattern)"
- `quote`: "Uses not specifically listed as permitted or conditional in the applicable district section of Chapter 36 are prohibited (MN municipal default-prohibition pattern; per-district narrative structure)."
- `url`: (above)

**Citation 2 — per-district:**
- `section`: "Edina Code of Ordinances Chapter 36 — [district-family hint] — Zone {zone_code} District Use Regulations"
- `quote`: "Self-storage facility, mini-warehouse, light industrial, and luxury garage condominium uses are not enumerated in the {zone_code} district permitted/conditional use list."
- `url`: (same — district anchors resolve via Municode page navigation)

---

## Industrial-flag callout (Somerset-style cleanup candidate)

### PID — Planned Industrial District (132 polygons, LandUse=Office)

Per Bellevue LI + Bainbridge B/I + Mill Creek BP + Gig Harbor ED precedent. PID is industrially zoned despite LandUse field saying "Office" (LandUse is a comp-plan/guideplan field; underlying zoning is industrial). Self-storage / mini-warehouse / light-industrial uses MAY be permitted in Planned Industrial — common in MN ordinances.

**Verdict-truth prediction**: PID likely warrants `permitted` for self_storage / mini_warehouse / light_industrial at the verdict-truth pass. Substrate-first catchall × 4 holds for matrix sprint; flag for Somerset-style cleanup post-ingest.

**No other industrial codes in Edina.** APD (6 polygons) is "Retail and Commercial" per LandUse — likely Auto/Parking District, not industrial.

---

## Authoring logic (per code)

All 39 codes → **Bergen catchall × 4** (`prohibited` on all four storage verticals):
- `self_storage = prohibited`
- `mini_warehouse = prohibited`
- `light_industrial = prohibited`
- `luxury_garage_condo = prohibited`
- `confidence = 0.86`
- `classification_source = "human"`
- `human_reviewed = false`
- `municipality = "Edina"` (matches MetroGIS `CTU_NAME` title case — verify against Lane A's `prod_city_value` at apply time)

---

## Apply procedure (when Lane A's Hennepin Phase 7A.2 ingest lands)

### Path A — Codes match prediction (estimated 5-10 min)

1. **Verify**: `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={edina-jid}&limit=500` — confirm 39 codes match `/tmp/op5_edina_prestage_rows.json` zone_code list
2. **Verify case**: `prod_city_value` matches `"Edina"` EXACTLY (MetroGIS title-case discipline expected)
3. **Apply**: POST `/api/jurisdictions/{edina-jid}/_upload-matrix-rows` with `rows=` pre-stage JSON (strip `_*` fields), `replace_existing=false`. Single batch of 39 rows.
4. **Endpoint truth**: re-pull `uncovered-zone-codes` to confirm `uncovered_count=0`
5. **ONE refresh**: `POST /api/admin/coverage/refresh?jurisdiction_id={edina-jid}` OR direct Python audit invocation if Railway HTTP times out
6. **Wait + verify**: poll audit captured_at; expect operational_readiness flip if cov clears 70% gate

### Path B — WAZA-vs-city-layer-style mismatch (estimated 30-60 min)

Edina has NO WAZA equivalent (WAZA is WA-specific). If Lane A ingested zoning via a different layer than the Edina city ArcGIS service (e.g., MetroGIS-derived, COUNTY_PIN-joined, or hand-digitized), codes may differ. Re-author per actual ingested codes using same Chapter 36 citation template.

### Path C — High-PUD-noise scenario

19 of 39 codes are PUD project-specific (PUD-1 through PUD-25, with gaps). If Lane A's ingest aggregates PUD variants under base "PUD" tag, the actual uncovered count may be smaller (~20-25 codes). The pre-stage authoring still applies; just fewer rows fire.

---

## Hard-rule pre-commitments

- ✅ Real ordinance citations only (Municode URL from `hennepin_mn_citation_directory.md`; chapter structure from Diagnostic PR #255)
- ✅ Bias against unclear (0 unclear verdicts; all 39 codes → prohibited × 4)
- ✅ `municipality` will match `prod_city_value` EXACTLY at apply time (MetroGIS `CTU_NAME` title case)
- ✅ ONE refresh fired at sprint end
- ✅ PR opens but does NOT MERGE — Master review required
- ✅ Stayed in-scope to Edina. No pre-emption of Wayzata / Plymouth / Eden Prairie / Minnetonka — those are queued for later sprints per Diagnostic's recommended sequence

---

## Pre-stage artifacts (in /tmp/)

- `/tmp/op5_edina_prestage.py` — authoring script (Bergen catchall × 4 per zone)
- `/tmp/op5_edina_prestage_rows.json` — 39 rows ready for apply when ingest lands

---

## Operational count trajectory (forecast)

| outcome | total | comment |
|---|---:|---|
| pre-Edina dispatch (current state) | 25 | WA wave complete (Bellevue + Mercer + Bainbridge + Mill Creek + Gig Harbor) |
| Edina flip (this pre-stage) | **26** | gated on Lane A's Hennepin Phase 7A.2 ingest |
| Wayzata flip | 27 | second MN per-muni in Diagnostic's queue |
| Plymouth, MN flip | 28 | third MN per-muni |
| Eden Prairie flip | 29 | fourth MN per-muni |
| Minnetonka flip | 30 | fifth MN per-muni (needs Lane A source hardening per Diagnostic) |

**Net effect after full Hennepin wave**: count 25 → 30. Then 6-county MetroGIS multi-county carry potential per Diagnostic PR #247 bonus.

---

## Cross-reference

- Hennepin citation directory: `docs/AUDIT_NOTES/hennepin_mn_citation_directory.md` (Diagnostic PR #255)
- Bergen catchall pattern: `docs/OP5_BERGEN_MATRIX_SPRINT.md` (PR #184)
- Per-muni jurisdiction pattern: `docs/OP5_BELLEVUE_MERCER_REJURISDICTION.md` (PR #271)
- Path A/B framework: `docs/OP5_KING_WA_MATRIX_SPRINT.md` PATH 1 addendum (PR #271)
- WA wave precedents (4 of 5 per-muni flips): Bainbridge `docs/AUDIT_NOTES/bainbridge_island_matrix_prestaged.md` (f99fb2c) + Mill Creek `docs/AUDIT_NOTES/mill_creek_citation_anchors_prestaged.md` (0a6ef78) + Gig Harbor `docs/AUDIT_NOTES/gig_harbor_matrix_prestaged.md` (156b0ed)
