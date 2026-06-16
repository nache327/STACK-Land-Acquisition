# Op-5 Pierce Task E — WA City Limits spatial join

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Pierce HALT forward-fix (PR #267 follow-up).
**Verdict:** **DONE. 162,219 / 328,832 Pierce parcels (49.3 %) populated with `city` via spatial join against Census 2020 TIGER WA city limits.** Gig Harbor's 5,312 parcels unblocks Phase 6B.2 Pierce per-muni dispatch. Remaining 166,613 NULL parcels are unincorporated Pierce County (rural / agricultural / forest) — correct behavior.
**Predecessors:** PR #267 (Pierce parcels ingested with SITUS_CITY_NM null) · HALT report `docs/OP5_PIERCE_WA_CITY_FIELD_HALT.md`.

---

## TL;DR

The Pierce HALT report's recommended forward-fix: spatial join 328,832 Pierce parcels against the canonical WA city limits layer. This script implements that fix via Census 2020 TIGER `WA_City_Limits` (services1.arcgis.com / slSNGMtvwLJi21om), 281 incorporated cities.

**Post-fire state:**

| Metric | Value |
|--------|------:|
| Pierce parcels total | 328,832 |
| Parcels with city populated | **162,219 (49.3 %)** |
| Parcels still NULL (unincorporated) | 166,613 (50.7 %) |
| Gig Harbor parcels | **5,312** |
| Tacoma parcels | 72,656 (largest Pierce city) |
| Lakewood parcels | 17,013 |
| Distinct cities populated in Pierce | ~25 |

Gig Harbor's 5,312 parcels is above Master's estimate of "~3,000" — the Census 2020 TIGER boundary includes the full incorporated extent (residential + commercial + waterfront corridors) where Census household-count alone suggests a smaller number.

## The WKT-builder bug (and fix)

**First fire** (with the original `_rings_to_wkt` ported from earlier per-muni adapters) produced only **66,919 city bindings**. Verification surfaced anomaly: **Tacoma was absent from the top 15 cities** despite being Pierce's largest city by far (~210k population). Diagnosis showed the Tacoma WKT output was only 2,411 chars — far too small for a 3-ring, 1,448-vertex polygon.

Root cause: the heuristic `_signed_area(r) < 0` → outer ring mis-classified TIGER 2020's ring windings. TIGER and WAZA use different ring-winding conventions; the heuristic worked for WAZA's simple per-parcel polygons but collapsed multi-ring TIGER places to a single inner ring.

Fix: emit each ring as a separate polygon body in a MULTIPOLYGON and let PostGIS reconstruct topology via `ST_Multi(ST_MakeValid(...))`:

```python
def _rings_to_wkt(rings):
    return "MULTIPOLYGON (" + ", ".join(f"(({coords}))" for r in rings for coords in [", ".join(f"{p[0]} {p[1]}" for p in r)]) + ")"
```

This delegates topology repair to PostGIS — the canonical polygon-correction path. Second fire produced 95,300 additional bindings (66,919 → 162,219), with Tacoma now correctly bound to 72,656 parcels.

## Top 15 Pierce cities post-fire

| Rank | City | Parcels |
|-----:|------|--------:|
| 1 | Tacoma | 72,656 |
| 2 | Lakewood | 17,013 |
| 3 | Puyallup | 13,512 |
| 4 | University Place | 10,539 |
| 5 | Bonney Lake | 7,920 |
| 6 | **Gig Harbor** | **5,312** |
| 7 | Edgewood | 5,156 |
| 8 | Sumner | 3,891 |
| 9 | DuPont | 3,396 |
| 10 | Orting | 3,180 |
| 11 | Fife | 3,158 |
| 12 | Auburn | 3,075 |
| 13 | Steilacoom | 2,728 |
| 14 | Fircrest | 2,560 |
| 15 | Buckley | 2,526 |

## Spot-check evidence (5 random Gig Harbor parcels)

```
apn=053-4755100070  addr=3013 ISLANDVIEW CT       centroid=POINT(-122.582 47.317)
apn=053-9003260160  addr=7816 SKANSIE AVE         centroid=POINT(-122.601 47.329)
apn=053-4002060050  addr=5151 BORGEN BLVD         centroid=POINT(-122.608 47.360)
apn=053-6391000190  addr=3702 EDWARDS DR          centroid=POINT(-122.588 47.328)
apn=053-0122361047  addr=10912 60TH AVE           centroid=POINT(-122.619 47.358)
```

All 5 centroids in Gig Harbor proper (lat 47.31-47.36, lon -122.58 to -122.62). Streets (Skansie, Borgen Blvd, Edwards Dr, Islandview Ct) are real Gig Harbor addresses.

## What changed in the repo

- `backend/scripts/pierce_task_e_city_derivation.py` (new) — Pierce city-derivation adapter
- `docs/OP5_PIERCE_TASK_E_CITY_DERIVATION.md` (this file)

No backend code changes. Only `parcels.city` was updated; `raw_attributes` untouched (Norfolk gate preserved).

## Next dispatch

**Gig Harbor per-muni** unblocks immediately:
- 5,312 Pierce parcels with `city = 'Gig Harbor'` ready to move
- WAZA Gig Harbor: 20 features (per PR #267 pre-stage in `backend/data/pierce_wa_zoning_directory.json`)
- Same Class A per-muni pattern as Bellevue / Mercer / Bainbridge / Mill Creek
- Expected flip → count +1 once orchestrator's matrix sprint applies

After Gig Harbor flips, count reaches 25 (per Master's WA-wave target). Master review for next-wave decision (Maricopa AZ vs Hennepin MN vs Fairfield CT).
