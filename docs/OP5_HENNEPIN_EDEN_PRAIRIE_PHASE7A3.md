# Op-5 Hennepin Eden Prairie Phase 7A.3 — city zoning Class A ingest

**Owner:** Lane A
**Date:** 2026-06-18
**Sprint type:** Phase 7A.3 — second of three parallel Hennepin per-muni zoning ingests (Plymouth + Eden Prairie + Minnetonka). Sibling of PR #295 Edina.
**Verdict:** **DB-LEVEL DONE. 5 / 5 quality gates PASS with 100.0 % `parcel_zoning_code_coverage_pct`.** Matches Edina's elite result. Eden Prairie flips operational once orchestrator's 28-row matrix sprint (commit `dfea670`) applies → count **26 → 27**.
**Predecessors:** PR #294 Phase 7A.2 (Eden Prairie jid `455b6dac-…` registered, 22,956 parcels moved) · PR #295 Edina Phase 7A.3 (sibling pattern).

---

## TL;DR

Eden Prairie publishes a parcel-density zoning layer at `gis.edenprairie.org/mapsb/.../Public/Zoning/MapServer/7` (City of Eden Prairie MN direct GIS). 19,818 features INSERTed as `zoning_districts` (out of 19,824 source features — 6 skipped due to degenerate rings, addressed via WKT-via-PostGIS pattern improvement). Spatial backfill bound **every Eden Prairie parcel** (22,891 contained + 65 nearest_50m = 22,956 / 22,956 = **100.0 %**).

## 5 / 5 Quality gates PASS

| Gate | Threshold | Eden Prairie | Status |
|------|-----------|--------:|:------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **100.0 %** (22,956 / 22,956) | **PASS** (+30 pp) |
| `nearest_*` share | < 30 % | **0.3 %** (65 / 22,956) | **PASS** (-29.7 pp) |
| `raw_attributes` preserved (Norfolk) | 0 empty | 0 / 19,818 | **PASS** |
| `zoning_district_count` | > 0 | 19,818 | **PASS** |
| `jurisdictions.bbox` populated inline (PR #261) | non-null + sanity range | `[-93.521, 44.799, -93.398, 44.892]` | **PASS** |

## WKT degenerate-ring skip — codified addition

First fire crashed at OBJECTID ~343 with PostGIS `geometry requires more points` error. Source has occasional degenerate rings (sliver geometry with <4 points). Patched `_rings_to_wkt` to skip rings with `len(r) < 4` (a valid polygon ring needs ≥4 points since first == last):

```python
def _rings_to_wkt(rings):
    ring_wkts = []
    for r in rings:
        if len(r) < 4:
            continue  # PR #285 + Eden Prairie addition
        coords = ", ".join(f"{p[0]} {p[1]}" for p in r)
        ring_wkts.append(f"(({coords}))")
    if not ring_wkts:
        raise ValueError("all rings degenerate")
    return "MULTIPOLYGON (" + ", ".join(ring_wkts) + ")"
```

6 features dropped (OBJECTID 19553-19555 etc.) — all small slivers; no spatial impact. Final: 19,818 districts INSERTed cleanly.

**Pattern carry**: this codification belongs in the per-muni adapter template for future waves (Maricopa, Fairfield, Oakland, Allegheny).

## 28 distinct codes (matches orchestrator pre-stage exactly)

Top by parcel binding:

| Code | Parcels | Share |
|------|--------:|------:|
| R1-13.5 | 8,578 | 37.4 % |
| RM-6.5 | 6,232 | 27.1 % |
| R1-9.5 | 3,005 | 13.1 % |
| R1-22 | 1,835 | 8.0 % |
| RM-2.5 | 1,739 | 7.6 % |
| P-PARK AND OPEN SPACE | 336 | 1.5 % |
| OFC | 212 | 0.9 % |
| C-REG-SER | 118 | 0.5 % |
| PUB | 69 | 0.3 % |
| GC | 49 | 0.2 % |
| **Please Call City 952-949-8485** | 36 | 0.2 % | ← "I-2"/"I-5"/"I-GEN" cleanup candidate placeholder |
| R1-44 | 18 | 0.1 % |
| C-REG | 14 | 0.1 % |

Note the "Please Call City 952-949-8485" code is the source's encoding for parcels Eden Prairie's GIS team handles manually (likely industrial / variance / nonconforming). 36 parcels = 0.2 %. Orchestrator's pre-stage covers I-2/I-5/I-GEN per Master's note; the substrate-first catchall handles the placeholder.

Industrial cleanup candidates (per Master's queue): Eden Prairie I-2/I-5/I-GEN — orchestrator pre-stage covers ~296 polygons.

## What's in the PR

- `backend/scripts/perm_muni_eden_prairie_zoning_ingest.py` (new) — Eden Prairie zoning adapter with degenerate-ring skip
- `docs/OP5_HENNEPIN_EDEN_PRAIRIE_PHASE7A3.md` (this file)

## Hard rules honored

- `raw_attributes` preserved (parcels' Phase 7A.1 rich raw + 6-key passthrough on zoning_districts)
- `municipality matches prod_city_value EXACTLY` — `parcels.city = 'Eden Prairie'` (Phase 7A.2 exact-count match)
- Inline `jurisdictions.bbox` UPDATE (PR #261)
- PR #285 Pierce Task E WKT-via-PostGIS pattern + degenerate-ring skip (this PR's contribution)
- Skip prod ROLLBACK preflight (PR #253)
- Don't author matrix — orchestrator's 28-row pre-stage (commit `dfea670`) applies separately
- Halt-and-report (0 HALTs)
- ONE refresh per phase (direct-python audit invocation per Mercer PR #278 pattern, since PR #280 still review-pending)

## Stack note

Branch is stacked on `adarench/op5-hennepin-mn-phase7a2` (PR #294). After PR #294 merges, this PR rebases trivially.

## Next dispatch

Per Master's sequencing:
1. Orchestrator applies 28-row matrix sprint via `_upload-matrix-rows` (~5-10 min Path A high confidence)
2. Audit recompute (direct-python) — Eden Prairie flips operational → **26 → 27**
3. **Plymouth Phase 7A.3** sibling (currently INSERTing in parallel)
4. **Minnetonka Phase 7A.3** Path B (ZoneCo "Proposed Zoning" + 4 ordinance codes)

Expected Hennepin wave close: Edina (26 ✓) + Plymouth (27) + Eden Prairie (28 — this PR) + Minnetonka (29) + Wayzata (deferred per PR #300 Diagnostic).
