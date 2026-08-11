# Op-5 Maricopa Paradise Valley Phase 7B.2 — direct PropertyCity registration

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** Phase 7B.2 first Maricopa per-muni fire after Phase 7B.1 (PR #305 MERGED). Differentiated strategy per Master's 2026-06-19 dispatch: direct PropertyCity for PV, city-limits prefilter for Scottsdale.
**Verdict:** **DB-LEVEL DONE. 5/5 quality gates PASS.** Paradise Valley, AZ registered as own jurisdiction `a79a7175-8e11-44a7-874d-5d9d79e53d99` with 9,847 parcels moved from Maricopa umbrella.
**Predecessors:** PR #305 Phase 7B.1 (Maricopa 1.7M parcels, 97.5% ingest) · PR #307 Fairfield Phase 7C.2 (per-muni cohort pattern) · PR #294 Hennepin Phase 7A.2.

---

## 5 / 5 Quality gates PASS

| Gate | Status |
|------|:------:|
| Parcels moved match expected (9,847) | **PASS** (9,847 — 0 drift from raw probe) |
| `raw_attributes` preserved (Norfolk) | **PASS** (0 empty) |
| `parcels.geom` non-null | **PASS** (9,847 / 9,847) |
| `jurisdictions.bbox` populated inline (PR #261) | **PASS** `[-112.013, 33.508, -111.920, 33.583]` |
| `city='PARADISE VALLEY'` consistency | **PASS** (9,847 / 9,847) |

bbox matches PR #232 spec exactly (spec: `[-112.013, 33.508, -111.920, 33.583]`).

## Why direct PropertyCity (not prefilter)

Per Master's 2026-06-19 dispatch: PV is incorporated, tiny enclave, trusted PropertyCity. Use raw `PropertyCity='PARADISE VALLEY'` filter; skip city-limits prefilter (which had reduced PV count from 9,847 to 7,857 by spatial-joining against Maricopa County's authoritative dissolved-by-CityName polygons).

**Field-level note**: My prior city-limits prefilter showed 1,990 PV-postal parcels had centroid OUTSIDE actual Paradise Valley city-limit polygon (likely East Phoenix sharing PARADISE VALLEY postal). Master's call accepted this as a definition-of-PV choice: use postal (raw PropertyCity) over geographic (actual annexation polygon).

The 1,990 parcels stay in Maricopa County umbrella with `city='PHOENIX'` (or whatever their centroid-derived city is) — not in PV jurisdiction.

## Filter + side-effect

```sql
UPDATE parcels
   SET jurisdiction_id = <new_jid>,
       city = 'PARADISE VALLEY',
       updated_at = NOW()
 WHERE jurisdiction_id = '<maricopa_jid>'
   AND raw->>'PropertyCity' = 'PARADISE VALLEY'
```

The `city = 'PARADISE VALLEY'` SET clause RESETS the city column on the 1,990 parcels the prefilter had UPDATEd to 'PHOENIX'. Net result: jurisdiction=PV + city='PARADISE VALLEY' for all 9,847 moved parcels. Consistent state.

## Patterns carried forward

- **PR #271 Bellevue** — PATH 1 transparent re-jurisdictioning (UPDATE jurisdiction_id)
- **PR #294 Hennepin Phase 7A.2** — per-muni atomic transaction (jurisdiction insert + parcel UPDATE + bbox in one tx)
- **PR #261** — inline jurisdictions.bbox UPDATE
- **PR #233** — case-discipline (UPPERCASE for AZ — 'PARADISE VALLEY' not 'Paradise Valley')
- **PR #305 Phase 7B.1** — Maricopa parcel ingest substrate

## What's in the PR

- `backend/scripts/perm_muni_maricopa_paradise_valley.py` (new) — PV-only cohort script using `raw->>'PropertyCity'` filter
- `docs/OP5_MARICOPA_PARADISE_VALLEY_PHASE7B2.md` (this file)

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate) — UPDATE touches jurisdiction_id + city + updated_at only
- UPPERCASE PARADISE VALLEY discipline (AZ codified)
- Inline jurisdictions.bbox (PR #261)
- Per-muni atomic transaction
- Skip ROLLBACK preflight at scale (PR #253)

## Next dispatch

1. Orchestrator applies PV 10-row pre-stage 9af5827 (LOW Path B ordinance) — ~30-60 min apply
2. PV flips operational → **count 30 → 31** (FIRST MARICOPA WAVE FLIP)
3. Scottsdale Phase 7B.2 fires next (uses city-limits prefilter result, 149,911 parcels)
4. Cave Creek + Fountain Hills + Carefree — PropertyCity probe + register
5. Phase 7B.3 Paradise Valley zoning ingest (Town of Paradise Valley `Planning_and_Zoning/MapServer/7`, ZONECLASS field, 427 nonblank rows)

## Sibling status (campaign 30 ops confirmed via orchestrator branch)

- **Hennepin wave**: 25 → 28 → 29 (Minnetonka applied per mercer-bainbridge-standby commit `4bd9c1e`)
- **Fairfield wave**: → 30 (Stamford applied per same commit)
- **Maricopa wave**: PV (this PR) firing first
- **Greenwich CT**: live ArcGIS Feature Server FOUND — Phase 7C.3 fires next (HIGH Path A, 285 polygons, 51 codes — Stamford-shape)
- **Westport / Darien / New Canaan CT**: token-gated SaaS (Vessel Technologies + Tighe-Bond + AxisGIS) — DEFER to Wayzata-style tooling sprint
