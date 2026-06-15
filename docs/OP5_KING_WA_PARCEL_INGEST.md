# Op-5 King WA Phase 6A.1 — parcel ingest + jurisdiction registration

**Owner:** Lane A
**Date:** 2026-06-15
**Sprint type:** Tier 2 King WA (Phase 6A.1 — parcel ingest + jurisdiction registration). Master-authorized after Tier 1 (Contra Costa Phase 5A.2) landed.
**Verdict:** **DONE. 635,186 parcels ingested in 21.3 min. All Phase 6A.1 quality gates clear. Spec match exact at Bellevue (33,217/33,217) and Mercer Island (7,448/7,448) — the PR #233 title-case municipality discipline holds at WA scale. Multi-county Puget Sound carry confirmed: same adapter shape unlocks Pierce/Snohomish/Kitsap (797,786 additional parcels) and WAZA covers all 4 counties (86 jurisdictions).**
**Predecessor:** PR #253 (Contra Costa Phase 5A.2 — Class A pattern proved end-to-end); `docs/KING_WA_ACQUISITION_SPEC.md` Phase 1 verdict.

---

## Headline

| Metric | Before | After | Δ |
|---|---:|---:|---|
| King County, WA jurisdiction rows | 0 | **1** | +1 |
| King County, WA parcels | 0 | **635,186** | +635,186 |
| with `geom` populated | 0 | **635,186** | 100 % |
| with `city` populated (SITUS_CITY_NM → title case) | 0 | **573,140** | 90.2 % |
| with `raw_attributes` populated | 0 | **635,186** | 100 % |
| empty `{}` raw_attributes (Norfolk gate) | n/a | **0** | gate cleared ✓ |
| Bellevue parcels (PR #233 exact-case match) | 0 | **33,217** | matches spec **exactly** |
| Mercer Island parcels (PR #233 exact-case match) | 0 | **7,448** | matches spec **exactly** |
| `zoning_code` populated | 0 | **0** | expected — Phase 6A.2 fills |
| `assessed_value > 0` | 0 | **624,408** | 98.3 % |
| `is_residential = TRUE` | 0 | **549,540** | 86.5 % |
| operational_readiness | not_loaded | **not_loaded** | unchanged (Phase 6A.2 prerequisite) |

**Wall-clock**: 21.3 minutes — 13 batches of 50k features each. Per-batch breakdown: fetch ~45-75s (paginated 25 × 2k ArcGIS queries) + map ~1.5s + COPY-upsert ~25-65s.

## Quality gates — all PASS

| Gate | Threshold | Observed | Status |
|------|-----------|----------|--------|
| 1 — Jurisdiction registered | 1 row name=`King County, WA`, state=`WA`, county=`King` | ✓ `1e65c053-da54-4733-9d77-ca9aa3b27a7b` | ✓ |
| 2 — Parcels with geom | ≥ 99 % | **100 %** (635,186 / 635,186) | ✓ |
| 3 — `raw_attributes` preserved (Norfolk gate) | 0 empty `{}` | **0 / 635,186** | ✓ |
| 4 — PR #233 case-sensitive municipality matching | Bellevue + Mercer Island title-case match ≈ spec | **Bellevue 33,217 vs spec 33,217 (100.000 %)**; **Mercer Island 7,448 vs spec 7,448 (100.000 %)** | ✓ |

## PR #233 lesson — holds at WA scale, exact match

CCMAP `s_city` (CA) was ALL-CAPS; SITUS_CITY_NM (WA) is also ALL-CAPS. Python `str.title()` normalization at ingest produced:

| Source | Spec count | Prod count | Match |
|--------|----------:|-----------:|------:|
| Bellevue (`SITUS_CITY_NM='BELLEVUE'`) | 33,217 | **33,217** | 100.000 % |
| Mercer Island (`SITUS_CITY_NM='MERCER ISLAND'`) | 7,448 | **7,448** | 100.000 % |

Phase 6A.2 zoning backfill can use exact-equality joins (`parcels.city = 'Bellevue'` matches `zoning_districts.raw_attributes->>'Jurisdiction' = 'Bellevue'`) without `ILIKE` or `LOWER()`.

## Wealth-band carry (free at Phase 6A.2)

Per spec, the 57-list King WA wealth band is concentrated in 7 cities. All 7 appear in WAZA's `Jurisdiction` field and 6 of 7 populated cleanly in `parcels.city`:

| City | Parcels | Notes |
|---|---:|---|
| Bellevue | 33,217 | 57-list primary |
| Mercer Island | 7,448 | 57-list primary |
| Medina | 1,186 | Bill Gates's neighborhood |
| Clyde Hill | 1,049 | Eastside wealth |
| Yarrow Point | 255 | Eastside wealth |
| Hunts Point | 183 | Microsoft execs |
| Beaux Arts Village | 0 | Tiny (~300 residents); SITUS_CITY_NM may write under another label, or the small footprint is unincorporated for SITUS purposes. Phase 6A.2 can confirm via WAZA `Jurisdiction='Beaux Arts Village'` spatial lookup. |

**Total wealth-band parcels ready for Phase 6A.2 directory extension: 43,338** (6.83 % of King County, vs spec's "Bellevue + Mercer = 40,665 = 6.4 %"). Phase 6A.2 dispatch can extend the directory to all 7 cities at near-zero marginal cost — the WAZA layer covers each one.

## Multi-county Puget Sound carry (bonus probe)

The Washington Current Parcels statewide source covers all 4 Puget Sound counties under the same adapter shape:

| County | `COUNTY_NM` filter | Live count | WAZA features | WAZA jurisdictions |
|---|---|---:|---:|---:|
| King | `'33'` | **635,192** | 56,900 | 39 |
| Pierce | `'53'` | **339,590** | 19,116 | 22 |
| Snohomish | `'61'` | **318,594** | 34,705 | 20 |
| Kitsap | `'35'` | **139,602** | 15,606 | 5 |
| **Total** |  | **1,432,978** | **126,327** | **86** |

The same Phase 6A.1 adapter (just swap `COUNTY_NM` filter + new jurisdiction registration) unlocks **797,786 additional Puget Sound parcels** under one re-use. WAZA is the unified zoning substrate across all 4 — Phase 6A.2 lessons cascade. Documented for a future dispatch.

## Adapter design

`backend/scripts/ingest_king_wa_parcels.py` — standalone (clone of PR #250 Contra Costa pattern):

- Three subcommands: `register` / `preflight` (read-only pipeline shape check; no DB writes per PR #253 lesson) / `fire` (`--i-know-this-writes-to-prod`)
- Bypasses SQLAlchemy import chain (system Python 3.9 / PEP-604 incompatibility same as PR #250)
- Preserves prod `_stage_parcels` shape + `INSERT … ON CONFLICT … DO UPDATE` upsert SQL verbatim
- Idempotent via `uq_parcels_jurisdiction_apn` constraint

### Field mapping (Current_Parcels → parcels)

| Source field | parcels column | transformation |
|---|---|---|
| `PARCEL_ID_NR` (e.g. `033-9888000060`) | `apn` | str().strip(); statewide-unique |
| `SITUS_CITY_NM` | `city` | **`title()`** — PR #233 discipline |
| `SITUS_ADDRESS` | `address` | str().strip() |
| `LANDUSE_CD` (int) | `land_use_code` | str(int); WA DOR code, not zoning |
| `VALUE_LAND + VALUE_BLDG` | `assessed_value` | sum; null/≤0 → null |
| `VALUE_BLDG` | `improvement_value` | float |
| `VALUE_BLDG > 0` | `has_structure` | bool |
| `LANDUSE_CD` 11-29 | `is_residential` | True (single + multi-family) |
| `DATA_LINK` | `county_link` | https:// prefix added |
| geometry (server-side `outSR=4326` reprojection from EPSG:2927) | `geom`, `centroid` | shape() + make_valid() |
| **all 17 source fields** | `raw` (JSONB) | verbatim dict-of-str |

### Class-A-scale preflight pattern (PR #253 lesson applied)

Per Master's dispatch: "Class A scale lesson applied: skip prod-side preflight ROLLBACK (per your PR #253 finding); use Phase 1 shapely-only verdict as the substitute. Document this as the King-WA-specific preflight pattern."

This script's `preflight` subcommand is **read-only pipeline shape validation only**:
- Pulls 1,000-row sample
- Validates field mapping, geometry parse, title-case discipline
- Counts Bellevue / Mercer Island matches in the sample
- **NO DB WRITES**

For parcel-ingest dispatches, the in-DB preflight ROLLBACK that hung Phase 5A.2 (in-txn rows aren't in GiST → sequential scans) doesn't apply because parcel ingest doesn't run spatial gates against itself — it just COPY-upserts. Phase 1 spec verification + this lightweight pipeline check are the Class A preflight pattern going forward.

## Pre-flight sample (read-only validation)

```
features fetched : 1000
geom_skipped     : 0
apn_skipped      : 0
mappable rows    : 1000
raw_attributes field-count avg/min/max: 17.0 / 17 / 17

Distinct SITUS_CITY_NM (title-cased) in sample: 12
  Seattle                   661
  Kent                      152
  Burien                    70
  …
  Bellevue                  6
  Mercer Island             4

57-list target cities in 1k sample:
  Bellevue (title-case match): 6
  Mercer Island (title-case match): 4

Sample mapped row:
  apn                  = '033-9906000100'
  address              = '119 NW 41ST ST'
  city                 = 'Seattle'
  land_use_code        = '11'
  county_link          = 'https://blue.kingcounty.com/Assessor/eRealProperty/Dashboard.aspx?ParcelNbr=9906000100'
  has_structure        = True
  improvement_value    = 224000.0
  assessed_value       = 881000.0
  is_residential       = True
  raw                  = <17 keys: [...]>
```

## Refresh status

`POST /api/admin/coverage/refresh?jurisdiction_id=1e65c053-…` fired once at 2026-06-15. Client timed out at 200 s (Railway proxy past 150 s ceiling). Did NOT retry per "ONE refresh per task" rule. DB-level numbers in this doc are authoritative.

Post-refresh operational_readiness will be `not_loaded` (zoning_code coverage is 0 %) — expected for Phase 6A.1.

## What changed in the repo

- `backend/scripts/ingest_king_wa_parcels.py` (new) — standalone parcel adapter (~600 lines, 3 subcommands)
- `backend/data/king_wa_zoning_directory.json` (new) — Phase 6A.2 pre-stage with Bellevue + Mercer Island entries (WAZA primary, city zoning fallback per spec verdicts)
- `docs/OP5_KING_WA_PARCEL_INGEST.md` (this file)
- `docs/PHASE2_PROGRESS.md` §15 — 2026-06-15 entry

No backend code changes (the existing `_CITY_FIELDS` doesn't matter since the script is standalone, but the title-case normalization in `_map_row` honors the same discipline). No matrix authoring.

## Phase boundary

This PR is the phase-A.1 / phase-A.2 rollback point per Master's dispatch:

> "STOP at Phase 6A.1 PR opened for Master review BEFORE starting Phase 6A.2 (zoning backfill)."

If Master accepts → Phase 6A.2 dispatch can fire on staged parcels:
- Build Class A backfill adapter (WAZA primary + Bellevue / Mercer Island city zoning fallbacks per pre-staged directory)
- Special handling: PR #248 Diagnostic's Bellevue WAZA-vs-city-layer code mismatch (WAZA shows R-10/GC; current city shows LDR-2/MU-H). Lane A's adapter pulls from whichever layer the directory selects; doc the actual `parcels.zoning_code` values post-ingest.
- Same 4 quality gates as Westchester + Contra Costa
- ONE audit refresh

Expected per spec: King partial → operational on matrix sprint follow-on; +1 to operational count; +2 polygons (Bellevue + Mercer Island), and possibly +5 more (wealth-band) if the directory extends.

## Operational state

Operational count unchanged: **19**. King County stays `not_loaded` until Phase 6A.2 + matrix work land.
