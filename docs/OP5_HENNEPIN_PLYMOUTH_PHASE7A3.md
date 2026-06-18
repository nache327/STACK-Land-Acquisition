# Op-5 Hennepin Plymouth Phase 7A.3 — city zoning Class A ingest

**Owner:** Lane A
**Date:** 2026-06-18
**Sprint type:** Phase 7A.3 sibling of Edina (PR #295) + Eden Prairie (PR #303). Plymouth is the **largest** Hennepin per-muni cohort jurisdiction at 29,204 parcels.
**Verdict:** **DB-LEVEL DONE. 29,174 zoning_districts INSERTed under Plymouth jid `7cc5f175-…` from Plymouth city direct GIS.** Spatial backfill + bbox + gate verdict pending (process still firing at PR commit time). Plymouth flips operational once orchestrator's 24-row matrix sprint (commit `528a21d`) applies → count **27 → 28**.
**Predecessors:** PR #294 Phase 7A.2 (Plymouth jid registered, 29,204 parcels moved from Hennepin umbrella) · PR #295 Edina (sibling pattern) · PR #303 Eden Prairie (sibling, includes degenerate-ring skip codification).

---

## TL;DR

Plymouth publishes a parcel-density zoning layer at `plymap.plymouthmn.gov/webgis/rest/services/ParcelViewer/MapServer/2`. 29,366 source features → 29,174 zoning_districts INSERTed under Plymouth jurisdiction. Spatial backfill expected to bind 100 % via parcel-density `ST_Within` (Edina/Eden Prairie precedent).

## Source — City of Plymouth MN direct GIS

```
https://plymap.plymouthmn.gov/webgis/rest/services/ParcelViewer/MapServer/2
```

- Publisher: **City of Plymouth MN** (direct GIS via plymap.plymouthmn.gov)
- Layer: `Zoning` (parcel-density — one polygon per parcel)
- SR: HENNEPIN COUNTY custom projection (PROJCS) — server-side reprojected via `outSR=4326`
- maxRecordCount: 5000 (paginated at 1000)
- Code field: `ZONING` (authoritative current code)
- Cross-ref field: `PID` (joins back to Hennepin LAND_PROPERTY parcels)
- 12-key bounded raw_attributes passthrough

## Quality gates (verdict-pending at PR commit time)

| Gate | Threshold | Plymouth |
|------|-----------|--------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | (running — Edina/EP precedent: ~100 %) |
| `nearest_*` share | < 30 % | (running — parcel-density expected <1 %) |
| `raw_attributes` preserved (Norfolk) | 0 empty | (running) |
| `zoning_district_count` | > 0 | **29,174** ✓ |
| `jurisdictions.bbox` populated inline (PR #261) | non-null + range | (running — sanity range lon -93.55 to -93.39 lat 44.97 to 45.07) |

PR description will be amended with final 5-gate verdict once spatial backfill completes.

## WKT-via-PostGIS pattern carried forward

This adapter incorporates:
- **PR #285 Pierce Task E** — emit each ring as separate polygon body in MULTIPOLYGON, let PostGIS reconstruct topology via `ST_Multi(ST_MakeValid(...))`
- **PR #303 Eden Prairie** — skip degenerate rings (<4 points) to avoid PostGIS `geometry requires more points` error

24 expected codes per orchestrator's pre-stage (commit `528a21d`) — Plymouth is HIGH Path A confidence.

## What's in the PR

- `backend/scripts/perm_muni_plymouth_zoning_ingest.py` (new) — Plymouth zoning adapter (parcel-density source)
- `docs/OP5_HENNEPIN_PLYMOUTH_PHASE7A3.md` (this file)

## Hard rules honored

- raw_attributes preserved (Norfolk gate)
- municipality matches prod_city_value ('Plymouth')
- Inline jurisdictions.bbox (PR #261)
- PR #285 + PR #303 WKT-via-PostGIS + degenerate-ring skip
- Skip prod ROLLBACK preflight (PR #253)
- Don't author matrix (orchestrator's 24-row pre-stage covers)
- Halt-and-report
- ONE refresh per phase

## Stack note

Branch stacked on `adarench/op5-hennepin-mn-phase7a2` (PR #294). After PR #294 merges, this PR rebases trivially.

## Next dispatch

1. Spatial backfill completes (in flight at PR open time) — PR amended with 5-gate verdict
2. Orchestrator applies 24-row matrix sprint via `_upload-matrix-rows` (~5-10 min HIGH Path A)
3. Audit recompute (direct-python) — Plymouth flips operational → **27 → 28**
4. Sibling PRs status:
   - **PR #295 Edina** — flipped 25 → 26 confirmed (matrix applied 2026-06-18T22:32:13Z)
   - **PR #303 Eden Prairie** — 100 % cov, 5/5 PASS, awaiting orchestrator's 28-row apply
   - **Plymouth (this PR)** — awaiting spatial backfill verdict + orchestrator apply
5. **Minnetonka Phase 7A.3** dispatch (Path B mixed 10 ArcGIS + 4 ordinance per orchestrator)
6. **Wayzata** — Diagnostic PR #300 verdict: GeoPDF vector extraction needed, deferred to tooling dispatch
