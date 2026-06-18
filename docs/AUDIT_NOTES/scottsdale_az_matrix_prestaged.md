# Scottsdale (Maricopa AZ) Matrix Pre-Stage

**Date:** 2026-06-16
**Purpose:** Pre-author 249 distinct full_zoning codes for Scottsdale. First Maricopa AZ per-muni in chain. Largest single-muni pre-stage of campaign (~7× larger than Bellevue's 51, ~6× larger than Edina's 39).
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED.
**Pattern:** Master use table ordinance (Article XI Land Use Tables / Table 11.201.A — like Bainbridge BIMC + Wayzata Chapter 937). Bergen catchall × 4.

**⚠️ CASE-DISCIPLINE NOTE**: Maricopa County uses **UPPERCASE** `PropertyCity` values (per Diagnostic PR #262). `municipality = "SCOTTSDALE"` NOT "Scottsdale" — different from WA/MN title-case convention. Verify against Lane A's prod_city_value at apply time.

---

## Direct ArcGIS verification

```
GET https://maps.scottsdaleaz.gov/arcgis/rest/services/OpenData/MapServer/24/query
    ?where=1=1
    &outFields=full_zoning
    &returnGeometry=false
```

**Result: 1,937 features, 249 distinct full_zoning codes** — 4× larger than Diagnostic PR #262 predicted 40-70.

Reason for size: Scottsdale's `full_zoning` field includes overlay/suffix combinations (e.g., `C-2 ESL (HD)` = C-2 base + ESL overlay + HD historic preservation). Diagnostic PR #262 recommended preserving raw full_zoning as matrix key rather than collapsing to base district; this pre-stage follows that recommendation.

---

## Code distribution

| Category | Count |
|---|---:|
| Total distinct full_zoning codes | **249** |
| Distinct base districts | **67** |
| Base district only (no overlay) | 41 |
| With overlay/suffix combinations | 208 |
| Single-polygon codes (long tail) | 79 (32%) |
| 2-5 polygons | 84 |
| 6-20 polygons | 60 |
| >20 polygons (high-frequency base zones) | 26 |

### Top 10 base districts by variant count

| Base | Overlay variants |
|---|---:|
| C-2 | 11 |
| R1-35 | 11 |
| R1-18 | 10 |
| R1-43 | 10 |
| R1-7 | 9 |
| C-O | 9 |
| R-4R | 9 |
| S-R | 8 |
| R1-10 | 8 |
| R-5 | 8 |

### Top high-frequency codes

| Code | Polygons |
|---|---:|
| R-5 | 78 |
| R1-43 ESL | 59 |
| C-3 | 47 |
| HC ESL | 45 |
| S-R | 41 |
| R-4 PCD | 40 |
| R-4 | 39 |
| R1-18 ESL (HD) | 39 |
| C-2 | 37 |
| R1-7 PCD | 36 |

### Common overlay suffixes

- **ESL** — Environmentally Sensitive Lands overlay
- **(HD)** — Historic District designation
- **PCD** — Planned Community District
- **DO** — Downtown Overlay
- **HP** — Historic Preservation
- **(C)** — Conditional use approval
- **PNC** — Planned Neighborhood Center

---

## Industrial cleanup candidates flagged (7)

Per Bellevue LI / WA wave + Edina PID / Plymouth I-1/2/3 / Eden Prairie I-2/5/GEN precedent. All 7 industrial codes get substrate-first catchall × 4 with verdict-truth review flag:

| Code | Base | Polys | Overlay/Suffix |
|---|---|---:|---|
| I-1 | I-1 | (varies) | (none) |
| I-G | I-G | (varies) | (none) |
| I-1 ESL (HD) | I-1 | (varies) | ESL + HD |
| I-1 (C) | I-1 | (varies) | Conditional |
| I-G (C) | I-G | (varies) | Conditional |
| I-1 PCD | I-1 | (varies) | PCD |
| I-1 PCD ESL (HD) | I-1 | (varies) | PCD + ESL + HD |

---

## Citation pattern

URLs:
- Ordinance index: `https://www.scottsdaleaz.gov/codes-and-ordinances/zoning`
- Municode (Article XI Land Use Tables): `https://library.municode.com/az/scottsdale/codes/code_of_ordinances?nodeId=VOLII_APXBBAZOOR`

Citation pair grounded in **Table 11.201.A master use table** (Bainbridge BIMC + Wayzata Chapter 937-style pattern):
1. Article XI Land Use Tables / Table 11.201.A — default-prohibition framing
2. Per-zone-code district/overlay use regulations

---

## Apply procedure (when Lane A's Maricopa Phase 7B ingest lands)

### Path A — Lane A preserves raw full_zoning (per Diagnostic recommendation, expected ~5-10 min ÷ 249 codes batched)

1. **Verify**: Pull uncovered-zone-codes for Scottsdale jid; cross-reference vs 249-code pre-stage
2. **Verify case**: `prod_city_value` matches `"SCOTTSDALE"` UPPERCASE
3. **Apply**: 249 rows in 17 batches (15 rows each + final 4). Path A flow: ~10-15 min including batch coordination
4. **Endpoint truth**: uncovered_count → 0
5. **ONE refresh** or direct Python audit invocation

### Path B — Lane A collapses to base districts (~67 codes)

If Lane A's ingest normalizes full_zoning to base district (against Diagnostic recommendation):
- Filter pre-stage to base-only rows (41 of 249)
- Author additional rows for the 26 missing base districts (e.g., R-3, R-4R, R-5 etc.) using same template
- 30-45 min total

### Path C — Lane A surfaces some overlay codes but not all

Most likely outcome given uncertainty. Apply matching rows, defer non-matching to follow-up.

### Bbox prefilter concern

Per Diagnostic: "Scottsdale raw PropertyCity bbox failed 50% primitive — needs city-boundary prefilter". This is a **Lane A ingest concern**, not a matrix pre-stage concern. If Lane A's ingest ends up binding some non-Scottsdale parcels to Scottsdale jid (postal-city noise), the matrix substrate still applies because it's keyed by zone_code, not parcel city.

---

## Pre-stage artifacts

- `/tmp/op5_scottsdale_prestage.py`
- `/tmp/op5_scottsdale_prestage_rows.json` (249 rows ready)
- `/tmp/scottsdale_raw.json` (1,937 raw features from ArcGIS query)
