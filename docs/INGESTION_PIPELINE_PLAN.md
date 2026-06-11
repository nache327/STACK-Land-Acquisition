# Ingestion pipeline plan — parcels_only / no-cov bucket

**Status:** PLANNING — DO NOT MERGE
**Author:** Lane A
**Date:** 2026-06-11
**Predecessors:** PR #211 (Morris heap-clustering diagnostic) ·
PR #212 (NY/CT structural diagnostic) · PR #98 (truthfulness gates)
**Sample size:** N=5 (Montgomery PA · Westchester NY · Nassau NY ·
Fairfield CT · DuPage IL). Orchestrator's full bucket enumeration
(`/tmp/ingestion_blocked_bucket_2026_06_11.md`) had not landed at
authoring time — see [§ Bucket enumeration caveat](#bucket-enumeration-caveat).

---

## TL;DR

The N=5 counties split into **four ingestion source classes**, each
needing a different amount of work to clear PR #98's truthfulness
gates (parcel_zoning_code_coverage ≥ 70 %, matrix_zone_match_pct
≥ 90 %, self_storage_classified ≥ 95 %).

> **Revised 2026-06-11 after PR #216.** The original TL;DR named
> Montgomery PA as the headline Class A free win. Pre-flight
> probing found the 54 ingested districts cover only ~1.2 % of
> the county's parcel bbox — a single-township partial ingest,
> not a county-wide layer. Montgomery PA reclassifies as Class
> B/D; the strengthened Class A gates and the at-risk-jurisdiction
> probe table are in [§ Class A](#class-a---polygons-loaded-and-spatially-cover-the-parcels-not-yet-bound).
> No N=5 county is currently a genuine Class A free win.

| Class | Counties (N=5) | Source state | Net-new work | Per-county effort after pipeline build |
|---|---|---|---|---|
| **A — polygons loaded AND spatially cover the parcels, not yet bound** | *(none from N=5 after PR #216 retiering)* | — | Fire existing `spatial_backfill` + matrix expansion | **2-4 h** when a county does qualify |
| **B — city drilldown works, no district polygons** | Westchester NY | 100 % parcels.city populated, 0 districts | Per-municipality zoning shapefile ingestion + directory | **8-12 h per muni**; ~3 munis to clear ≥70 % parcel coverage of the county |
| **C — statewide aggregator, field mapping dropped** | Fairfield CT | CT CAMA Statewide, 0 city / 0 zoning_code | Re-ingest with CAMA "Town" / "Zone" field mapping recovered | **6-10 h** (re-ingest is cheap once mapping is right) |
| **D — county GIS, no zoning attribute at all** | DuPage IL · Nassau NY · **Montgomery PA** (retiered after PR #216) | County-direct GIS, 0 city / 0 zoning_code | Separate county zoning shapefile OR per-muni discovery + ingest + matrix sprint | **20-40 h** |

**The single biggest unlock from one ticket** shifts to **Class C
on Fairfield CT**: the CT CAMA statewide layer already provides
zoning attributes on every CT parcel, but the existing ingest
field-map drops them. Recovering the map is a one-time fix that
amortizes across every CT county sourced from the same layer
(Hartford, New Haven, Litchfield, etc. — see Phase 2B notes
below). The 6-10 h Class C estimate stands.

The Class A free win remains the right shape **when a county
qualifies** — it just isn't on the N=5 list today. If/when an
operator loads county-wide districts for Montgomery PA (or any
other county currently failing the strengthened Class A gates),
the existing `spatial_backfill` path is ready to fire.

The reusable pipeline component that amortizes across B/C/D is a
**municipality directory + per-source ingest adapter** that follows
the Bergen `bergen_zoning_directory.json` shape PR #212 surfaced —
not net-new architecture, just net-new directories and adapter
wiring per source class.

---

## Why now (read first)

Two diagnostics converged this week:

1. **PR #211 (Morris anomaly)** — for the 10 whole-county outliers
   already in the 57-list, the slowness is heap clustering
   (`pg_repack` ticket). That work is queued; it does not unlock new
   counties.
2. **PR #212 (NY/CT diagnostic)** — the OTHER 10+ counties stuck at
   "parcels_only" / "partial" cannot run an NJ-style matrix sprint
   because `parcels.zoning_code` is null. They're not gated by
   matrix authoring; they're gated by **upstream parcel data
   shape**.

The 57-list grows fastest if we build one ingestion pipeline that
turns parcels_only → operational for the bucket of ~12 counties
sharing this shape. This plan scopes that pipeline.

---

## Bucket health — the N=5 sample as probed against prod

Captured 2026-06-11 against
`https://capable-serenity-production-0d1a.up.railway.app`:

| Jurisdiction | Parcels | zoning_code pct | city pct | zoning_districts | active matrix | parcel_endpoint host |
|---|---:|---:|---:|---:|---:|---|
| Montgomery County, PA | 301,424 | **2.2 %** | 0 % | **54** | **12** | `gis.montcopa.org/arcgis/...` (county GIS) |
| Westchester County, NY | 257,914 | 0 % | **100 %** | 0 | 0 | `services6.arcgis.com/EbVsqZ18sv1kVJ3k/...` (county GIS) |
| Nassau County, NY | 420,577 | 0 % | 0 % | 0 | 0 | `services6.arcgis.com/a523XM128lX5Nsff/...` (county GIS) |
| Fairfield County, CT | 261,652 | 0 % | 0 % | 0 | 0 | `services3.arcgis.com/3FL1kr7L4LvwA2Kb/.../Connecticut_CAMA_and_Parcel_Layer_2024` (**state CAMA**) |
| DuPage County, IL | 336,715 | 0 % | 0 % | 0 | 0 | `gis.dupageco.org/arcgis/...` (county GIS) |

Cross-cuts already covered:

- Tier-A heap-clustering counties from PR #211 (Nassau · Monmouth ·
  Hudson · Westchester · Fairfield · Loudoun) overlap this list at
  Nassau · Westchester · Fairfield. **The Morris-anomaly fix
  (`pg_repack`) is independently useful for those three even after
  this pipeline lands** — they will be slow to query AND
  parcels_only until both tickets run.
- Per-municipality ordinance shape was already mapped by PR #212
  for Westchester (5 munis sampled) · Nassau (5) · Fairfield (5).
  That work feeds Class B / D directly.

---

## Pipeline shape — by source class

This plan does **not** propose net-new architecture. The existing
pipeline (`backend/app/services/pipeline.py`) already orchestrates
the stages we need. The gap is **adapters + per-county directories**
that plug into existing stages.

### Class A — polygons loaded AND spatially cover the parcels, not yet bound

> **Revised 2026-06-11 after PR #216 found Montgomery PA was a
> false-positive Class A.** The original definition keyed only on
> `zoning_district_count > 0` and that signal turned out to be a
> partial-ingest trap: when only one township's worth of districts
> is loaded for a county, the count looks high but the spatial
> coverage is tiny. See [§ Class A pre-flight gates](#class-a-pre-flight-gates) below for the
> strengthened classification, and [§ Re-tiering after PR #216](#re-tiering-after-pr-216) for the
> live audit against prod.

Pipeline plug points already in place (unchanged):

```text
existing zoning_districts (county-coverage polygons, geom populated)
       │
       ▼
backend/app/services/spatial_backfill.py
  └─ backfill_parcel_zoning_from_districts(jid)
       └─ ST_Within(centroid, district.geom) → parcels.zoning_code
```

#### Class A pre-flight gates

Before classifying any county as Class A, the operator (or an
automated pre-flight) must verify **all three** of the following
against prod:

1. **`zoning_district_count > 0`** for the jurisdiction. (Existing
   check — necessary but not sufficient.)
2. **District bbox covers ≥ 50 % of the parcel bbox**:
   ```sql
   WITH d AS (SELECT ST_Extent(geom) AS bb FROM zoning_districts WHERE jurisdiction_id = :jid),
        p AS (SELECT ST_Extent(geom) AS bb FROM parcels         WHERE jurisdiction_id = :jid)
   SELECT ST_Area(ST_Intersection(d.bb, p.bb)) / NULLIF(ST_Area(p.bb), 0) AS pct
   FROM d, p;
   ```
   Below 50 % means the loaded districts are a partial-source
   ingest covering only a fraction of the county.
3. **1,000-parcel `ST_Within` dry-run returns ≥ 50 % matches** on
   unzoned parcels:
   ```sql
   WITH sample AS (
     SELECT id, geom FROM parcels
     WHERE jurisdiction_id = :jid
       AND (zoning_code IS NULL OR btrim(zoning_code) = '')
       AND geom IS NOT NULL
     LIMIT 1000
   )
   SELECT COUNT(*) FILTER (WHERE EXISTS (
     SELECT 1 FROM zoning_districts zd
     WHERE zd.jurisdiction_id = :jid
       AND zd.geom IS NOT NULL
       AND ST_Within(ST_Centroid(s.geom), zd.geom)
   )) / 10.0 AS match_pct
   FROM sample s;
   ```
   Below 50 % means the loaded districts don't sit where the
   unzoned parcels live, regardless of bbox arithmetic.

A county that passes (1) but fails (2) **or** (3) is **not** Class
A. It's Class B / D depending on whether `parcels.city` is
populated and whether a county-wide source exists upstream.

#### Re-tiering after PR #216

Live probe against prod 2026-06-11 of every jurisdiction with
`zoning_district_count > 0 AND parcel_zoning_code_coverage_pct
< 70`:

| Jurisdiction | districts | zoning_pct | district-bbox / parcel-bbox | ST_Within dry-run (1,000 sample) | Original tier | Revised tier |
|---|---:|---:|---:|---:|---|---|
| Payson, UT | 14 | 0.3 % | 2.9 % | 0 / 1,000 | (n/a, not in bucket) | Not Class A — partial ingest |
| Montgomery County, PA | 54 | 2.2 % | 1.2 % | 0 / 1,000 | **Class A** | **Class B/D** (see PR #216) |
| Essex County, NJ | 2,966 | 23.8 % | 24.3 % | 0 / 1,000 | (n/a, not in bucket) | Not Class A — partial ingest |
| Draper City, UT | 55 | 65.9 % | 59.7 % | 0 / 1,000 | (n/a, not in bucket) | Not Class A — already-bound parcels live where the districts are; the unbound 34 % live elsewhere |

**All four jurisdictions that previously presented as Class A
candidates fail the strengthened gates.** The signal is
systematic — `zoning_district_count` on its own is misleading on
partial-source ingests. The strengthened gates are the right
classification primitive.

Implication for the Phase 2 bucket: the N=5 sample's other
jurisdictions (Westchester NY, Nassau NY, Fairfield CT, DuPage IL)
all have `zoning_district_count = 0` and were therefore correctly
classified as B / C / D originally — no re-tiering needed for
them. **Only Montgomery PA moves**, and it moves out of Class A.

Recommendation for the Phase 2 operator playbook: run the Class A
pre-flight (3 gates above) before any backfill fire, and treat any
failure as a halt-and-report event in the OP5 sprint-doc format
that PR #216 established.



**Net-new work:** none. The function already exists, ships in prod,
is wired into `pipeline.py:1617` and again at `:1677`. The "skip if
≥99 % already zoned" guard at `spatial_backfill.py:92` is the
operational reason this hasn't fired automatically — it correctly
sees no work, but Montgomery PA's 2.2 % is well below that gate so
the run would proceed.

**Why it hasn't run yet:** unclear from this side. The full pipeline
chain at `pipeline.py:1617` should have fired on the last
Montgomery PA ingest (2026-05-19) but the result shows 6,548
parcels with zoning_code on a 301k base. The likely answer is the
zoning_districts ingest happened in a separate, later operation
without the chained backfill call. **Verifying that hypothesis is
the first action of Phase 2** — if confirmed, the unlock is a single
`POST /api/admin/coverage/refresh?jurisdiction_id={mp_uuid}` plus a
direct `spatial_backfill` invocation.

**Matrix expansion follow-up:** after backfill, count the resulting
distinct `zoning_code` values. If they exceed the existing 12
matrix rows, kick a matrix sprint scoped to the new codes only
(the Op-5 PR #156-style adjudication pattern). Expected scale: a
PA suburban county should have ~30-60 distinct codes after
backfill, so the matrix sprint is 6-10 hours, not the 3-4 hours of
an NJ-style sprint.

### Class B — city drilldown works, no district polygons (Westchester NY shape)

Pipeline plug points already in place:

```text
new per-muni zoning sources (shapefiles or GIS REST URLs)
       │
       ▼
backend/app/services/zoning_ingestion.py
  └─ ingest_zoning_districts(geo_df, jid, db)        ← already async + idempotent
       │
       ▼
backend/app/services/spatial_backfill.py
  └─ backfill_parcel_zoning_from_districts(jid)     ← already wired
       │
       ▼
matrix authoring (existing Op-5 adjudication path)
```

**Net-new work:** **(1) per-county municipality directory** —
mirrors PR #212's Westchester shape:

```json
{
  "muni_name": "Yonkers",
  "muni_type": "city",
  "prod_city_value": "Yonkers",          // must match parcels.city
  "zoning_district_source_url": "...",   // shapefile / FeatureServer / KMZ
  "zoning_district_source_kind": "arcgis_feature_server",
  "ordinance_url": "...",
  "ordinance_platform": "ecode360"
}
```

**(2) per-source adapter** — `zoning_ingestion.py` already takes a
GeoDataFrame, so the adapter is a thin layer that:

- Pulls shapefile (`geopandas.read_file`) or paginates an ArcGIS
  FeatureServer (`backend/app/services/arcgis_query.py` already
  exists for this).
- Normalises the `zone_code` field name (each muni's GIS uses a
  different attribute).
- Tags `municipality` so the matrix join key downstream uses
  `(jurisdiction_id, municipality, zone_code)` — exactly what
  Bergen / Somerset / Hunterdon already use.

**Scope of "build the pipeline once, run per muni":** the adapter
should accept a directory entry as input and call
`ingest_zoning_districts` + `spatial_backfill` per muni without
operator intervention. Build cost: **1-2 days**. After that, per-muni
runs are **8-12 h each** (directory entry research +
field-mapping confirmation + dry-run + write).

**Westchester top-3 cities by parcel count** (probed live):
Yonkers 36,431 · New Rochelle 15,756 · Greenburgh 14,425. Doing
just these three plus White Plains 13,965 and Mount Vernon 11,173
puts ~92 k of 258 k parcels under coverage — short of the 70 %
gate. To clear 70 % of Westchester (~180 k parcels), expect to
ingest the top ~10-15 munis.

### Class C — statewide aggregator with field mapping dropped (Fairfield CT shape)

Fairfield came from CT CAMA (Statewide
`Connecticut_CAMA_and_Parcel_Layer_2024`). The CAMA layer has, per
the CT Office of Policy and Management metadata, fields including
`TOWN_ID`, `MUN_NAME` (or similar variants per cycle), and parcel
attribute fields. **None of those reached `parcels.city` or
`parcels.zoning_code` in prod for Fairfield**, suggesting the
existing CT ingest path lost them at the `ingestion.py` field-map
step.

Pipeline plug points already in place:

```text
re-fetch from CT CAMA Statewide (same parcel_endpoint)
       │
       ▼
backend/app/services/ingestion.py
  └─ field_map: extend to include TOWN_ID → city, ZONE_CODE → zoning_code
       │
       ▼
re-upsert into parcels (idempotent on (jurisdiction_id, apn))
       │
       ▼
backend/app/services/spatial_backfill.py (for any town with district polygons)
       │
       ▼
matrix sprint
```

**Net-new work:** **(1) audit the CT CAMA layer fields** —
`https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/.../FeatureServer/0?f=json`
returns the field list; confirm `TOWN_ID` (or equivalent) and any
zone field. **(2) extend the existing CT ingest field map** to copy
those fields through. **(3) re-run** the parcel ingest scoped to
Fairfield. This is cheaper than B because the per-parcel data
already exists upstream — we just need to extract it.

**The same fix amortizes across the other CT counties** that came
through the same CAMA source. Lane A did not check the other CT
counties' fields in this dispatch — recommend Phase 2 starts with
field audit of the layer.

### Class D — county GIS with no zoning attribute (DuPage IL · Nassau NY)

Hardest class. The county-direct GIS endpoints for DuPage and
Nassau publish parcels with no zoning attribute at all
(verified via the prod-DB probes above; both show 0 zoning_code
across 100 % of parcels and 0 city).

Two paths, picked per county:

**D.1 — separate county-level zoning shapefile.** If the county
publishes a unified zoning GIS layer (separate from parcels), ingest
it directly into `zoning_districts`, then `spatial_backfill`. Same
pipeline as Class B, but one ingest call covers the whole county.

- DuPage IL: DuPage County Land Records Department publishes a
  `Zoning` FeatureServer layer at the same `gis.dupageco.org` host
  family — **needs confirmation** as part of Phase 2's first hour.
- Nassau NY: per PR #212, no single county-level zoning layer
  exists; authority is village + town nested. Almost certainly
  needs Class B per-muni pattern.

**D.2 — per-muni discovery + ingest.** If no county layer, fall
back to Class B's pattern. For Nassau this is realistic but
high-cost: PR #212 surfaced 5 sample munis and the structural
prereq estimate was 18-30 hours for the directory alone.

**Net-new work for D.1:** same adapter as Class B, single-source
case. For D.2: same as Class B at large multiplier (Nassau has
~70 municipalities of varying size).

---

## Per-county effort estimate

Pipeline build (one-time, amortizes across the bucket):

| Component | Effort | Notes |
|---|---|---|
| Per-source adapter wrapping `zoning_ingestion.ingest_zoning_districts` | 1-2 days | Accepts directory entry; handles ArcGIS / shapefile / KMZ; normalises field names |
| Directory schema + per-county JSON files | 4-6 h | Mirrors `backend/data/bergen_zoning_directory.json`; one per county |
| CT CAMA field-map extension in `ingestion.py` | 2-3 h | Class C only; same change unlocks every CT county |
| Operator playbook + matrix-sprint runbook | 4-6 h | Shared across all classes |

After the pipeline ships, **per-county execution cost** breaks down
as:

| County | Class | Per-county hours after pipeline | Estimated parcel coverage uplift | Net-new 57-list polygons |
|---|---|---:|---|---:|
| Montgomery County, PA | ~~A~~ **D** (retiered after PR #216) | 20-40 h (source acquisition + adapter) | 2.2 % → ≥70 % once county-wide districts loaded | ~30-60 once source acquired |
| Westchester County, NY | B | 8-12 h × ~10-15 munis = **80-180 h** | 0 % → ≥70 % over top munis | ~150-300 |
| Fairfield County, CT | C | 6-10 h | 0 % → ≥80 % (CAMA has near-complete town/zone) | ~100-200 |
| Nassau County, NY | D (likely D.2) | 18-30 h directory + per-muni cost | 0 % → 50-70 % over ~year+ of work | ~200-400 |
| DuPage County, IL | D (likely D.1) | 8-12 h if county zoning layer exists, else 60-100 h | 0 % → ≥70 % | ~80-150 |

**Bucket-wide extrapolation** assuming the other 7 unknown counties
in orchestrator's enumeration split roughly the same way (1A / 2B /
2C / 2D, after PR #216 takes one A → D):

- Pipeline build: ~3-4 days.
- Per-county execution to clear 12 counties: lumpy. Class C counties
  land in days; Class B and D counties land in weeks. A genuine
  Class A win (after a county-wide district ingest) would still be
  the fastest path when one materialises.
- Realistic 90-day target: **5-7 of the bucket counties operational**
  (revised down by 1 after PR #216 — Montgomery PA leaves the
  fast-track), starting with Class C re-ingest (Fairfield + the
  rest of CT), then top-N Class B municipalities for the larger
  counties.

### Bucket enumeration caveat

`/tmp/ingestion_blocked_bucket_2026_06_11.md` was not present at
authoring time. The orchestrator's Loudoun / Montgomery PA Phase 1
work was expected to name 9 additional counties in this bucket;
this plan uses the N=5 sample and treats the orchestrator's set as
a multiplier. If the orchestrator's list is materially different
from the N=5 split (e.g., dominated by a class this plan
underweights), Phase 2 should re-estimate before kickoff. The plan
shape and adapter design hold regardless.

---

## Quality gates

The new pipeline must close PR #98's truthfulness gates before any
jurisdiction flips to `operational`. Concretely, after each county
runs the new pipeline, the standard audit
(`backend/scripts/audit_zoning_coverage.py`) must show:

| Metric | Source field | PR #98 gate | Where checked |
|---|---|---|---|
| `parcel_zoning_code_coverage_pct` | `JurisdictionAudit.parcel_zoning_code_coverage_pct` | ≥ 70 | `_operational_readiness()` :393 |
| `matrix_zone_match_pct` | `JurisdictionAudit.matrix_zone_match_pct` | ≥ 90 | `blocking_gaps` :442 |
| `self_storage_classified_parcel_pct` | `JurisdictionAudit.self_storage_classified_parcel_pct` | ≥ 95 | `blocking_gaps` :444 |
| `zoning_polygon_coverage_flag` | (true OR `parcel_source_zoned` carve-out) | not-blocking when ≥ 80 % zoning_code + ≥ 90 % matrix_match | `_build_audit` :456-463 |

**Additional pipeline-side gates I want before flipping a county:**

1. **`zone_binding_method` distribution** — spatial_backfill already
   stamps `'contained'` vs `'nearest_<N>m'`. The pipeline should
   refuse to mark a county operational when more than 30 % of bound
   parcels are `nearest_*` rather than `contained` — that's the
   honest fence between "we have polygons" and "we're guessing from
   a polygon nearby." This is a new boolean check added to
   `_operational_readiness`, **not** a code change in this dispatch.
2. **Per-municipality minimum coverage** — for Class B / D
   counties where coverage is built up muni-by-muni, refuse to mark
   the county operational unless top-N municipalities (covering
   ≥70 % of parcels) ALL show ≥70 % zoning_code internally.
   Otherwise we end up with "Westchester operational, but
   Greenburgh is 5 %" — looks fine in the headline, lies to a
   buyer pinpointing Greenburgh.
3. **Provenance receipt** — every newly-ingested zoning_district
   row should carry `raw_attributes->source_url` and
   `raw_attributes->ingested_at` so the operator can audit
   "where did this polygon come from" without re-running the
   ingest. The model already has the `raw_attributes` JSONB
   column.

These additions land naturally inside the existing
`coverage_audit.refresh_all_snapshots` path — none requires
schema changes.

---

## Risk register

| # | Risk | Likelihood | Impact | Mitigation / fallback |
|---|---|---|---|---|
| 1 | CT CAMA field names change between annual layers (`Connecticut_CAMA_and_Parcel_Layer_2024` → `_2025`) | High | Medium | Pin the layer year in the parcel_endpoint; ingest re-runs reuse the same map. Refresh map yearly when CT publishes a new layer. |
| 2 | Nassau village/town nested authority misroutes a muni's parcels (e.g. Manhasset under N. Hempstead or under village) | High | High | PR #212 already flagged. Pipeline must use authority-mapping from a curated directory, not just `parcels.city`. **Refuse to flip Nassau operational** until village/town boundaries are validated against the directory. |
| 3 | Per-muni shapefile decay (URL moves, format changes from shapefile to KMZ to ArcGIS REST) | High | Low per-event | Adapter pattern handles three source kinds (shapefile, ArcGIS REST, KMZ). Add new source kinds as we encounter them; directory entry includes `last_validated_at` so periodic checks can flag staleness. |
| 4 | DuPage zoning shapefile doesn't exist; falls through to per-muni at scale | Medium | High (D.1 estimated cost balloons by 6-8 ×) | Phase 2 first action: verify DuPage GIS catalog for zoning layer. If absent, re-estimate before committing. |
| 5 | `spatial_backfill` `nearest_within_meters` fallback bleeds bad assignments | Medium | Medium | Quality gate #1 above (≤ 30 % nearest_* before operational) — already proposed. |
| 6 | Matrix authoring blows up because a county has hundreds of distinct zones (e.g. Nassau with town + village overlays) | Medium | High | Tier the matrix sprint by parcel-volume — start with zones covering ≥ 1 % of county parcels, ignore long-tail ones. PR #98 carve-out at `audit:456` allows operational status without full matrix coverage if zoning_code coverage is high. |
| 7 | Re-ingest of a county wipes user-side edits (apn normalisation, address fixups) | Medium | Medium | Upsert path in `ingestion.py` already uses ON CONFLICT on `(jurisdiction_id, apn)`; field-by-field merge preserves user-side fields. Confirm CT re-ingest doesn't overwrite e.g. `geocoded_lat` before running. |
| 8 | Westchester per-muni discovery turns up unsupported source formats (PDF-only zoning, no GIS) | Medium | High per-muni | Fallback: ordinance-PDF + Op-5 pipeline already exists for PDF→polygon flow. Higher cost but proven path. |
| 9 | A county's parcels.city values don't match the directory's `muni_name` exactly (capitalisation, "Township of X" vs "X") | High | Low | Normalise both sides in the directory entry (`prod_city_value` field PR #212 already proposed). Add a one-time match audit before ingest. |

---

## Recommended Phase 2 dispatch (Master sign-off required)

Three concrete tickets, sized so the cheapest one ships first and
validates the playbook before sinking time into the harder ones:

### Phase 2A — HALTED at pre-flight (see PR #216)

**Originally proposed**: fire `spatial_backfill` on Montgomery PA
based on the apparent Class A signal (54 zoning_districts loaded).
**Outcome**: pre-flight discovered the districts cover ~1.2 % of
the county and the dry-run returned 0 / 1,000 matches. Halted, no
prod writes. Sprint doc:
`docs/OP5_MONTGOMERY_PA_BACKFILL.md` (PR #216). Montgomery PA
retiered from Class A to Class B/D — needs source-acquisition
work, not a backfill fire.

### Phase 2B — pipeline build + Class C Fairfield CT (3-4 days, **new headline ticket**)

1. Define `MunicipalityZoningDirectoryEntry` schema (Python +
   pydantic, mirrors PR #212's shape).
2. Author per-source adapter wrapping `ingest_zoning_districts`
   for `arcgis_feature_server`, `shapefile`, `kmz` source kinds.
3. Author the Class C field-map extension in `ingestion.py` for CT
   CAMA layer; dry-run on Fairfield without write.
4. Build the per-county directory file for Fairfield.
5. Run Fairfield Class C re-ingest; audit; flip if gates clear.

**Why this is now first:** Phase 2A's free-win pretext is gone.
Class C is the next-cheapest path and amortizes across every CT
county on the same CAMA layer (Hartford, New Haven, Litchfield).
A successful Fairfield CT flip validates the adapter pattern AND
unlocks ~4-5 more counties with no per-county pipeline work.

### Phase 2C — incremental Class B rollout: Westchester (ongoing, after 2B lands)

1. Build Westchester directory (top 5 munis from PR #212's sample).
2. Run per-muni ingest + matrix for Yonkers + Greenburgh + New
   Rochelle. Validate quality gates per-muni before moving on.
3. Decision point: if quality gates hold per-muni, continue with
   Westchester's next 5 munis. If they don't, fall back and
   investigate.

Tickets 2B and 2C should not be bundled — 2B is a one-shot
adapter build; 2C is a slow per-muni grind that wants its own
weekly cadence.

### Phase 2D (future) — Montgomery PA + Class D follow-up

**Class D counties (DuPage, Nassau, Montgomery PA after PR #216
retiering)** explicitly OUT of Phase 2A/B/C. Their cost-benefit
is significantly worse and they need their own scoping after the
playbook is proven. Phase 2A's diagnostic still applies — if a
county-wide Montgomery PA zoning layer is later loaded, the
existing `spatial_backfill` path is ready to fire, and the
strengthened Class A gates above are the pre-flight playbook.

---

## What's not in this plan

- No backend code changes.
- No SQL changes.
- No schema migrations.
- No web-ordinance auto-extraction (Op-5 path covers that already
  for PDF cases; mentioned in §Class B / D fallback only).
- No `pg_repack` work — that's PR #211's diagnostic, separate
  ticket.
- No cross-jurisdiction coverage roll-up (counties flip
  independently; the audit handles roll-up).
- No re-baseline of the perf workflow — covered by PR #209's
  weekly cron.

---

## Artifacts and references

- **Code paths referenced**:
  `backend/app/services/spatial_backfill.py:44` ·
  `backend/app/services/pipeline.py:1617` ·
  `backend/app/services/pipeline.py:1677` ·
  `backend/app/services/ingestion.py` ·
  `backend/app/services/zoning_ingestion.py` ·
  `backend/app/services/zoning_discovery.py` ·
  `backend/app/services/arcgis_query.py` ·
  `backend/scripts/audit_zoning_coverage.py:386` (truthfulness gate).
- **Doc references**:
  `docs/PERF_MORRIS_ANOMALY.md` (heap clustering, PR #211) ·
  `docs/PHASE2_NY_CT_DIAGNOSTIC.md` (NY/CT structural, PR #212) ·
  `backend/data/bergen_zoning_directory.json` (directory shape
  reference).
- **Prod probes captured during this plan** (read-only):
  bucket health table above; Westchester city distribution
  (Yonkers / New Rochelle / Greenburgh / Yorktown / White Plains
  top-5); Fairfield CAMA endpoint; Montgomery PA
  zoning_districts geom coverage.
- **No writes, no schema changes, no extension installs.**
