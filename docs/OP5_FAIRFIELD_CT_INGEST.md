# Op-5 Fairfield CT Phase 2B Class C adapter — HALTED, source has no zoning field

**Owner:** Lane A
**Date:** 2026-06-11
**Sprint type:** Phase 2B — extend CT CAMA field-map to populate `zoning_code`
**Verdict:** **HALT — the dispatch hypothesis is wrong. CT CAMA has no zoning field.**
**No prod writes performed. No code changes shipped in this PR.**
**Predecessor:** `docs/INGESTION_PIPELINE_PLAN.md` (PR #214) — Class C definition needs strengthening per the parallel finding.

---

## Headline

The CT statewide CAMA + Parcel layer (the source Fairfield County
parcels already pull from) **does not publish a zoning attribute on
any sampled vintage**. Phase 2B's primary deliverable — extending
`backend/app/services/ingestion.py` to recover a zoning field map
that had been dropped — is moot. There is nothing to recover.

The Class C playbook in PR #214 was anchored on a mistaken
hypothesis. CAMA is CT's *assessment* layer (Parcel_Typ, State_Use,
Assessed_Total, Owner, Mailing_Address, etc.), not its zoning
layer. CT zoning authority is municipal under CGS Chapter 124 —
exactly the structural point PR #212 already flagged — and there
is no statewide CT zoning aggregator analogous to NJ MOD-IV.

**Two consequences**:

1. No code change populates `zoning_code` for Fairfield CT (or any
   CT county sourced from the same CAMA layer). Class C as
   originally scoped is non-actionable for CT.
2. A no-code re-ingest of Fairfield CT *would* populate
   `parcels.city` (currently 0 %), because the existing
   `_CITY_FIELDS` list already includes `TOWN_NAME` and the
   `_first()` lookup is case-insensitive. That unblocks per-muni
   Class B work for CT.

Full field audit in `/tmp/ct_cama_zoning_field_audit.md`.

---

## Pre-flight evidence

### 1. CAMA layer metadata field grep — no zoning anywhere

```
$ curl ".../Connecticut_CAMA_and_Parcel_Layer_2024/FeatureServer/0?f=json"
HTTP 200, 17,058 bytes
$ jq -r '.fields[] | "\(.name)|\(.alias)"' /tmp/ct_cama_metadata.json | grep -iE "zon|distri"
(empty)
$ jq -r '.fields[] | "\(.name)|\(.alias)"' /tmp/ct_cama_metadata.json | grep -iE "use|land"
Assessed_Land|Assessed Land
Appraised_Land|Appraised Land
Land_Acres|Land Acres
State_Use|State Use
State_Use_Description|State Use Description
```

`State_Use` is CT's per-parcel assessment code (`10` = single-family,
`15` = 2-3 family, `16` = 4+ family, plus alternative `RA3`/`COM`/`IND`
encoding in some town records). It is **not** a zoning-district
code (R-1, AAA, GB, WB, etc.). State-use is what the tax assessor
sees the property as; zoning is what the town's zoning commission
allows. They overlap occasionally but are not the same primitive.

### 2. Live row sample (Greenwich, Fairfield County)

```json
{"Town_Name":"Greenwich","Property_City":"Greenwich","Parcel_Typ":" ","State_Use":"16","State_Use_Description":null,"Land_Acres":4.3015}
{"Town_Name":"Greenwich","Property_City":"Greenwich","Parcel_Typ":" ","State_Use":"15","State_Use_Description":null,"Land_Acres":5.663}
```

No zoning attribute on any sampled row. `State_Use_Description` is
`null` for these specific Greenwich parcels — the description field
is populated for some towns and not others.

### 3. Existing prod state — CAMA fields already captured into `parcels.raw`

The prior ingest stored every CAMA attribute into `parcels.raw`
(JSONB). A sample Shelton (Fairfield County) row contains
`Town_Name`, `Parcel_Typ`, `State_Use`, `Property_City`, etc. The
0 % city in prod isn't because the ingest dropped Town_Name from
`raw` — it's because the field-map *at the time of the 2026-05-08
ingest* didn't include the CT-specific `Town_Name` casing. The
current `_CITY_FIELDS` at `backend/app/services/ingestion.py:181`
does, and `_first()` is case-insensitive, so a re-ingest today
would populate city correctly **without any code change**.

---

## Pre-flight verification table (per dispatch §1)

| Check | Expected | Observed | Status |
|---|---|---|---|
| CAMA layer reachable + responsive | yes | HTTP 200, 17 KB metadata | ✓ |
| Field list includes zoning-like attribute | yes (per dispatch) | **NONE** — closest match is `State_Use` (assessment code, not zoning) | **✗ HALT** |
| Field list includes town identity | yes | `Town_Name`, `Property_City` both present and populated | ✓ |
| Existing prod `parcels.raw` captured CAMA fields | yes | `Town_Name` etc. present in the JSONB column | ✓ |
| Existing `_CITY_FIELDS` covers CAMA naming | yes (case-insensitive) | `TOWN_NAME` in `_CITY_FIELDS`, `_first()` lowercases — would match `Town_Name` | ✓ |
| Existing `_ZONE_FIELDS` would match CAMA | n/a — source has no zoning | n/a | ✗ source gap |

---

## Quality-gate verdict (per the three gates I proposed in PR #214)

| Gate | Threshold | Status | Reason |
|---|---|---|---|
| `parcel_zoning_code_coverage_pct` | ≥ 70 % | **CANNOT EVALUATE — fix is non-actionable.** | Source has no zoning data; no code-change populates the field. |
| `zone_binding_method` nearest_* share | ≤ 30 % | n/a — no backfill | Backfill requires zoning_districts polygons; this dispatch is about parcel-attribute ingest, not spatial. |
| Provenance receipt | populated | n/a — no write | The `raw_attributes` provenance proposal applies to `zoning_districts`, not `parcels`. No relevance here. |

---

## Dispatch hard-rule compliance

| Rule | Status |
|---|---|
| Preview Supabase branch FIRST for field-map test | n/a — no code change. The halt occurred at the pre-write audit. |
| One refresh after the full prod ingest, not per-batch | n/a — no ingest fired. |
| Halt if anything looks wrong | ✓ — field audit returned zero zoning matches; halted before any code change. |
| Don't fight gates that need orchestrator's matrix work | ✓ — Fairfield doesn't flip; the gap is upstream of the field-map, not in matrix authoring. |
| If adapter works, document which CT counties same field-map unlocks | **Inverted**: documenting which CT counties the same finding affects — see below. |

---

## CT counties affected by the same finding

Every CT county currently sourced from the same CAMA layer
(`services3.arcgis.com/3FL1kr7L4LvwA2Kb/.../Connecticut_CAMA_and_Parcel_Layer_2024`)
shares this state. Fairfield is the canary. Lane A did not probe
the other 7 CT counties' `parcel_endpoint` values directly in this
sprint, but Master / orchestrator should expect:

- Fairfield County, CT (probed today; 0 % city, 0 % zoning_code)
- Hartford / Litchfield / Middlesex / New Haven / New London /
  Tolland / Windham CT — likely sourced from the same CAMA layer.

For each:

- **`city` population**: unlocked by a no-code re-ingest. The
  existing `TOWN_NAME` matcher in `_CITY_FIELDS` handles
  `Town_Name` via case-insensitive lookup.
- **`zoning_code` population**: NOT unlocked by any change to
  CAMA ingest. Each CT county/town needs its own zoning source
  (per-muni shapefile / eCode360 / Municode / town GIS portal).
  That's Class B work, not Class C. PR #212 already mapped this
  per-muni shape for Fairfield's 5 sampled towns (Greenwich,
  Westport, Darien, New Canaan, Stamford).

---

## Correction to `docs/INGESTION_PIPELINE_PLAN.md` (PR #214)

Class C as written in PR #214 requires the upstream aggregator to
actually contain the missing fields. The plan didn't include a
live field audit as a pre-flight gate for Class C — it took the
field's presence on faith from the source layer's name. PR #216
established this same pattern for Class A; **the same fix shape
applies to Class C**:

Proposed strengthened Class C pre-flight:

1. **Aggregator layer reachable + metadata loadable** (existing
   implicit check).
2. **NEW — Live field audit**: fetch the FeatureServer `?f=json`,
   grep the field list for the target attribute. If absent, the
   county is NOT Class C — re-tier to B (per-muni source needed).
3. **NEW — Live row sample**: pull 5 random rows for at least 2
   sampled munis. Confirm the target attribute is non-null and
   non-trivial (` ` / `nan` / `NULL` don't count). If consistently
   empty even though the field exists, the county is NOT Class C.

The strengthened pre-flight should be a one-paragraph addition
under §Class A's existing strengthening, plus a one-line note in
the TL;DR table that says "Class C requires the source layer to
publish the target attribute."

I'll send this as a follow-up commit to PR #214 (already-DO-NOT-MERGE
planning doc) once Master reviews this Fairfield finding.

---

## Recommended next dispatch (Master sign-off required)

### Option A — drop Class C from the Phase 2 plan; Fairfield + the rest of CT join Class B (Lane A's recommendation)

Conceptually accept that no statewide CT aggregator publishes
zoning, and route CT counties through Class B per-muni. PR #212
already mapped 5 munis for Fairfield, 5 for Nassau, 5 for
Westchester — those three together cover ~15 muni-level adapter
calls of work.

Cost: shifts ~6-10 h of "Class C field-map" effort into the Class
B per-muni queue. Doesn't add net new work; just relabels where
the effort lives.

### Option B — minimum-effort city-only re-ingest of Fairfield CT (cheap, useful, no zoning flip)

Trigger a no-code re-ingest of Fairfield CT via the existing
admin path. Audit refresh. Capture before/after. **Fairfield will
not flip operational** (still 0 % zoning_code), but `parcels.city`
will go 0 % → ~100 %, enabling Class B per-muni work to start.

Cost: 1 hour of operator time + one audit refresh. Risk: very low
(case-insensitive `_first()` is already in prod and proven). This
is the same shape as PR #216's "Option B" recommendation —
mechanical, doesn't fight any gate, sets up the next step.

### Option C — repeat Option B for every CT county sourced from the same CAMA layer

Same as Option B but applied to all 8 CT counties. Effort scales
linearly with one audit refresh at the end. **Still no
operational flips**; just enables Class B for all of CT in one
operator pass.

---

## Artifacts

- `/tmp/ct_cama_metadata.json` — full FeatureServer metadata
  response (committed nowhere; available on request).
- `/tmp/ct_cama_greenwich_sample.json` — 5-row Greenwich sample.
- `/tmp/ct_cama_zoning_field_audit.md` — extended field audit doc
  with the full attribute list + categorisation.
- No SQL writes, no audit refresh attempts, no schema changes, no
  extension installs.
