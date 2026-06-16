# Op-5 Bainbridge Island per-muni registration (Phase 6B-PIVOT, third per-muni)

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** Phase 6B-PIVOT cohort — third per-muni after Bellevue (PR #271) and Mercer Island (PR #274 + PR #278).
**Verdict:** **DB-LEVEL DONE. Bainbridge is partial-with-zoning awaiting orchestrator's pre-staged 15-row matrix sprint.** Once matrix applies + audit re-runs, Bainbridge flips → count 22 → 23.
**Predecessors:** PR #267 (Phase 6B.1 Kitsap parcels) · PR #271 (Bellevue flip, pattern proof) · PR #274/#278 (Mercer flip + direct-python audit unblock).

---

## TL;DR

Bainbridge Island per-muni registration follows the Bellevue/Mercer pattern but with one structural difference: Kitsap County had no pre-existing WAZA zoning ingest, so this script runs the full sequence in one transaction:

1. Register new `Bainbridge Island, WA` jurisdiction
2. Move 9,796 parcels from `Kitsap County, WA` (jid `88a6b339-…`) → new Bainbridge jid
3. INSERT 76 WAZA zoning_districts under Bainbridge (`Mercer_Island_Planning_Layers` not used — Kitsap WAZA is the authoritative source)
4. 2-pass spatial backfill (`ST_Within` contained, then `ST_DWithin nearest_50m` fallback)
5. Inline `jurisdictions.bbox` UPDATE per PR #261 codified pattern
6. Direct-python audit recompute per Mercer PR #278 unblock pattern (since the prod HTTP refresh endpoint kept 502'ing pre-PR #280 fix)

**Bainbridge new jid:** `c6af2bd5-6ecb-4c4a-a9af-d51345c615c0`

## 5/5 Quality gates PASS

| Gate | Threshold | Bainbridge | Status |
|------|-----------|-----------:|:------:|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **70.9 %** (6,950 / 9,796) | **PASS** (+0.9 pp margin) |
| `nearest_*` share | < 30 % | **9.5 %** (930 / 9,796) | **PASS** (-20.5 pp margin) |
| `raw_attributes` preserved (Norfolk) | 0 empty `{}` | 0 / 76 | **PASS** |
| `zoning_district_count` | > 0 | 76 (matches WAZA feature count) | **PASS** |
| `jurisdictions.bbox` populated | non-null | `[-122.593, 47.574, -122.479, 47.722]` (inline) | **PASS** |

## Audit snapshot (post-fire)

```json
{
  "jurisdiction_id": "c6af2bd5-6ecb-4c4a-a9af-d51345c615c0",
  "captured_at": "2026-06-16T21:31:38.501783+00:00",
  "source": "manual-direct-python",
  "parcel_count": 9796,
  "parcel_with_zoning_code_count": 6950,
  "parcel_zoning_code_coverage_pct": 70.9,
  "zoning_district_count": 76,
  "matrix_zone_count": 0,
  "operational_readiness": "partial",
  "blocking_gaps": [
    "no_zone_use_matrix",
    "no_matrix_matches_for_parcel_zones",
    "low_matrix_match_pct"
  ]
}
```

All 3 blockers are matrix-related — orchestrator's pre-staged 15-row matrix sprint (PR `f99fb2c`) closes them in one apply.

## 15 distinct zone codes (matches orchestrator's pre-stage)

| Code | Parcels | ZoneName |
|------|--------:|----------|
| R-2 | 2,800 | Residential 2 du/ac |
| R-1 | 2,314 | Residential 1 du/ac |
| R-4.3 | 465 | Residential 4.3 du/ac |
| R-3.5 | 458 | Residential 3.5 du/ac |
| MUTC | 320 | Mixed-Use Town Center |
| R-2.9 | 126 | Residential 2.9 du/ac |
| R-8 | 107 | Residential 8 du/ac |
| HSR | 98 | High School Road |
| R-14 | 84 | Residential 14 du/ac |
| R-6 | 58 | Residential 6 du/ac |
| B/I | 32 | Business / Industrial |
| NC | 31 | Neighborhood Center |
| R-0.4 | 29 | Residential 0.4 du/ac |
| R-5 | 24 | Residential 5 du/ac |
| WD-I | 4 | Water-Dependent Industrial |
| **Total** | **6,950** | |

15 distinct codes match the orchestrator's pre-stage exactly (per Master's brief). Once matrix applies, **6,950 parcels (70.9 %) get matrix-matched in one sprint**.

## What changed in the repo

- `backend/scripts/perm_muni_bainbridge_island.py` (new) — combined re-jurisdictioning + WAZA Class A ingest adapter
- `docs/OP5_BAINBRIDGE_ISLAND_PERM_MUNI.md` (this file)

No backend code changes. No matrix authoring (orchestrator's domain).

## Direct-python audit recompute pattern (until PR #280 lands)

The HTTP refresh endpoint kept 502'ing on Bainbridge for ~15 min until I killed the process and re-ran via the direct-python pattern (per Mercer PR #278 + the audit-scoping fix in PR #280):

```python
# Python 3.12 venv with sqlalchemy[asyncio]+asyncpg+geoalchemy2+pydantic-settings
from app.db import async_session_maker
from app.services.coverage_audit import refresh_all_snapshots
async with async_session_maker() as db:
    result = await refresh_all_snapshots(
        db, jurisdiction_id=bainbridge_jid, source="manual-direct-python",
    )
    await db.commit()
```

After PR #280 (audit CTE scoping fix) merges, the HTTP refresh will work in seconds again. Until then, direct-python is the operational fallback.

## Next dispatch

Per Master's sequencing — Mill Creek per-muni fires immediately after Bainbridge PR opens (pre-authorized). The 5,406 WAZA feature anomaly is **verified real polygon-density** (5-feature spot-check: distinct OBJECTIDs, bounded polygons, parcel-shaped — 5,406 / 6,237 Mill Creek parcels = 0.87 polygons-per-parcel ratio). Mill Creek WAZA has 8 distinct ZoneIDs: LDR, MDR, HDR, OP, CB, MU/HDR, PRD 7200, EGPUV.

Expected trajectory:
- Bainbridge (this PR, partial) → operational after orchestrator's 15-row matrix → 23
- Mill Creek (next PR) → operational after orchestrator's matrix sprint → 24
- Pierce city-derivation (Task E) → unblocks Gig Harbor
- Gig Harbor → operational → 25
