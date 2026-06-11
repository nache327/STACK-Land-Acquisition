# Op-5 Montgomery PA spatial-backfill sprint — HALTED at pre-flight

**Owner:** Lane A
**Date:** 2026-06-11
**Sprint type:** Phase 2A free-win — fire existing `backfill_parcel_zoning_from_districts`
**Verdict:** **HALT — diagnosis was incomplete. Do not flip. No prod writes performed.**
**Predecessor:** `docs/INGESTION_PIPELINE_PLAN.md` (PR #214) — Class A claim was wrong for this county.

---

## Headline

The 54 `zoning_districts` rows loaded for Montgomery County, PA cover
**~1.2 % of the county by area** (centroid at -75.38, 40.13 — one
township in the eastern half of the county, ~5 mi × 3 mi window).
The remaining 98.8 % of the county has no district polygons to bind
parcels to.

A dry-run of the spatial-join logic against 1,000 sample unzoned
parcels returned **0 ST_Within matches**. Firing the production
backfill would have:

- in pure ST_Within mode: bound ~6,500 parcels (the ones inside the
  loaded township) — pushing coverage from 2.2 % → ~3.5 %, **far
  below the 70 % operational gate**;
- in `nearest_within_meters` fallback mode: bound the remaining
  ~98 % to whatever "nearest" district happens to sit hundreds of
  meters to miles away, **explicitly violating** the
  `zone_binding_method nearest_* > 30 %` quality gate I proposed
  in PR #214's risk register.

Either outcome would be operationally misleading. The sprint stops
here. Master decides whether to escalate to a county-wide
zoning-district acquisition ticket (Class B / D work in the
ingestion plan, not the Class A free-win I claimed).

---

## Pre-flight evidence (the load-bearing finding)

All numbers captured against prod 2026-06-11. No writes performed.

### Bounding-box overlap: districts vs parcels

| Layer | xmin | ymin | xmax | ymax |
|---|---:|---:|---:|---:|
| `zoning_districts` (54 rows) | -75.4242 | 40.1082 | -75.3445 | 40.1559 |
| `parcels` (301,424 rows) | -75.6975 | 39.9771 | -75.0150 | 40.4471 |

District bbox area / parcel bbox area = **0.0118 ≈ 1.2 %**. The
districts sit entirely *inside* the parcel bbox (no spatial-reference
mismatch — both layers are SRID 4326 and geometrically valid).

### Sample spatial-join dry-run

```sql
SELECT COUNT(*) FILTER (WHERE EXISTS (
  SELECT 1 FROM zoning_districts zd
   WHERE zd.jurisdiction_id = '<MP>'
     AND ST_Within(ST_Centroid(s.geom), zd.geom)
))
FROM (
  SELECT geom FROM parcels
   WHERE jurisdiction_id = '<MP>'
     AND (zoning_code IS NULL OR btrim(zoning_code) = '')
     AND geom IS NOT NULL
   LIMIT 1000
) s;
-- result: 0 / 1000
```

A broader `ST_Intersects` query (touches, not centroid-within) shows
~6,569 parcels overlap the district polygons across the whole county
— close to the **6,548** existing `parcel_with_zoning_code_count`,
suggesting the prior 2.2 % coverage came from the same one-time
ingest of this small area.

### Provenance of the 54 districts

`raw_attributes->>'Name'`, `->>'Districts'` patterns + bbox centroid
suggest the 54 rows came from a single PA township FeatureServer
ingest. Zone codes (R-A, R-1, R-2, R-3, RE, A, C, B-P, LC&I, I, RR,
L-C — 12 distinct) and the "RURAL RESIDENCE" / "RES. ESTATES"
language are consistent with a small township in the eastern part of
the county. The county-wide zoning layer was never ingested.

`zoning_districts.source = 'arcgis'`, `created_at = 2026-05-12` for
all 54. `ingest_zoning_districts` ran once on a partial source, not
on a county-aggregated layer.

---

## Pre-flight verification table (per dispatch §1)

| Check | Expected | Observed | Status |
|---|---|---|---|
| `zoning_district_count` | 54 | 54 | ✓ |
| `ST_IsValid(geom)` sample of 5 random districts (≥ 95 % valid) | ≥ 4 / 5 | **5 / 5 valid**, SRID 4326, vertex counts 7-361 | ✓ |
| Parcels with NULL `zoning_code` | ~295k | **294,876** | ✓ |
| `zone_class` NULL count | n/a | 294,876 (mirrors `zoning_code`) | ✓ |
| `centroid` NULL count | 0 | 0 | ✓ |
| **Dry-run ST_Within match rate (NEW gate)** | ≥ 50 % | **0 / 1,000 = 0 %** | **✗ HALT** |
| Districts cover % of county bbox | ≥ 50 % | **1.2 %** | **✗ HALT** |

The two ✗ rows are the load-bearing findings. Both are new checks not
in the dispatch's §1 list — surfaced because the canonical pre-flight
list didn't include "does the data actually overlap." That's a gap
in the Class A playbook, called out in the corrections section below.

---

## Before-state audit snapshot

`/tmp/montgomery_pa_before.json` (captured via
`GET /api/admin/coverage` 2026-06-11, since
`POST /api/admin/coverage/refresh` timed out at 90 s — separate
known behavior, see `docs/refresh_worker_diagnosis.md`; not a
blocker for this sprint).

```json
{
  "name": "Montgomery County, PA",
  "captured_at": "2026-05-12T20:51:13.358493+00:00",
  "parcels": 301424,
  "with_zoning_code": 6548,
  "zoning_pct": 2.2,
  "contained": null,
  "nearest": null,
  "districts": 54,
  "matrix": 0,
  "matrix_match_pct": null,
  "readiness": "partial",
  "gaps": [
    "no_zone_use_matrix",
    "no_matrix_matches_for_parcel_zones",
    "low_matrix_match_pct"
  ]
}
```

Note: `matrix: 0` in the API response vs `active matrix = 12` from
the direct DB probe — likely the snapshot is older than the matrix
rows. Either way, neither value is large enough to clear the gates.

---

## After-state

**No backfill was fired. No audit refresh fired. State is unchanged.**

`captured_at` on the public coverage snapshot remains
`2026-05-12T20:51:13.358493+00:00`. The 6,548 / 301,424 parcels with
`zoning_code` and 2.2 % coverage are the same as before.

---

## Quality-gate verdict (per the three gates I proposed in PR #214)

| Gate | Threshold | Status | Reason |
|---|---|---|---|
| `zone_binding_method` nearest_* share | ≤ 30 % of bound parcels | **WOULD FAIL** (~98 % if `nearest_within_meters` were enabled) | The contained-only path binds <3 %; the nearest fallback would bind nearly everything to wildly off-zone districts. |
| Per-muni minimum coverage (each top-N muni ≥ 70 %) | n/a — `parcels.city` is 0 % populated for this county | **CANNOT EVALUATE** | The Class B per-muni gate doesn't apply until `city` is populated. |
| Provenance receipt (`raw_attributes->source_url` + `ingested_at`) | populated | **PARTIAL** | `created_at` exists; `raw_attributes` shows source FID / Shape attrs but no source URL field. Acceptable for now, not flagged as a blocker. |

---

## Dispatch hard-rule compliance

| Rule | Status |
|---|---|
| No NEW code beyond the one-off invocation script | ✓ — `backend/scripts/backfill_montgomery_pa.py` committed with `DO NOT RUN` docstring; pre-flight failure means the script is staged for after county-wide districts are loaded. |
| Preview Supabase branch is the right place to validate before prod | n/a — workspace has no preview DATABASE_URL; the pre-flight halt occurred before any write would have been attempted. |
| One refresh after the backfill, not per-step | n/a — no backfill fired; no refresh fired. |
| Halt if anything looks wrong | ✓ — halted at pre-flight on the 0 / 1,000 ST_Within match. |
| Do not proceed to Phase 2B / 2C | ✓ — this sprint stops here. |

---

## Corrections to `docs/INGESTION_PIPELINE_PLAN.md` (PR #214)

The plan claimed Montgomery PA was Class A ("polygons loaded, not
bound") based on `zoning_district_count = 54`. That count was a
necessary but **insufficient** signal — the plan needed to also check
"do the polygons spatially cover the parcels?" before classifying
the county.

**Proposed plan corrections (Master to approve):**

1. Move Montgomery PA from Class A to Class B / D (per-municipality
   acquisition). It needs the same per-source adapter work as
   Westchester / Nassau / DuPage.
2. Add a new pre-flight check to the Class A definition: **district
   bbox area must cover ≥ 50 % of the parcel bbox AND a
   1,000-parcel ST_Within dry-run must return ≥ 50 % matches**
   before claiming Class A. Without this, Class A as defined is
   false-positive on partial-source ingests.
3. Re-tier the bucket: if any other county Master expected to be
   Class A had only a fraction of its polygons loaded, the same
   diagnosis applies. **Lane A recommends re-running the Class A
   sanity probe on every county with `zoning_district_count > 0
   AND zoning_code_coverage_pct < 70` before treating any of them
   as free wins.**

This isn't a contradiction of PR #214's overall pipeline shape —
the per-source adapter + directory design still holds. It's a
correction of the per-county tier assignment for Montgomery PA
specifically.

---

## What I would have done if pre-flight had passed

For Master's reference; the script `backend/scripts/backfill_montgomery_pa.py`
on this branch encodes this path exactly:

```python
async with async_session_maker() as db:
    updated = await backfill_parcel_zoning_from_districts(
        MONTGOMERY_PA_ID, db, fill_missing_zone_code=True
    )
    await db.commit()
print(f"updated {updated} parcels")
```

The admin-endpoint equivalent is
`POST /api/debug/fix-zoning/{jurisdiction_id}` (mounted at
`backend/app/api/debug.py:85` per `app.include_router(debug.router,
prefix='/api')` in `main.py:91`). Same in-process call.

After a successful run, the operator would then have fired
`POST /api/admin/coverage/refresh?jurisdiction_id=<MP>&source=phase2a-2026-06-11`
once, captured the after-state, and reported deltas.

None of this happened because the pre-flight halted.

---

## Recommended next dispatch (Master sign-off required)

Three options:

### Option A — drop Montgomery PA from the Phase 2 bucket entirely (cheapest)

Accept that the 54 districts are vestigial and Montgomery PA is
effectively Class D — needs full source acquisition. Defer until
Phase 2B (Fairfield CT) and 2C (Westchester) validate the adapter
pattern.

### Option B — minimum-effort first pass: backfill just the township the 54 districts cover

Run `backfill_parcel_zoning_from_districts` with the contained-only
path, accept the resulting ~6 k parcel coverage bump (2.2 → ~3.5 %),
and audit. **Will NOT flip Montgomery PA operational** (still far
below the 70 % gate), but does cleanly populate the one township
without lying via the nearest fallback.

Cost: ~30 minutes of operator time. Risk: very low — the bound
parcels would be honest "contained" bindings within a single
township's actual polygon set. Use case: validates that
`backfill_parcel_zoning_from_districts` itself works correctly on
prod when given valid input, separately from validating the
diagnosis.

### Option C — full county source acquisition (highest leverage, biggest cost)

Treat Montgomery PA as Class B (sometimes county zoning is published
per-municipality) or Class D (sometimes a single county-wide zoning
shapefile exists at `gis.montcopa.org`). Phase 2 first-action is a
1-hour catalog audit of MontCo GIS to determine the source-class
correctly before committing to scope. Estimated post-source-acquisition
work: matches the Westchester estimate of 8-12 h per muni × ~3 munis
to clear 70 %, or 6-10 h end-to-end if a county-wide layer exists.

Lane A recommends **Option A** as the immediate decision (the bucket
has cheaper wins in Fairfield CT / CT CAMA field-map). **Option C
would be the right follow-up once Phase 2B and 2C validate the
adapter pattern — but it's not a free win and shouldn't be sold as
one.**

---

## Artifacts

- `/tmp/montgomery_pa_before.json` — before-state coverage snapshot
  (captured 2026-06-11 from `GET /api/admin/coverage`; the upstream
  `captured_at` is the 2026-05-12 audit refresh, not today).
- `/tmp/coverage_now.json` — full fleet snapshot at the same time.
- `backend/scripts/backfill_montgomery_pa.py` — one-off invocation
  with `DO NOT RUN` guard, ready for Phase 2A-redux.
- No SQL writes, no audit refresh attempts succeeded, no schema
  changes, no extension installs.
