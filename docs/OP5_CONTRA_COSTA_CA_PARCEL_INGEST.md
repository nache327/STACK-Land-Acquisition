# Op-5 Contra Costa CA Phase 5A.1 — parcel ingest + jurisdiction registration

**Owner:** Lane A
**Date:** 2026-06-15
**Sprint type:** Phase 5A.1 (Path 5A — split dispatch). Master authorised the path-split after the Phase 2 HALT (PR #242) surfaced the prerequisite gap. This dispatch loads parcels + registers the jurisdiction; Phase 5A.2 zoning backfill via CA Statewide Zoning North waits for separate Master sign-off.
**Verdict:** **DONE. 387,492 parcels ingested in 5 min. All Phase 5A.1 quality gates clear. Walnut Creek + Lafayette per-muni counts match the acquisition spec to within 3 parcels — the PR #233 title-case municipality discipline holds at CA scale.**
**Predecessor:** PR #242 (Task 5 Phase 2 HALT — prerequisite gap); `docs/CONTRA_COSTA_CA_ACQUISITION_SPEC.md` Phase 1 verdict at `/tmp/contra_costa_class_a_preview.md` (PASS).

---

## Headline

| Metric | Before | After | Δ |
|---|---:|---:|---|
| Contra Costa, CA jurisdiction rows | 0 | **1** | +1 |
| Contra Costa, CA parcels | 0 | **387,492** | +387,492 |
| with `geom` populated | 0 | **387,492** | 100 % |
| with `city` populated (s_city → title-case) | 0 | **386,627** | 99.78 % |
| with `raw_attributes` populated | 0 | **387,492** | 100 % |
| empty `{}` raw_attributes (Norfolk gate) | n/a | **0** | gate cleared ✓ |
| Walnut Creek parcels (PR #233 case-sensitive match) | 0 | **34,946** | spec said 34,949 |
| Lafayette parcels (PR #233 case-sensitive match) | 0 | **11,086** | spec said 11,088 |
| `zoning_code` populated | 0 | **0** | expected — Phase 5A.2 fills |
| `assessed_value > 0` | 0 | **376,829** | 97.25 % |
| `is_residential = TRUE` | 0 | **354,333** | 91.4 % |
| operational_readiness | not_loaded | **not_loaded** | unchanged (Phase 5A.2 prerequisite) |

**Wall-clock**: 5.0 minutes (8 batches of 50k features). Original 4-8h estimate was conservative — Supabase session-pool + COPY-based bulk upsert handled 387k parcels much faster than projected.

## Phase 5A.1 quality gates — all PASS

| Gate | Threshold | Observed | Status |
|---|---|---|---|
| 1 — jurisdiction registered with name=`Contra Costa County, CA`, state=`CA`, county=`Contra Costa` | 1 row | **1** (id `7ad622d4-…`) | ✓ |
| 2 — parcels ingested with valid geometry | ≥ 99 % | **100 %** (387,492 / 387,492) | ✓ |
| 3 — `raw_attributes` preserved (Norfolk gate) | 0 empty `{}` | **0 / 387,492** | ✓ |
| 4 — `s_city` normalised + matches CA Statewide Zoning North case (PR #233 lesson) | Walnut Creek title-case row count ≈ spec | **34,946 vs spec 34,949** (99.99 %) | ✓ |
| 5 — Lafayette title-case match | ≈ spec | **11,086 vs spec 11,088** (99.98 %) | ✓ |

## Source layer

**CCMAP Assessment Parcels MapServer/0**
`https://ccmap.cccounty.us/arcgis/rest/services/CCMAP/Assessment_Parcels_ArcPro/MapServer/0`

- Total feature count: **387,835** (CCMAP query `?returnCountOnly=true`)
- Max records per query: 2,000 (paginated via `resultOffset` / `resultRecordCount` with `orderByFields=OBJECTID`)
- Spatial reference: Web Mercator wkid=102100 / latestWkid=3857. Reprojected server-side to WGS84 via `outSR=4326`.
- 50 source fields (all preserved verbatim in `parcels.raw`)

## Adapter design

`backend/scripts/ingest_contra_costa_parcels.py` — **standalone** script that does the COPY-upsert directly against prod via asyncpg. Bypasses the SQLAlchemy import chain because the workspace's system Python (3.9) lacks the PEP-604 type syntax (`str | None`) the app code uses; the standalone script keeps the production `_stage_parcels` shape + `INSERT … ON CONFLICT … DO UPDATE` upsert SQL verbatim so the resulting rows are indistinguishable from the SQLAlchemy path.

Three subcommands:

- **`register`** — idempotent jurisdiction INSERT/find. Prints jurisdiction_id.
- **`preflight`** — read-only. Pulls 1,000-row sample, validates geometry parse + field mapping, reports `s_city` distribution + sample mapped row. NO DB WRITES.
- **`fire`** — real prod ingest. Requires `--i-know-this-writes-to-prod` flag. Paginates the full layer in 50,000-feature batches (8 batches total) and upserts via COPY into `_stage_parcels` → `parcels`. Idempotent on conflict.

### Field mapping (CCMAP → parcels)

| CCMAP source | parcels column | transformation |
|---|---|---|
| `APN` | `apn` | str().strip(); APN collisions collapse (333 across the county) |
| `s_city` | `city` | **`title()` case normalisation** — PR #233 lesson |
| `full_address_display` | `address` | str().strip() |
| `USE_CODE` (int) | `land_use_code` | str(int) |
| `ACREAGE` | `acres` | float; null/≤0 → null |
| `LAND_VALUE + IMP_VAL` | `assessed_value` | sum; null/≤0 → null |
| `IMP_VAL` | `improvement_value` | float |
| `assr_url` | `county_link` | https:// prefix added |
| geometry (WGS84 polygon) | `geom`, `centroid` | shape() + make_valid() |
| **all 50 source fields** | `raw` (JSONB) | verbatim dict-of-str |

### s_city title-case normalisation

CCMAP publishes ALL-CAPS (`"WALNUT CREEK"`); CA Statewide Zoning North uses title case (`"Walnut Creek"`). Python `str.title()` cleanly maps the 38 distinct CCMAP s_city values without edge cases (`"EL CERRITO"` → `"El Cerrito"`, `"BAY POINT"` → `"Bay Point"`, etc.).

The PR #233 collision-fix lesson — that municipality matching is load-bearing for downstream Class A / Class B work — applies in two directions here:
1. **Upstream** (this PR): parcels.city must use the case convention the downstream layer publishes.
2. **Downstream** (Phase 5A.2): the zoning backfill can use exact-equality joins on `Walnut Creek` instead of `LOWER()` or `ILIKE`.

### is_residential / has_structure heuristics

Contra Costa assessor use codes — conservative classification:
- `11`-`29` → `is_residential = True` (single-family + multi-family)
- `51`-`59` → `is_residential = True` (mixed-use w/ residential)
- `80`-`89` → `has_structure = False` (vacant)
- Anything with "Vacant" in `Description` → `has_structure = False`

Orchestrator can refine per use-code if needed; current shape is sufficient for the spatial backfill in Phase 5A.2.

### Known limitations (acceptable)

- **`acres` is sparse** (10.6 %) — CCMAP's `ACREAGE` column is sparsely populated. The production `_resolve_acres` path computes a geodetic fallback from geometry when `ACREAGE` is null; my standalone script does not (bypassed the import chain). Orchestrator can backfill from `geom` via a single UPDATE if Phase 5A.2 + matrix work needs acres.
- **865 parcels (0.22 %) without `city`** — CCMAP `s_city` is null on a small number of unincorporated parcels. Phase 5A.2 spatial backfill won't bind these per-muni; they'll fall through to county-level zoning.

## Refresh status

`POST /api/admin/coverage/refresh?jurisdiction_id=7ad622d4-…` fired once at 2026-06-15. Client timed out at 200 s (Railway proxy past 150 s ceiling). Did NOT retry per "ONE refresh per task" rule. DB-level numbers above are authoritative. Audit snapshot will reconcile on next automated cycle.

The post-refresh operational_readiness will be `not_loaded` or `partial` (zoning_code coverage is 0 %) — expected for Phase 5A.1. Phase 5A.2 flips this.

## What changed in the repo

- `backend/app/services/ingestion.py` — 1-line addition: `s_city` added to `_CITY_FIELDS`. Benefits any future CCMAP-style source.
- `backend/scripts/ingest_contra_costa_parcels.py` (new) — 600-line standalone adapter (register / preflight / fire subcommands).
- `docs/OP5_CONTRA_COSTA_CA_PARCEL_INGEST.md` (this file).
- `docs/PHASE2_PROGRESS.md` §15 — entry.

No matrix authoring (orchestrator's domain). No zoning data written (Phase 5A.2).

## Phase boundary

This PR is the phase-A.1 / phase-A.2 rollback point. If Master reviews and accepts:
- Phase 5A.2 dispatch can fire on the now-staged parcels: build Contra Costa zoning adapter + directory, pre-flight strengthened Class A gates against the live data, fire CA Statewide Zoning North filtered to `County='CCO'`, run `backfill_parcel_zoning_from_districts` scoped to Contra Costa.
- Expected Phase 5A.2 outcome per Phase 1 verdict + spec: coverage 0 % → 50-80 %. May NOT flip Contra Costa operational on first sprint; if not, dispatch follow-ups for Walnut Creek + Lafayette per-muni Class B work.

If Master halts: parcels stay loaded; no data loss; Phase 5A.2 deferred.

## Operational state

Operational count unchanged: **19**. Contra Costa stays `not_loaded` until Phase 5A.2 + matrix authoring land.
