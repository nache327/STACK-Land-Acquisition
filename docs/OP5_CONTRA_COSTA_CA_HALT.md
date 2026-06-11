# Op-5 Contra Costa CA Phase 2 — HALT (prerequisite gap)

**Owner:** Lane A
**Date:** 2026-06-11
**Sprint type:** Phase 2 Contra Costa CA production backfill (Master's Task 5 Phase 2 dispatch after Phase 1 PASS verdict)
**Verdict:** **HALT at prerequisite check.** Master's dispatch assumed Contra Costa parcels exist in prod ("preflight on prod against ~1,000 parcels"); they do not. **0 jurisdiction rows + 0 parcels for Contra Costa, 0 CA jurisdictions in prod entirely.** Phase 2 as scoped cannot run.

**Predecessor:** Phase 1 verdict at `/tmp/contra_costa_class_a_preview.md` (PASS, bbox 95.6 % / ST_Within 71.1 % via shapely source-vs-source — no DB).

---

## What Master's dispatch assumed

From the Task 5 Phase 2 brief:

> "Preflight ROLLBACK on prod against a small sample (~1,000 parcels) to confirm:
> - California Statewide Zoning North layer accessible from your env
> - Spatial backfill writes parcels.zoning_code correctly
> - raw_attributes preserved (no Norfolk-style {} discard)
> - municipality field populates from raw Town_Name or equivalent
>   (validate the prod_city_value mapping — Walnut Creek vs WALNUT CREEK
>   case-insensitivity)"

This presupposes a Contra Costa County row in `jurisdictions` and a
non-empty set of `parcels` rows scoped to it. Neither exists in prod.

## Probe evidence

```sql
SELECT id, name, state FROM jurisdictions
WHERE LOWER(name) LIKE '%contra costa%' OR LOWER(name) LIKE '%contracosta%';
-- 0 rows

SELECT id, name FROM jurisdictions WHERE state = 'CA' LIMIT 20;
-- 0 rows
```

Confirmed: 0 Contra Costa rows, 0 CA jurisdictions in prod. The Phase 1
preview verdict was a pure source-vs-source spatial primitive via shapely
(no DB connection opened — see `/tmp/contra_costa_preview.py`).

The acquisition spec already flagged this:
> `docs/CONTRA_COSTA_CA_ACQUISITION_SPEC.md` §"Current Prod State":
> "Contra Costa remains `NOT-LOADED-NEEDS-INGEST`."

## Why this matters

The Class A spatial backfill (the work Master scoped for Phase 2)
operates on `parcels.geom` × `zoning_districts.geom` — it depends on
parcels existing in prod. Without parcels:

- No `prod_city_value` mapping can be validated (the spec's
  Walnut Creek vs WALNUT CREEK question can't be answered without
  a parcel sample to grep `city` against).
- No 1,000-parcel `ST_Within` dry-run can run (no parcels to
  sample).
- The strengthened Class A gates from PR #216 (district bbox /
  parcel bbox + 1,000-row sample) can't run.
- The fire UPDATE has no target rows.

This is the same kind of prerequisite gap that surfaced in:

- **PR #216 (Phase 2A Montgomery PA)** — pre-flight found 54
  districts cover ~1.2 % of the county; halt before fire saved a
  bad bulk write. Strengthened Class A gates landed as the
  correction.
- **PR #221 (Phase 2B Fairfield CT)** — pre-flight found the CT
  CAMA layer has zero zoning attributes; the dispatch's hypothesis
  was wrong. Strengthened Class C gates (live field audit + row
  sample) landed as the correction.

This halt continues that discipline.

## What it would take to unblock Phase 2

Three pieces must land before the zoning backfill makes sense:

1. **Register Contra Costa County, CA in `jurisdictions`** — one
   INSERT row. Bbox / centroid from CCMAP layer metadata. Trivial.
2. **Ingest CCMAP Assessment Parcels** —
   `https://ccmap.cccounty.us/arcgis/rest/services/CCMAP/Assessment_Parcels_ArcPro/MapServer/0`.
   Live probes: 387,835 features, Web Mercator (wkid=102100,
   latestWkid=3857), max 2,000/req. That's **~194 paginated
   requests + PostGIS load**. Existing path:
   `backend/app/services/ingestion.ingest_parcels` (line 429).
   Empirical estimate based on prior county ingests (Bergen, Morris,
   etc.) of similar parcel counts: **4-8h wall-clock** for fetch +
   reproject (Web Mercator → WGS84) + PostGIS write + non-fatal
   overlay computation (flood / wetland) + city-field derivation
   from CCMAP's `s_city` field.
3. **Then** the zoning_districts ingest + backfill Master scoped
   for Phase 2 (~3-5h, mirrors Westchester pattern at Class A
   scale: single source filter `County='CCO'` instead of per-muni
   filters).

Items 1+2 are out of scope for Master's "Phase 2" framing (which
explicitly said "ingest California Statewide Zoning North"). Lane A
will not unilaterally expand scope to do them.

## Recommended paths forward (Master picks)

### Path 5A — split into two dispatches (recommended)

**Dispatch 5A.1**: Contra Costa parcel ingest only.
- Register jurisdiction (1 INSERT).
- Run `ingest_parcels` against CCMAP MapServer/0 with paginated
  pulls (the existing ingestion path handles Web Mercator → WGS84).
- Verify prod state: ~387,835 parcels loaded with `city`
  populated from `s_city`, raw_attributes preserved (Norfolk gate
  — preserve `s_city`, `USE_CODE`, `Description`, `ACREAGE`,
  `assr_url`, all addressing fields).
- ONE audit refresh at end; coverage will be 0 % until 5A.2
  lands.
- ~4-8h.

**Dispatch 5A.2**: Phase 2 zoning backfill (the original Task 5).
- Build the Class A statewide-zoning adapter +
  `backend/data/contra_costa_ca_zoning_directory.json`.
- Pre-flight ROLLBACK with the now-available 1,000-parcel sample.
- Fire + spatial backfill scoped to Contra Costa.
- ONE refresh.
- ~3-5h.

**Why recommended**: parcel ingest is its own gated unit. If it
halts (e.g. CCMAP layer rate-limits, or PostGIS load surprises
on 387k Web Mercator polygons), the halt is bounded to "no
parcels loaded" rather than entangled with a half-finished
zoning backfill.

### Path 5B — single bundled mega-dispatch

Do all three pieces (register + parcel ingest + zoning ingest +
backfill) in one dispatch. **~7-13h total wall-clock.**

**Risk**: a halt at any point leaves prod in a partial state
(jurisdiction without parcels, or parcels without zoning, etc.)
that someone has to reason about. The Westchester pattern
(Class B per-muni) sidestepped this because Westchester parcels
were already in prod. Contra Costa doesn't have that luxury.

### Path 5C — defer Contra Costa entirely

Park Phase 2 pending higher-priority work. Path 5C is the right
move if Master wants to:
- Wait for orchestrator's Westchester matrix sprint to land
  (which would actually flip Westchester county-wide operational)
  before spending engineering capacity on another county.
- Pursue a fresher single-county target where parcels are already
  in prod (Allegheny PA per `docs/ALLEGHENY_PA_ACQUISITION_SPEC.md`,
  Maricopa AZ per spec, King WA per spec, Hennepin MN per spec,
  Oakland MI per spec — all of which were added to main since
  PR #233).

## Lane A recommendation

**Path 5A** — split into two dispatches. Cheap halt discipline:
parcel ingest is bounded and recoverable if anything goes wrong;
zoning backfill becomes a clean Phase 2 dispatch on staged data.

If Master prefers velocity over recovery, Path 5B is acceptable
but Lane A would want explicit instruction to bundle.

If Master prefers depth-first (Westchester matrix → flip → then
new county), **Path 5C** is also defensible — the Westchester
matrix sprint is the next operational-flip wedge, and Contra
Costa Phase 1 verdict will stay valid for a long time (the
California Statewide Zoning North layer is on a multi-year
vintage cycle).

## What did NOT happen

- **No adapter code authored** — Lane A halted at prerequisite
  check, didn't author `backend/scripts/ingest_contra_costa_class_a.py`
  or `backend/data/contra_costa_ca_zoning_directory.json` yet.
  Those are for the actual Phase 2 dispatch once parcels are in.
- **No prod writes** — read-only probes only (`SELECT` against
  `jurisdictions`; ArcGIS REST queries against CCMAP and CA
  Statewide Zoning North).
- **No audit refresh fired** — there's nothing to refresh; ONE
  refresh applies to a task with writes.

## Artifacts

- `/tmp/contra_costa_class_a_preview.md` — Phase 1 verdict
  (PASS, bbox 95.6 % / ST_Within 71.1 % via shapely).
- `/tmp/contra_costa_preview.py` — Phase 1 shapely-based primitive
  probe (Agent-authored, read-only).
- This sprint doc.

## Operational state

Operational count unchanged: **17**. Contra Costa is still
`NOT-LOADED`. The Phase 1 PASS verdict in PR #238 still stands as
the spatial-primitive guarantee — when Path 5A.1 lands and parcels
exist in prod, Phase 5A.2 can fire with confidence.
