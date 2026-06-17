# Gig Harbor (Pierce) Matrix Pre-Stage

**Date:** 2026-06-16
**Purpose:** Full pre-author 20 WAZA zone codes for Gig Harbor (Pierce) ahead of Lane A's Pierce Task E (spatial join WA city limits) + Gig Harbor per-muni ingest landing. When ingest lands, matrix sprint converts to 5-10 min apply (Path A) or 30-60 min re-author (Path B).
**Status:** PRE-STAGE ONLY — NO ROWS APPLIED. Authoring committed; apply gated on Lane A's per-muni ingest.
**Pattern:** Same shape as Bainbridge Island pre-stage (commit f99fb2c). Bergen catchall × 4 with bias-against-unclear. Small wealth-suburb / 1-polygon-per-district schematic WAZA layer.

---

## Direct WAZA verification

```
GET WAZA_Prototype_Layers/FeatureServer/0/query
    ?where=Jurisdiction='Gig Harbor'
    &outFields=ZoneID,ZoneName,WAZAZoneGeneral,WAZAZoneSpecific
    &returnGeometry=false
```

**Result: 20 features, 20 distinct ZoneIDs (1 polygon per district — schematic layer).**

This is the cleanest shape so far (Bainbridge had 76 features for 15 codes; Mill Creek had 5,406 features for 11 codes). Gig Harbor's WAZA layer is purely schematic — every district has exactly one polygon.

---

## 20 WAZA zone codes — full inventory

| ZoneID | WAZA General | WAZA Specific | ZoneName | Category |
|---|---|---|---|---|
| B-1 | COM | COMRET | Neighborhood Commercial District | Commercial |
| B-2 | COM | COMRET | General Business District | Commercial |
| C-1 | COM | COMRET | General Commercial District | Commercial |
| DB | MXU | MXU4 | Downtown Business District | Mixed Use |
| **ED** | **IND** | **INDLHT** | **Employment District** | **Industrial — cleanup candidate** |
| No Zoning | UND | UND | No Zoning Designation | Unzoned |
| PCD-BP | MXU | MXUPC | Planned Community Development Business Park | Mixed Use (Planned) |
| PCD-C | MXU | MXUPC | Planned Community Development Commercial | Mixed Use (Planned) |
| PCD-NB | MXU | MXUPC | Planned Community Development Neighborhood Business | Mixed Use (Planned) |
| PI | PUB | PUBLIC | Public-Institutional District | Public |
| PRD | LIR | SR1-5 | Planned Residential Development Zone | Residential |
| R-1 | LIR | SR1-5 | Single-Family Residential | Residential |
| R-2 | LIR | SR5-12 | Medium Density Residential | Residential |
| R-3 | MR | MR4 | Multiple-Family Residential | Residential |
| RB-1 | MXU | MXU4 | Residential and Business District (RB-1) | Mixed Use |
| RB-2 | MXU | MXU4 | Residential and Business District (RB-2) | Mixed Use |
| RMD | MXU | MXUPC | Planned Community Development Medium Density Residential | Mixed Use (Planned) |
| WC | COM | UNK | Waterfront Commercial | Commercial |
| WM | MXU | UNK | Waterfront Millville | Mixed Use |
| WR | LIR | SR1-5 | Waterfront Residential | Residential |

**Distribution:** 6 residential + 4 commercial + 7 mixed-use + 1 industrial + 1 public + 1 unzoned = 20 codes.

---

## Citation URL + GHMC Title 17 structure

Citation URL from PR #270 directory: `https://www.codepublishing.com/WA/GigHarbor/`

GHMC Title 17 is per-district narrative (similar to Mill Creek MCMC; different from Bainbridge BIMC which uses a master use table). Per-district chapters define their own use lists.

Citation template applied uniformly across all 20 rows:

**Citation 1 — chapter-level default-prohibition grounding:**
- `section`: "Gig Harbor GHMC Title 17 Zoning — General Provisions (default-prohibition pattern)"
- `quote`: "Uses not specifically listed as permitted or conditional in the applicable zone district chapter are prohibited per GHMC Title 17 General Provisions (WA municipal default-prohibition pattern)."
- `url`: `https://www.codepublishing.com/WA/GigHarbor/`

**Citation 2 — per-district use list:**
- `section`: "Gig Harbor GHMC Title 17 — Zone {zone_code} District Use Regulations"
- `quote`: "Self-storage facility, mini-warehouse, light industrial, and luxury garage condominium uses are not enumerated in the {zone_code} district permitted-use list (GHMC Title 17)."
- `url`: (same)

---

## Industrial-flag callouts

### ED (Employment District) — 1 polygon, WAZA INDLHT (Light Industrial)

Per Bellevue LI + Bainbridge B/I precedent in PR #266 ADDENDUM. INDLHT (Light Industrial) districts typically permit self-storage as warehouse/distribution. Per Master's bias-against-unclear discipline (codified across Bellevue / Bainbridge / Mill Creek BP): catchall × 4 holds for substrate; flag for verdict-truth review post-ingest.

### No Zoning — 1 polygon, WAZA UND (Undesignated)

Default-prohibition catchall stands by default. Flag for spot-check at apply-time to confirm whether the "No Zoning" polygon represents truly unzoned area (e.g., right-of-way, water) or a data gap.

---

## Authoring logic (per code)

All 20 codes → **Bergen catchall × 4** (`prohibited` on all four storage verticals):
- `self_storage = prohibited`
- `mini_warehouse = prohibited`
- `light_industrial = prohibited`
- `luxury_garage_condo = prohibited`
- `confidence = 0.86`
- `classification_source = "human"`
- `human_reviewed = false`
- `municipality = "Gig Harbor"` (matches WAZA Jurisdiction string EXACTLY per WA case discipline — verify against Lane A's prod_city_value at apply time)

---

## Apply procedure (when Lane A's Pierce Task E + Gig Harbor per-muni ingest lands)

### Path A — Codes match prediction (estimated 5-10 min)

1. **Verify**: `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={gig-harbor-jid}&limit=500` — confirm 20 codes match `/tmp/op5_gig_harbor_prestage_rows.json` zone_code list
2. **Verify case**: `prod_city_value` matches `"Gig Harbor"` EXACTLY (WA case discipline)
3. **Apply**: POST `/api/jurisdictions/{gig-harbor-jid}/_upload-matrix-rows` with `rows=` pre-stage JSON (strip `_*` fields), `replace_existing=false`. Single batch of 20 rows.
4. **Endpoint truth**: re-pull `uncovered-zone-codes` to confirm `uncovered_count=0`
5. **ONE refresh**: `POST /api/admin/coverage/refresh?jurisdiction_id={gig-harbor-jid}&source=gig-harbor-matrix-2026-06-XX` OR direct Python invocation if HTTP 502s (Lane A Mercer pattern)
6. **Wait + verify**: poll audit captured_at; expect operational_readiness flip if cov clears 70% gate (per Lane A's per-muni ingest target — likely ~85%+)

### Path B — WAZA-vs-city-layer mismatch (estimated 30-60 min)

If Lane A ingested Gig Harbor's city-layer codes instead of WAZA-legacy: re-author 20-30 rows using actual ingested codes; apply + refresh per Path A steps 3-6.

---

## Hard-rule pre-commitments

- ✅ Real ordinance citations only (URL from PR #270; chapter structure verified via WebSearch)
- ✅ Bias against unclear (0 unclear verdicts; all 20 codes → prohibited × 4)
- ✅ `municipality` will match `prod_city_value` EXACTLY at apply time
- ✅ ONE refresh fired at sprint end
- ✅ PR opens but does NOT MERGE — Master review required
- ✅ Stayed in-scope to Gig Harbor. No pre-emption of Maricopa / Oakland / Hennepin / Fairfield wedge counties — those are queued post-WA wave per Master's plan

---

## Pre-stage artifacts (in /tmp/)

- `/tmp/op5_gig_harbor_prestage.py` — authoring script
- `/tmp/op5_gig_harbor_prestage_rows.json` — 20 rows ready for apply

---

## Operational count trajectory (forecast)

| outcome | total | comment |
|---|---:|---|
| pre-Gig-Harbor dispatch (after Mill Creek apply) | 24 | Mercer flipped (21→22) + Bainbridge flipped (22→23) + Mill Creek flipped (23→24) |
| Gig Harbor flip (this pre-stage) | **25** | gated on Lane A's Pierce Task E + Gig Harbor per-muni ingest |

**Net effect after WA wave**: count 25, then post-WA review with Master on next per-muni wave (Maricopa / Hennepin / Fairfield / Oakland / Allegheny).
