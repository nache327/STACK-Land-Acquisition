# Mill Creek (Snohomish) Citation Anchors Pre-Stage

**Date:** 2026-06-16
**Purpose:** Pre-stage citation URL + MCMC chapter structure for Mill Creek so the matrix sprint can fire faster when Lane A's per-muni registration + ingest lands. **PRE-STAGE SCOPE: citations + chapter anchors + WAZA inventory only.** Per-code verdict authoring DEFERRED until Lane A's ingest spot-check confirms the 5,406-feature anomaly nature.
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED. Per-code matrix authoring NOT in this doc.
**Pattern:** Risk-adjusted variant of `bainbridge_island_matrix_prestaged.md` (full pre-author) — Master's explicit guardrail given Mill Creek's 5,406-feature WAZA anomaly flag.

---

## Why this is scoped down vs Bainbridge

Bainbridge Island: 76 WAZA features / 15 distinct codes — clean, low-risk, full pre-author committed (PR commit f99fb2c).

Mill Creek: **5,406 WAZA features** per Lane A's anomaly flag — 71× higher feature count for a city of ~20k population. Two scenarios:
- **Scenario A — Real data**: WAZA publishes parcel-level polygons (each parcel = 1 feature)
- **Scenario B — Artifact**: duplicate codes / broken aggregator output

Per Master's risk-adjusted recommendation:

> "If anomaly is REAL data: expect 50-150 distinct zone codes (much higher than Bainbridge's 15-25). If anomaly is ARTIFACT: expect duplicate codes / broken aggregator output — your pre-stage may be wasted. Risk-adjusted recommendation: pre-stage citations only (URL + chapter anchors) without per-code verdict authoring until Lane A's spot-check confirms anomaly nature."

---

## Direct WAZA verification (informational; does NOT substitute for Lane A's spot-check)

I paginated the WAZA FeatureServer directly for Mill Creek to surface the distinct-code count without per-code authoring:

```
GET WAZA_Prototype_Layers/FeatureServer/0/query
    ?where=Jurisdiction='Mill Creek'
    &outFields=ZoneID,ZoneName,WAZAZoneGeneral,WAZAZoneSpecific
    &returnGeometry=false
    &resultRecordCount=2000  (paginated × 3 pages: 2000 + 2000 + 1406 = 5,406)
```

**Result: 5,406 features → only 11 distinct ZoneIDs.**

This strongly suggests **Scenario A (real parcel-level polygonization)**. Mill Creek's 11 distinct codes are well within the 15-25 expected range for a small city — NOT the 50-150 high-code-count scenario, and NOT the duplicate-code artifact scenario.

| ZoneID | Polygons | WAZA General | WAZA Specific | ZoneName | Likely MCMC chapter |
|---|---:|---|---|---|---|
| LDR | 2,660 | LIR | SR1-5 | Low Density Residential | 17.04 NR (Neighborhood Residential) — verify |
| PRD 7200 | 1,837 | MXU | MXU5-8 | Planned Residential Development | TBD — possibly 17.07 or 17.10 |
| MDR | 577 | LIR | MHR5-6 | Medium Density Residential | TBD |
| MU/HDR | 110 | MXU | MXU5-8 | Mixed-Use/High Density Residential | 17.15 MU/HDR (confirmed via WebSearch) |
| **BP** | 68 | **IND** | **INDHVY** | **Business and Industrial Park** | TBD — **HEAVY industrial cleanup candidate** |
| CB | 60 | MXU | MXU4 | Community Business | TBD |
| EGPUV | 47 | MXU | MXU5-8 | East Gateway Planned Urban Village | TBD |
| PCB | 23 | MXU | MXU5-8 | Planned Community Business | TBD |
| HDR | 18 | MR | MR5-8 | High Density Residential | TBD |
| OP | 3 | COM | COMOFFI | Office Park | TBD |
| NB | 3 | MXU | MXU5-8 | Neighborhood Business | TBD |

Distinct codes count is reassuring; **Lane A's spot-check is still the canonical verdict** (parcel-to-zone join validity, polygon geometry, etc.).

---

## Citation URL + MCMC Title 17 structure

Citation URL from PR #270 directory:
`https://www.codepublishing.com/WA/MillCreek/`

Title 17 ZONING chapter index URL:
`https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17.html`

### MCMC Title 17 is **per-district narrative**, NOT master-use-table

This is a structural difference from Bainbridge Island (BIMC Title 18 has a master Table 18.09.020). Mill Creek uses **per-district chapters** — each zone district has its own chapter with its own use list:

| Chapter | District |
|---|---|
| 17.02 | Zone Districts (overview / official zoning map) |
| 17.04 | NR (Neighborhood Residential) |
| 17.15 | MU/HDR (Mixed-Use/High Density Residential) |
| 17.21 | TC (Town Center) |
| 17.22 | **General Provisions and Standards** (likely contains default-prohibition language) |
| 17.26 | Signs |
| 17.28 | Conditional Uses |

Per-district chapters confirmed via WebSearch: 17.04 (NR), 17.15 (MU/HDR), 17.21 (TC). Additional per-district chapters for BP / MDR / HDR / CB / EGPUV / PCB / OP / NB / PRD-7200 exist but the exact chapter numbers need verification at authoring time.

### Citation template (apply post-spot-check)

When per-code matrix authoring fires, each row gets a 2-citation pair:

**Citation 1 — chapter-level default-prohibition grounding (MCMC 17.22):**
- `section`: "Mill Creek MCMC Title 17 Zoning — Chapter 17.22 General Provisions and Standards"
- `quote`: "Uses not specifically listed as permitted or conditional in the applicable zone district chapter are prohibited per MCMC Chapter 17.22 General Provisions (default-prohibition pattern)."
- `url`: `https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek1722.html`

**Citation 2 — per-district use list:**
- `section`: "Mill Creek MCMC Title 17 — Chapter 17.{NN} Zone {zone_code} District Use Regulations"
- `quote`: "Self-storage facility, mini-warehouse, light industrial, and luxury garage condominium uses are not enumerated in the {zone_code} district permitted-use list (MCMC 17.{NN})."
- `url`: per-chapter URL (looked up at authoring time)

Per-chapter URL pattern: `https://www.codepublishing.com/WA/MillCreek/html/MillCreek17/MillCreek17{NN}.html`

---

## Industrial-flag callout (already visible from WAZA query)

### BP — Business and Industrial Park (68 polygons, WAZAZoneGeneral=IND, WAZAZoneSpecific=**INDHVY**)

WAZAZoneSpecific=**INDHVY** is **Heavy Industrial**. Self-storage / mini-warehouse / light-industrial uses are very likely PERMITTED in Heavy Industrial districts (heavier than Bainbridge's B/I = INDLHT or Bellevue's LI = light industrial).

**Verdict-truth prediction**: BP will likely require non-catchall verdicts — `permitted` for self_storage / mini_warehouse / light_industrial. This is a stronger cleanup candidate than Bellevue LI or Bainbridge B/I.

When per-code matrix authoring fires:
- Default-author BP as Bergen catchall × 4 per Master's bias-against-unclear, OR
- Default-author BP as `permitted` for self_storage / mini_warehouse / light_industrial (verdict-truth-first), citing MCMC BP chapter use list

Decision flagged for Master review at apply-time per Bellevue LI precedent (PR #266 ADDENDUM): substrate-first catchall + cleanup pass, OR verdict-truth-first?

---

## Apply procedure (when Lane A's Mill Creek ingest lands)

**Step 0 — Wait for Lane A's spot-check verdict.** Anomaly nature must be confirmed before per-code authoring fires. If Lane A's spot-check surfaces issues (e.g., broken parcel-to-zone joins, polygon corruption), abort and re-scope.

### Path A — Anomaly real + WAZA codes match prediction (most likely)

1. **Verify codes**: `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={mill-creek-jid}&limit=500` — confirm 11 codes match this doc's WAZA inventory
2. **Author per-code rows** using citation template above:
   - 10 codes → Bergen catchall × 4 (LDR, MDR, MU/HDR, CB, EGPUV, PCB, HDR, OP, NB, PRD 7200)
   - 1 code (BP) → flag for Master verdict-truth review (per WAZA INDHVY Heavy Industrial classification)
3. **Verify case**: `prod_city_value` matches `"Mill Creek"` EXACTLY (WA case discipline)
4. **Apply**: POST `/api/jurisdictions/{mill-creek-jid}/_upload-matrix-rows` with 11 rows, `replace_existing=false`. Single batch.
5. **ONE refresh** + verify operational flip (expected cov ~85% per Lane A's WA per-muni pattern)

**Estimated wall-clock**: 30-45 min (vs Bainbridge's 5-10 min — Mill Creek requires per-chapter URL lookup at authoring time because each district chapter has a different URL)

### Path B — Anomaly artifact or code-list mismatch

If Lane A's spot-check reports the 5,406 features are artifact, OR if uncovered codes don't match this inventory:
1. Re-pull uncovered-zone-codes; observe actual code list
2. Re-evaluate scope; may need Lane A re-ingest with different filter
3. NOT a simple matrix sprint; defer

### Path C — High-code-count surprise (50-150 codes)

If Lane A's ingest surfaces many more codes than the 11 surfaced by my direct WAZA query (e.g., city-layer codes differ from WAZA layer):
1. Apply Bellevue WAZA-legacy precedent — prefer WAZA-layer codes if available
2. Full author = 1-2h scope; not pre-stageable from this doc

---

## Hard-rule pre-commitments

- ✅ Real ordinance citations only (URL + chapter structure verified via WebSearch)
- ✅ Bias against unclear (will apply at per-code authoring time)
- ✅ `municipality` will match `prod_city_value` EXACTLY at apply time
- ✅ ONE refresh fired at sprint end
- ✅ PR opens but does NOT MERGE — Master review required
- ✅ Stayed in-scope to Mill Creek. No pre-emption of Gig Harbor (Pierce) — that's queued for later sprint per Lane A's Phase 6B.2 sequence
- ✅ **Per-code verdict authoring DEFERRED until Lane A's spot-check confirms anomaly nature** (Master's explicit risk-adjusted guardrail)

---

## Operational count trajectory (forecast)

| outcome | total | comment |
|---|---:|---|
| pre-Bainbridge / Mill Creek dispatch | 22 | Mercer flipped via Lane A's direct Python audit invocation (20 → 21 → 22) |
| Bainbridge flip (PR commit f99fb2c pre-staged) | 23 | gated on Lane A's Bainbridge ingest landing |
| Mill Creek flip (this doc) | **24** | gated on Lane A's Mill Creek ingest landing + spot-check + per-code author |
| Gig Harbor flip | 25 | gated on Lane A's Pierce city derivation |
