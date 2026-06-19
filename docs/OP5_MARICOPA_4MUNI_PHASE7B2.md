# Op-5 Maricopa 4-muni Phase 7B.2 — Scottsdale + Cave Creek + Fountain Hills + Carefree

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** Phase 7B.2 second batch after Paradise Valley (PR #310). Differentiated filter strategy per Master's 2026-06-19 dispatch — Scottsdale uses city-limits prefilter result (postal noise); CC/FH/Carefree use direct PropertyCity.
**Verdict:** **DB-LEVEL DONE. 4/4 munis registered.** 183,208 parcels moved (Scottsdale 147,886 + Cave Creek 16,521 + Fountain Hills 15,810 + Carefree 2,991).
**Predecessors:** PR #305 Phase 7B.1 (Maricopa parcel ingest) · PR #310 Phase 7B.2 PV · ingest_maricopa_az_city_limits.py prefilter run.

---

## 4-muni summary

| Muni | jid | Filter | Parcels | Bbox |
|------|-----|--------|--------:|------|
| Scottsdale, AZ | `8e31ce3a-67cd-4e62-b975-a4e799b59876` | `city='SCOTTSDALE'` (prefilter) | **147,886** | `[-111.995, 33.377, -111.467, 33.965]` |
| Cave Creek, AZ | `5b1227a1-ea7e-4f8a-b265-ac73c21dae2d` | `raw->>'PropertyCity'='CAVE CREEK'` | 16,521 | `[-112.138, 33.655, -111.822, 33.911]` |
| Fountain Hills, AZ | `666dc28d-a877-43bc-9763-06a100b4f89b` | `raw->>'PropertyCity'='FOUNTAIN HILLS'` | 15,810 | `[-111.787, 33.568, -111.588, 33.727]` |
| Carefree, AZ | `da313f75-af51-4e5e-b2fb-a315607fb383` | `raw->>'PropertyCity'='CAREFREE'` | 2,991 | `[-111.963, 33.799, -111.874, 33.857]` |

**Total moved**: 183,208. **Maricopa residual**: 1,505,615.

## Why differentiated filters

| Muni | Reason for filter choice |
|------|--------------------------|
| Scottsdale | PR #232 risk flagged Scottsdale's bbox FAILS Class A primitive due to postal-city noise. City-limits prefilter (Maricopa County `Reference/ParcelCityCounty/MapServer/1` — authoritative dissolved-by-CityName annexation source) resolves this. |
| Cave Creek | Master's call: <3% postal-vs-geographic delta. Direct PropertyCity (postal) accepted as proxy for incorporated boundary. |
| Fountain Hills | Same: <2% delta, direct PropertyCity. |
| Carefree | Master offered prefilter result (3,352) as alternative since Carefree GAINED 359 from prefilter (some non-CAREFREE-postal parcels actually within Carefree limits). Lane A chose direct PropertyCity (2,991) for cohort simplicity — delta is <12% of muni count, both interpretations are valid. |

## 5 / 5 gates PASS (per muni)

For all 4 munis:

| Gate | Status |
|------|:------:|
| Parcels moved match pre-move count | **PASS** (4/4 exact match) |
| `raw_attributes` preserved (Norfolk) | **PASS** (4/4, 0 empty) |
| `parcels.geom` non-null | **PASS** (4/4, 100 %) |
| `jurisdictions.bbox` populated inline (PR #261) | **PASS** (4/4) |
| Case-discipline UPPERCASE | **PASS** (SCOTTSDALE, CAVE CREEK, FOUNTAIN HILLS, CAREFREE) |

## Scottsdale parcel count note (147,886 vs spec 150,207)

Net -2,321 vs PR #232 spec. Attributable to:
- 44k random ingest gap from Maricopa GIS rate-limit 502 crash (Phase 7B.1, accepted per Master)
- ~2,000 parcels with raw='PARADISE VALLEY' but centroid in Scottsdale polygon — moved to PV jurisdiction by PR #310 (postal definition for PV won over geographic)

Net effect: 147,886 is the post-PV-move count. **Well above Master's 145k threshold** — gate PASS.

## Path A vs Path B per muni

- **Scottsdale**: HIGH Path A (orchestrator's 249-row pre-stage `20dacfc`)
- **Cave Creek**: LOW Path B (10 rows of orchestrator's 9af5827)
- **Fountain Hills**: LOW Path B (24 rows of orchestrator's 9af5827)
- **Carefree**: LOW Path B (8 rows of orchestrator's 9af5827)

Phase 7B.3 ingest:
- Scottsdale fires immediately via `perm_muni_scottsdale_zoning_ingest.py` (bundled in this PR — Stamford-shape adapter using full_zoning field from `maps.scottsdaleaz.gov/.../OpenData/MapServer/24`, 1,937 polygons)
- CC/FH/Carefree: orchestrator authors at apply-time from ordinance/PDF sources (Master's call — no Lane A polygon authoring required)

## What's in the PR

- `backend/scripts/perm_muni_maricopa_4muni_cohort.py` (new) — 4-muni cohort registration
- `backend/scripts/perm_muni_scottsdale_zoning_ingest.py` (new) — Scottsdale Phase 7B.3 adapter (fires after this PR's cohort committed)
- `docs/OP5_MARICOPA_4MUNI_PHASE7B2.md` (this file)

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate) — UPDATE touches jurisdiction_id + city + updated_at only
- UPPERCASE AZ case-discipline (per-muni city values)
- Inline jurisdictions.bbox per muni (PR #261 codified)
- Per-muni atomic transaction (insert + UPDATE + bbox in one tx)
- Skip ROLLBACK preflight at scale (PR #253)
- Don't author matrix (orchestrator's 20dacfc + 9af5827 pre-stages cover all 4)

## Next dispatch

1. **Scottsdale Phase 7B.3** — fires immediately via `perm_muni_scottsdale_zoning_ingest.py fire` (1,937 polygons, ~5 min wall-clock)
2. **CC/FH/Carefree applies** — orchestrator's 9af5827 pre-stage absorbs (LOW Path B re-author at apply-time)
3. **Scottsdale apply** — orchestrator's 249-row 20dacfc applies (HIGH Path A, ~10-15 min)
4. Expected: **+4 → count 31 → 35** (PV apply + 4 Maricopa applies)

## Sibling waves status

- **Maricopa**: PV (PR #310) + 4-muni (this PR) → 5/5 ops registered; Scottsdale 7B.3 firing next
- **Fairfield**: Stamford (PR #308 merged + applied) + Greenwich (PR #311 5/5) → 2/5 ops, 3 deferred to Vessel Tech bulk unlock
- **Oakland MI Wave 4**: parcel ingest firing in parallel (Phase 7E.1, 490k parcels, ~3-4h)
