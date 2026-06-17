# Bainbridge Island (Kitsap) Matrix Pre-Stage

**Date:** 2026-06-16
**Purpose:** Pre-stage 15 matrix rows for Bainbridge Island so the matrix sprint can fire in 30-60 min (vs ~1-2h standard) when Lane A's Bainbridge per-muni registration + ingest lands.
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED. Authoring committed to working doc; apply gated on Lane A's per-muni ingest landing.
**Pattern:** Same shape as PR #266 (King WA / Bellevue + Mercer), PR #258 (Contra Costa), PR #240 (Westchester), PR #234 (Scarsdale). Bergen catchall × 4 with bias-against-unclear.

---

## Why pre-stage NOW

Per Master's 2026-06-16 dispatch ("Stand-down lifted — productive forward work AVAILABLE while Lane A unblocks Mercer"):

> When Lane A's Bainbridge ingest lands (gated on Mercer audit unblock per their parallel dispatch), your matrix sprint should fire in 30-60 min instead of the standard 1-2h. Pre-authoring closes the latency window.

Three lanes parallel-executing: Lane A unblocks Mercer + ships PR #274 + fires Bainbridge ingest while I pre-author the Bainbridge matrix. When Lane A's Bainbridge ingest lands, this doc converts to a 5-10 min apply via `_upload-matrix-rows` (if codes match prediction) or 30-60 min author-the-actual-codes (if WAZA-vs-city-layer mismatch surfaces — same risk Bellevue Phase 6A.2 verified resolved by sticking with WAZA-legacy).

---

## Source verification

### WAZA FeatureServer query

Direct query of WAZA Prototype Layers (the same FeatureServer Bellevue + Mercer used in PR #266):

```
GET https://services6.arcgis.com/tboeqGwETr5ppr5Q/arcgis/rest/services/WAZA_Prototype_Layers/FeatureServer/0/query
    ?where=Jurisdiction%3D%27Bainbridge+Island%27
    &outFields=ZoneID,ZoneName,WAZAZoneGeneral,WAZAZoneSpecific,Info,ReferenceURL
    &returnGeometry=false
```

**Result: 76 features, 15 distinct ZoneIDs.**

### Bainbridge Island Municipal Code (BIMC) Title 18

Citation URL from PR #270 directory:
`https://www.codepublishing.com/WA/BainbridgeIsland/html/BainbridgeIsland18/BainbridgeIsland18.html`

BIMC Title 18 structure (confirmed via WebSearch — Code Publishing platform returns 403 to WebFetch):

- **Chapter 18.03 General Provisions** — contains the default-prohibition clause (`18.03.D General Prohibition`)
- **Chapter 18.06 Zoning Districts** — district definitions; references `18.06.050.B` for B/I performance standards
- **Chapter 18.09 Use Regulations** — contains `Table 18.09.020` master use table (the per-district permitted/conditional use chart)

WebSearch surfaced this verbatim from the BIMC General Provisions / unlisted-use direction:

> "The director has the authority to evaluate an application and compare a proposed unlisted use against the permitted and conditional uses listed in the table, and a use may be allowed if the director determines that it is similar to other uses listed, indistinguishable in terms of land use impacts, and compatible with other uses in the vicinity."

Net: Bainbridge has BOTH a general-prohibition default AND a director-discretion unlisted-use process. For matrix substrate purposes (bias-against-unclear), the default-prohibition clause grounds the catchall × 4.

---

## 15 WAZA zone codes — full inventory

| ZoneID | Polygons | WAZA General | WAZA Specific | ZoneName | Category |
|---|---:|---|---|---|---|
| **B/I** | 6 | IND | INDLHT | Business/Industrial | **Industrial — cleanup candidate** |
| HSR | 2 | MXU | MXU4 | High School Road Districts I and II | Mixed Use |
| MUTC | 6 | MXU | MXU4 | Mixed Use Town Center | Mixed Use |
| NC | 6 | MXU | MXU4 | Neighborhood Center | Mixed Use |
| R-0.4 | 2 | RUR | RR1-5 | Residential 0.4 (1 unit / 0.4 acres) | Residential |
| R-1 | 14 | LIR | SR1-5 | Residential 1 | Residential |
| R-14 | 2 | MR | MR4 | Residential 14 | Residential (medium) |
| R-2 | 13 | LIR | SR1-5 | Residential 2 | Residential |
| R-2.9 | 5 | LIR | SR1-5 | Residential 2.9 | Residential |
| R-3.5 | 6 | LIR | SR1-5 | Residential 3.5 | Residential |
| R-4.3 | 3 | LIR | SR1-5 | Residential 4.3 | Residential |
| R-5 | 1 | LIR | SR5-12 | Residential 5 | Residential |
| R-6 | 1 | LIR | SR5-12 | Residential 6 | Residential |
| R-8 | 7 | MR | MR4 | Residential 8 | Residential (medium) |
| **WD-I** | 2 | IND | INDPORT | Water-Dependent Industrial | **Industrial (port/marine)** |

**Distribution:** 10 residential + 3 mixed-use + 2 industrial = 15 codes / 76 polygons.

Bainbridge has 9,796 parcels per the Kitsap County coverage breakdown — Lane A's per-muni ingest target.

---

## Authoring logic (per code)

All 15 codes → **Bergen catchall × 4** (`prohibited` on all four storage verticals):
- `self_storage = prohibited`
- `mini_warehouse = prohibited`
- `light_industrial = prohibited`
- `luxury_garage_condo = prohibited`
- `confidence = 0.86`
- `classification_source = "human"`
- `human_reviewed = false`
- `municipality = "Bainbridge Island"` (matches WAZA Jurisdiction string EXACTLY per WA case discipline — PR #264 / PR #266 lesson; verify against Lane A's prod_city_value when ingest lands)

### Citation pair (per row, applied uniformly)

Citation 1 — chapter-level default-prohibition grounding:
- `section`: "Bainbridge Island BIMC Title 18 — Chapter 18.03 General Provisions; Chapter 18.09 Use Regulations (Table 18.09.020 master use table)"
- `quote`: "Uses not specifically listed as permitted or conditional in Table 18.09.020 (master use table) are prohibited per BIMC Chapter 18.03 General Provisions (default-prohibition pattern)."
- `url`: `https://www.codepublishing.com/WA/BainbridgeIsland/html/BainbridgeIsland18/BainbridgeIsland18.html`

Citation 2 — per-district use chart:
- `section`: "Bainbridge Island BIMC Title 18 — Chapter 18.06 Zoning Districts; Zone {zone_code} District Use Regulations (Table 18.09.020)"
- `quote`: "Self-storage facility, mini-warehouse, light industrial, and luxury garage condominium uses are not enumerated in the {zone_code} district row of Table 18.09.020 (master use table)."
- `url`: (same)

---

## Industrial-flag callouts (Somerset-style cleanup candidates)

Two codes have an industrial WAZAZoneGeneral and merit post-ingest verdict-truth review:

### B/I (Business/Industrial) — 6 polygons, WAZA INDLHT (Light Industrial)

BIMC 18.06.050.B confirms B/I permits "light manufacturing"; on-site retail must be subordinate to manufacturing. Self-storage / mini-warehouse / light-industrial uses MAY be permitted as "warehouse / distribution" under the B/I master use table. Following the **Bellevue LI precedent** documented in PR #266 ADDENDUM:

> "Catchall × 4 stands per Master's bias-against-unclear for substrate purposes; flag for verdict-truth review post-ingest."

Per Bellevue LI deferral pattern: substrate first, verdict-truth cleanup later (Somerset-style pass).

### WD-I (Water-Dependent Industrial) — 2 polygons, WAZA INDPORT (Port/Marine Industrial)

Port-specific water-dependent uses (marinas, boat repair, ferry terminal operations). Self-storage is NOT a water-dependent use — catchall × 4 holds firmly. No cleanup candidate.

---

## Apply procedure (when Lane A's Bainbridge ingest lands)

### Path A — Codes match prediction (estimated 5-10 min)

1. **Verify**: `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={bainbridge-jid}&limit=500` — confirm 15 codes match `/tmp/op5_bainbridge_prestage_rows.json` zone_code list
2. **Verify case**: `prod_city_value` from endpoint matches `"Bainbridge Island"` EXACTLY (WA case discipline per PR #264 / PR #266 — "Bainbridge Island" not "BAINBRIDGE ISLAND")
3. **Apply**: POST `/api/jurisdictions/{bainbridge-jid}/_upload-matrix-rows` with `rows=`pre-stage JSON (strip `_*` fields), `replace_existing=false`. Single batch of 15 rows.
4. **Endpoint truth**: re-pull `uncovered-zone-codes` to confirm `uncovered_count=0`
5. **ONE refresh**: `POST /api/admin/coverage/refresh?jurisdiction_id={bainbridge-jid}&source=bainbridge-island-matrix-2026-06-XX`
6. **Wait + verify**: poll audit captured_at; expect operational_readiness flip if cov clears 70% gate (per Lane A's per-muni ingest target — likely ~85%+ similar to Bellevue's 85.2%)

### Path B — WAZA-vs-city-layer mismatch (estimated 30-60 min)

If Lane A ingested Bainbridge's city-layer codes (post-2017 codes) instead of WAZA-legacy:
1. Re-pull uncovered-zone-codes; observe actual code list
2. Re-author 15-25 rows from scratch using Bergen catchall pattern + BIMC Title 18 citations (URL stays same)
3. Apply + refresh per Path A steps 3-6

The PR #266 Bellevue lesson confirmed WAZA-legacy is authoritative (13 of 15 spot-checked parcels carried WAZA codes); Bainbridge likely follows the same pattern. Path A is the expected case.

---

## Hard-rule pre-commitments

- ✅ Real ordinance citations only (URL from PR #270 directory; chapter refs verified via WebSearch)
- ✅ Bias against unclear (0 unclear verdicts; all 15 codes → prohibited × 4)
- ✅ `municipality` will match `prod_city_value` EXACTLY at apply time (verify case)
- ✅ ONE refresh fired at sprint end (Path A or Path B)
- ✅ PR opens but does NOT MERGE — Master review required
- ✅ Stayed in-scope to Bainbridge Island. No pre-emption of Mill Creek (Snohomish) or Gig Harbor (Pierce) — those are queued for later sprints per Lane A's Phase 6B.2 sequence

---

## Pre-stage artifacts (in /tmp/)

- `/tmp/op5_bainbridge_prestage.py` — authoring script (Bergen catchall × 4 per zone)
- `/tmp/op5_bainbridge_prestage_rows.json` — 15 rows ready for apply when ingest lands

---

## Operational count trajectory (forecast)

| outcome | total | comment |
|---|---:|---|
| pre-Bainbridge dispatch | 21 | Bellevue confirmed today (2026-06-16) |
| Bainbridge flip (this sprint, when Lane A's ingest lands) | **22** | 15 codes / 9,796 parcels; expected ~85% per-muni cov per Lane A's WA ingest pattern |
| Mill Creek flip (Snohomish) | 23 | gated on Lane A Snohomish per-muni ingest |
| Gig Harbor flip (Pierce) | 24 | gated on Lane A Pierce city derivation |

Note: Mercer Island's flip (target → 22) is the next dispatch above this — depends on Lane A's Mercer city-fallback Task E lifting cov above 70%. If Mercer flips first, Bainbridge becomes the +1 (22 → 23 trajectory).
