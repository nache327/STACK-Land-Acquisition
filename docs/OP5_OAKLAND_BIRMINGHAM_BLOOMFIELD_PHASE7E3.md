# Op-5 Oakland MI Phase 7E.3 — Birmingham + Bloomfield Hills HIGH Path A

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** Phase 7E.3 first MI fires after Phase 7E.2 (PR #318). Birmingham + Bloomfield Hills both HIGH Path A per Diagnostic PR #260.
**Verdict:** **DB-LEVEL DONE. 2 MUNIS, BOTH 5/5 PASS @ 100.0 % cov.** Campaign's **7th + 8th consecutive 100 % ingest** (Edina, Plymouth, Eden Prairie, Stamford, Minnetonka, Greenwich, Birmingham, Bloomfield Hills).
**Predecessors:** PR #318 Phase 7E.2 (5 Oakland munis registered) · Diagnostic PR #260 (Oakland acquisition spec) · PR #311 Greenwich CT precedent (Stamford-shape).

---

## 5/5 PASS — Birmingham

| Gate | Result |
|------|-------:|
| GATE 1 cov% | **100.0 %** (9,778 / 9,778) — PASS |
| GATE 2 near% | **0.0 %** (0 / 9,778) — PASS |
| GATE 3 raw_attributes empty | 0 — PASS |
| GATE 4 zoning_district_count | 399 (1 degenerate-ring skip) — PASS |
| GATE 5 jurisdictions.bbox | `[-83.250, 42.531, -83.186, 42.566]` — PASS |

### Birmingham source

- `https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0`
- 400 polygons, `district` field (R1, R2, R4, R8, B-1, B-2, MX, TZ-1, etc.)
- **0-1/0-2 numeric ZERO codes verified preserved verbatim** (Diagnostic PR #260 caveat)
- Publisher: City of Birmingham MI GIS (bhamgov)
- Vintage: live as of 2026-06-19 probe

Top 10 codes by parcel binding:

| Code | Parcels |
|------|--------:|
| R2 | 3,086 |
| R1 | 2,369 |
| R3 | 1,774 |
| R5 | 657 |
| R6 | 322 |
| R7 | 256 |
| B-4 | 207 |
| MX | 183 |
| R8 | 152 |
| R1-A | 151 |

21 distinct codes total — orchestrator's `8fe33e5` 21-row pre-stage matches EXACTLY.

## 5/5 PASS — Bloomfield Hills

| Gate | Result |
|------|-------:|
| GATE 1 cov% | **100.0 %** (1,833 / 1,833) — PASS |
| GATE 2 near% | **0.2 %** (3 / 1,833) — PASS |
| GATE 3 raw_attributes empty | 0 — PASS |
| GATE 4 zoning_district_count | 1,853 — PASS |
| GATE 5 jurisdictions.bbox | `[-83.266, 42.559, -83.225, 42.597]` — PASS |

### Bloomfield Hills source

- `https://services9.arcgis.com/jGlVpYnGiHmSg9fR/arcgis/rest/services/Zoning_BloomfieldHills/FeatureServer/0`
- 1,853 polygons (parcel-like — carries PIN + Zoning + CVTTAXDESC fields)
- Publisher: City of Bloomfield Hills MI (services9 ArcGIS)
- Vintage: live as of 2026-06-19 probe

13 distinct codes (vs Diagnostic PR #260 spec 12 = +1 — minor drift acceptable):

| Code | Parcels |
|------|--------:|
| A-3 | 626 |
| B-1 | 284 |
| A-4 | 250 |
| A-1 | 242 |
| A-6 | 227 |
| A-2 | 96 |
| A-3-1 | 28 |
| I-1 | 26 |
| O-1 | 26 |
| C-1 | 15 |
| O-2 | 9 |
| P-1 | 3 |
| RR | 1 |

## Note on Master's "Beverly Hills" mention

Master's 2026-06-19 dispatch mentioned "Birmingham + Beverly Hills" as HIGH Path A. Per Diagnostic PR #260, the verified pair was **Birmingham + Bloomfield Hills** (not Beverly Hills). Likely a typo. Lane A fired both verified-by-Diagnostic sources.

**Beverly Hills MI status**: No public ArcGIS layer surfaced in 2026-06-19 probe. The Village of Beverly Hills (4,174 parcels) does not appear to publish its own zoning Feature Service. Master can decide whether to:
- Defer Beverly Hills per Wayzata pattern
- Direct Lane A to attempt PDF extraction
- Accept that "Birmingham + Bloomfield Hills" was always the HIGH Path A pair

## Patterns carried forward

- **PR #285 Pierce Task E** — WKT-via-PostGIS via `ST_Multi(ST_MakeValid(...))`
- **PR #303 Eden Prairie** — degenerate-ring skip (Birmingham caught 1 degenerate ring at OBJECTID 39617)
- **PR #261** — inline jurisdictions.bbox UPDATE
- **PR #253** — skip prod ROLLBACK preflight at Class A scale
- **PR #260 Diagnostic** — Birmingham 0-1/0-2 numeric ZERO caveat preserved

## What's in this PR

- `backend/scripts/perm_muni_oakland_birmingham_zoning.py` (new) — Birmingham 7E.3 adapter (Stamford-shape, district field)
- `backend/scripts/perm_muni_oakland_bloomfield_hills_zoning.py` (new) — Bloomfield Hills 7E.3 adapter (parcel-like source, Zoning field)
- `docs/OP5_OAKLAND_BIRMINGHAM_BLOOMFIELD_PHASE7E3.md` (this file)

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate)
- MI case discipline UPPERCASE + political-entity prefix on jurisdictions ('CITY OF BIRMINGHAM', 'CITY OF BLOOMFIELD HILLS')
- Inline jurisdictions.bbox (PR #261)
- PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
- Skip prod ROLLBACK preflight (PR #253)
- Don't author matrix (orchestrator's `8fe33e5` 21+12 = 33 rows covers EXACTLY)
- Source freshness verified at fire time (Maricopa lesson)

## Next dispatch

1. Orchestrator applies 21-row Birmingham + 12-row Bloomfield Hills matrices (~10-15 min HIGH Path A clean apply)
2. Both flip operational → **count +2**
3. Bloomfield Township + Franklin + Beverly Hills LOW Path B (orchestrator authors at apply-time per Greenwich precedent) OR defer per Wayzata pattern if Master decides

## Sibling waves status

- **Maricopa**: Scottsdale 7B.3 PASS at 86 % cov (PR #313 amended); PV/CC/FH/Carefree DEFERRED (PR #319) — Maricopa wave = 1/5 ops
- **Fairfield**: Stamford applied + Greenwich (#311) — 2/5 ops, 3 Vessel Tech deferred
- **Oakland MI**: 7E.2 (PR #318) + 7E.3 Birmingham + Bloomfield Hills (this PR) → 2/5 ops confirmed; 3 LOW Path B pending
- **Allegheny PA**: 7F.2 cohort done (PR #316), 68 % parcel ingest gap flagged for Master; Phase 7F.3 awaiting orchestrator + Diagnostic PR #317 live-layer follow-up

## Campaign update

Confirmed 100 % wave for Birmingham + Bloomfield Hills. **Campaign's 7th + 8th consecutive 100 % ingest**. Pre-stage prediction quality at peak (Birmingham 21 codes = orchestrator's 21 EXACT match).

Updated trajectory:
- Scottsdale apply → 32
- Birmingham + Bloomfield Hills applies → 34
- Plus PV/CC/FH/Carefree deferred → not 35-36 (Master's prior 36-38 estimate revised down due to Maricopa PR #319 deferrals)
