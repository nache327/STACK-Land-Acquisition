# Op-5 Fairfield CT city re-derivation — DONE (Option B from PR #221)

**Owner:** Lane A
**Date:** 2026-06-11
**Sprint type:** Phase 2B-redux — minimum-effort city re-derivation from existing `parcels.raw`
**Verdict:** **261,652 / 261,652 parcels updated. `parcels.city` 0 % → 100 %. No flip (no zoning_code yet); per-muni Class B work now unblocked.**
**Predecessor:** PR #221 (Phase 2B Class C halt). Master picked Option B.
**Bundled diagnostic:** [§ Norfolk MA embedded-zoning probe](#norfolk-ma-embedded-zoning-probe) — read-only, no writes.

---

## Headline

Direct SQL UPDATE on prod populated `parcels.city` for all 261,652
Fairfield County, CT parcels from `parcels.raw->>'Town_Name'`
(captured during the 2026-05-08 CAMA ingest into `raw` but never
mapped to the `city` column). No code shipped. The dispatch's
hard rule trio held:

- ✓ Parcel `geom` unchanged (261,652 with_geom, before = after).
- ✓ Parcel `zoning_code` unchanged (0 with_zoning_code, before = after).
- ✓ `zone_use_matrix` and `zoning_districts` row counts unchanged
  (both still 0).

ONE audit refresh fired per dispatch rule — got HTTP 502 at the
5 min mark (same refresh-endpoint Railway-proxy issue documented
in `/tmp/refresh_worker_diagnosis.md`; audit snapshot did not
commit by report time). State verified at the DB layer instead;
the public `/api/admin/coverage` snapshot will catch up on the
next successful refresh cycle.

Bundled Norfolk MA probe: **answer NO.** `parcels.raw` for all
206,365 Norfolk MA rows is the empty JSON object `{}` — the ingest
discarded source attributes. PATH 1 (embedded-zoning extraction)
is non-actionable. PATH 3 (partial-with-residual) stands.

---

## Pre-flight verification (per dispatch §1)

### Spot-check: 5 random Fairfield CT parcels

```sql
SELECT apn, raw->>'Town_Name', raw->>'Property_City', city, zoning_code
FROM parcels WHERE jurisdiction_id = '66230887-…' AND raw IS NOT NULL
ORDER BY random() LIMIT 5;
```

```
apn              | raw.Town_Name | raw.Property_City | city | zoning_code
63480-5-55       | Redding       | Redding           |      |
J250030000       | Danbury       | Danbury           |      |
B3-60            | Trumbull      | Trumbull          |      |
56060-5-70-85-0  | Norwalk       | Norwalk           |      |
C05-0045         | Ridgefield    | Ridgefield        |      |
```

**Confirms PR #221's side-finding**: every sampled row has
`Town_Name` + `Property_City` populated; `city` is NULL.

### Fleet-level coverage of `Town_Name` in `raw`

```
total      with_Town_Name   with_Property_City   current_city_filled
261,652    261,652 (100 %)  261,652 (100 %)      0 (0 %)
```

100 % of Fairfield CT parcels carry `Town_Name`. 95.6 % agree with
`Property_City` (250,147 / 261,652); 4.4 % disagree
(11,505 / 261,652). Per CGS Chapter 124 (PR #212), zoning
authority is the *town* — so `Town_Name` is the correct join key
for the future Class B per-muni adapter pattern, not
`Property_City` which can reflect mailing conventions that cross
town lines.

### Distinct town count

23 distinct CT towns: Bridgeport (26,966) · Stamford (25,524) ·
Norwalk (21,607) · Fairfield (19,616) · Danbury (18,948) ·
Greenwich (18,042) · Stratford (17,536) · Shelton (13,249) ·
Trumbull (12,050) · Newtown (10,997) · Westport (9,947) ·
Ridgefield (9,176) · Bethel (7,728) · Brookfield (7,513) ·
New Canaan (7,386) · Monroe (6,856) · New Fairfield (6,397) ·
Darien (5,831) · Redding (3,955) · Weston (3,954) · Easton (3,232) ·
Sherman (2,581) · Wilton (2,561).

Matches the expected Fairfield CT municipality list.

---

## Re-derivation path identified

**No existing admin endpoint or script handles this case.**
`backend/scripts/backfill_parcel_city.py` covers the
single-city-jurisdiction fallback (sets `city = jurisdiction.name`)
and **explicitly skips county_gis jurisdictions** (line 27:
`AND (j.parcel_source::text IS DISTINCT FROM 'county_gis')`).
Fairfield CT is `parcel_source='county_gis'`, so the existing
script declines to touch it. The `/api/admin/_backfill-nj-parcel-city`
endpoint is NJ-specific (TIGER MCD spatial join).

**Cleanest path: direct SQL UPDATE on prod.** Wrapped as
`backend/scripts/backfill_fairfield_ct_city_from_raw.py` in this
PR for reproducibility and future re-runs (the other 7 CT
counties can re-fire with a different `jurisdiction_id`). The
script uses the existing `run_batched_update` helper with
`FOR UPDATE … SKIP LOCKED` semantics so concurrent writers stay
unblocked.

### Dry-run on 100 rows (BEGIN…ROLLBACK)

100 random NULL-city Fairfield CT parcels: 100 / 100 updated
correctly, every row showing `city = raw.Town_Name`. Transaction
rolled back, no writes. Full output captured in run log; sample:

```
id      | apn              | city        | raw_town
4880279 | 115-3            | Shelton     | Shelton
4977857 | E16029           | Brookfield  | Brookfield
4988781 | 33620-11-2342    | Greenwich   | Greenwich
5010071 | 23/26/2          | New Canaan  | New Canaan
5019504 | 549400           | New Fairfield | New Fairfield
…
```

### Full UPDATE on prod

```sql
SET LOCAL statement_timeout = 0;
WITH updates AS (
  UPDATE parcels
  SET city = raw->>'Town_Name'
  WHERE jurisdiction_id = '66230887-…'::uuid
    AND (city IS NULL OR btrim(city) = '')
    AND raw IS NOT NULL
    AND raw ? 'Town_Name'
    AND btrim(raw->>'Town_Name') <> ''
  RETURNING 1
)
SELECT COUNT(*) FROM updates;
```

```
13:31:28 MDT  pre-state:  with_city=0      total=261,652
13:33:05 MDT  UPDATE:     rows_updated=261,652  (~1 m 37 s wall-clock)
              post-state: with_city=261,652 total=261,652  (100.00 %)
```

---

## Quality check — nothing else changed

| Column | Before | After | Δ |
|---|---:|---:|---|
| `parcels.city` populated | 0 | 261,652 | **+261,652 (the goal)** |
| `parcels.geom` populated | 261,652 | 261,652 | 0 |
| `parcels.zoning_code` populated | 0 | 0 | 0 |
| `parcels.land_use_code` populated | 239,752 | 239,752 | 0 |
| `zone_use_matrix` rows | 0 | 0 | 0 |
| `zoning_districts` rows | 0 | 0 | 0 |

Hard-rule trio passes. No parcel geometry changed; no `zoning_code`
changed; no matrix or zoning_districts changes. The UPDATE
touched the single `city` column (plus `updated_at` via the
table's existing trigger).

---

## Audit refresh — fired ONCE, HTTP 502 at 5 min

Per dispatch rule:

```
POST /api/admin/coverage/refresh?jurisdiction_id=66230887-…&source=phase2b-redux-fairfield-city-2026-06-11
HTTP 502, total=300.140499s
body: "upstream error"
```

Railway-proxy 5 min timeout — same behavior documented in
`/tmp/refresh_worker_diagnosis.md` and observed during the Hunterdon
matrix sprint (PR #196 needed 2 fires + ~16 min wall-clock). PR
#194 bumped the backend's asyncpg `command_timeout` to 3600 s but
Railway's HTTP proxy still caps at ~5 min for these long-running
POSTs.

**Post-refresh state on `/api/admin/coverage` at report time**:

```json
{
  "name": "Fairfield County, CT",
  "captured_at": "2026-05-19T17:57:29.041607+00:00",  // pre-update snapshot
  "parcels": 261652,
  "with_zoning_code": 0,
  "zoning_pct": 0.0,
  "readiness": "partial",
  "gaps": ["no_parcel_zoning_codes", "no_zone_use_matrix", "no_zoning_polygons"]
}
```

The audit snapshot did not commit before the 502. Hard rule "ONE
refresh per task, not per batch" means I do not fire again here;
Master can either (a) fire a second refresh in a follow-up, (b)
wait for an automated cron, or (c) accept the DB-layer
verification above for the city delta and let the snapshot catch
up later.

The DB-layer verification is authoritative for the work this
sprint did. The snapshot will reconcile on the next successful
refresh cycle; the audit's `blocking_gaps` for Fairfield CT will
not change in any case (the city population doesn't directly
affect the audit's three gates — only sets up future Class B
per-muni work).

---

## What this unlocks (and what it does NOT)

**Unlocks:** Class B per-muni work for Fairfield CT specifically.
The `(jurisdiction_id, municipality, zone_code)` matrix join key
that Bergen / Somerset / Hunterdon already use becomes available
once Lane A's Phase 2C Westchester proof validates the per-muni
adapter pattern. The 23 distinct Fairfield CT town names listed
above match the granularity needed.

**Does not unlock:**

- A flip of Fairfield CT to operational. `zoning_code` is still
  0 % across the county; PR #98's truthfulness gate requires
  ≥ 70 % zoning_code coverage. Per-muni zoning acquisition stays
  long-pole work.
- Anything for the other 7 CT counties. Master picked Option B
  scope (Fairfield-only) — the other 7 CT counties remain
  parcels-only with 0 % city, deferred per PR #214 patch (only
  Fairfield is on the 57-list per `docs/TARGET_MARKETS.md`).

---

## Norfolk MA embedded-zoning probe

> Bundled per dispatch. Read-only; no Norfolk writes performed.

### Question

Per orchestrator's Norfolk MA Phase 2B Step 1, `matrix_zone_match_pct
= 100 %` already; the only gap keeping Norfolk MA partial is
`parcel_zoning_code_coverage_pct = 74.9 %` (5.1 pp below the
parcel-source-zoned exception's 80 % threshold at
`audit_zoning_coverage.py:457-462`). PATH 1 (extract embedded
zoning from `parcels.raw`) is a possible free win if Norfolk's
ingest captured a zoning attribute that the field-map dropped —
same shape as the Fairfield CT side-finding above.

### Method

Pulled `jsonb_object_keys(raw)` from 100 random Norfolk MA
parcels with NULL zoning_code and grep-filtered for keys matching
`zon | distri | use[_ ]?code` (case-insensitive). Avoided the
`USE_CODE` / `State_Use` trap (PR #221 — assessment code, not
zoning).

### Result

```
total                 with raw NOT NULL    raw NON-trivial ({} ≠ {})
206,365 Norfolk MA    206,365              0
```

**`parcels.raw` is the empty JSON object `{}` on all 206,365
Norfolk MA parcels** — including the 51,749 with NULL
`zoning_code` that PATH 1 would target. The ingest discarded
source attributes entirely; there is no zoning-like (or any
other) field to extract.

| Norfolk MA field probe | Result |
|---|---|
| `raw` IS NULL | 0 / 206,365 |
| `raw` IS `{}` | 206,365 / 206,365 (100 %) |
| `raw` has any `zon\|distri\|use_code` key | 0 |
| `raw->>'ZONING'` populated | 0 |
| `raw->>'ZONE_CODE'` populated | 0 |
| `raw->>'ZONING_CODE'` populated | 0 |
| `raw->>'ZONING_DIST'` populated | 0 |

### Verdict

**PATH 1 is non-actionable for Norfolk MA.** Master accepts the
Norfolk MA `partial-with-residual` PATH 3 as documented in the
orchestrator's Phase 2B Step 1 diagnostic. Lifting Norfolk's
`parcel_zoning_code_coverage_pct` from 74.9 % to ≥ 80 % requires
either:

- **PATH 1-redux**: re-ingest Norfolk MA parcels from MassGIS or
  whichever upstream layer carries zoning (separate dispatch;
  not in scope here).
- **PATH 2**: lower the audit's parcel-source-zoned exception
  threshold from 80 % → 70 % (Lane A audit-logic change; needs
  jurisdiction-wide impact survey first to catch silent flips).
- **PATH 3**: accept Norfolk MA stays partial-with-residual. The
  cleanup KPI improvement (classified 79.9 → 100 %) from
  orchestrator's Phase 2B sprint already stands.

---

## Dispatch hard-rule compliance

| Rule | Status |
|---|---|
| Preview Supabase branch first for any code/ingest test | n/a — no code ingest test; just a scoped SQL UPDATE on a single column. Dry-run on 100 rows inside a ROLLBACK transaction served as the equivalent pre-flight. |
| Halt-and-report discipline | ✓ — pre-flight spot-check confirmed PR #221's hypothesis on Fairfield (proceeded); Norfolk probe confirmed PATH 1 non-actionable (halted further Norfolk work). |
| ONE refresh per task, not per batch | ✓ — fired once; 502 at 5 min documented; did not retry. |
| Don't fight gates that need orchestrator's matrix work | ✓ — Fairfield CT remains partial because zoning_code is still 0 %; matrix gate is the orchestrator's domain when per-muni data lands. |

---

## What ships in this PR

- `backend/scripts/backfill_fairfield_ct_city_from_raw.py` —
  one-off committed for reproducibility. Re-targettable to the
  other 7 CT counties if/when Master authorizes Option C scope.
- `docs/OP5_FAIRFIELD_CT_CITY_REINGEST.md` (this file).
- `docs/PHASE2_PROGRESS.md` §15 — 2026-06-11 entry with the
  Fairfield CT city result + the Norfolk PATH-1 probe outcome.

---

## Artifacts

- Pre/post DB-level verification queries captured in this doc.
- 502 response body from the audit refresh attempt
  (`upstream error`, HTTP 502, 300 s).
- No prod schema changes, no extension installs, no matrix
  or zoning_districts writes.
