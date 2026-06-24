# Wave-6 Pre-Stage Apply Claims (Orchestrator Ownership)

**Date:** 2026-06-23
**Status:** Active — substrate ready for Path A apply per Lane A signals
**Updated:** 2026-06-23 (Lake Oswego + Summit added; Winnetka MATRIX SIGNAL received)

Per Master 2026-06-23 dispatch (ACTION 1): orchestrator claims substrate apply ownership for each pre-staged polygon. Fire Path A apply when corresponding Lane A adapter PR merges + fire-signal arrives + cov gate clears 70%.

---

## Signal status (live as of 2026-06-23)

| Polygon | Pre-stage file | Lane A adapter PR | Lane A fire PR | Signal? | Action |
|---|---|---|---|---|---|
| **Cook IL Winnetka** | `docs/AUDIT_NOTES/winnetka_il_matrix_prestaged.md` (TRACK B) | #334 MERGED | **#356 MERGED** | **🟢 MATRIX SIGNAL → orchestrator (substrate ready, 5/5 PASS @ 94.2% cov)** | **READY TO APPLY — flagged to Master for go-ahead (outside ACTION 1 scope but pre-authorized via TRACK B)** |
| **Fox Chapel PA** | `allegheny_fox_chapel.json` | #346 OPEN | — | 🟡 adapter PREP not yet merged | WAIT |
| **Williamson TN Brentwood** | `williamson_brentwood.json` | (Agent 4 adapter TBD) | — | 🔴 no adapter PR yet | WAIT |
| **Williamson TN Franklin** | `williamson_franklin.json` | (Agent 4 adapter TBD) | — | 🔴 no adapter PR yet | WAIT |
| **Fulton GA Sandy Springs** | `fulton_sandy_springs.json` | #348 MERGED | — | 🟡 PREP merged, fire PR pending | WAIT for Agent 5 fire signal |
| **Fulton GA Buckhead** | `fulton_buckhead.json` | #348 MERGED | — | 🟡 PREP merged, fire PR pending | WAIT for Agent 5 fire signal |
| **Mecklenburg Charlotte** | `mecklenburg_charlotte.json` | #354 MERGED | — | 🟡 PREP merged, fire PR pending | WAIT for Agent 6 fire signal |
| **Mecklenburg S.Charlotte** | `mecklenburg_south_charlotte.json` | #354 MERGED | — | 🟡 PREP merged, fire PR pending | WAIT for Agent 6 fire signal |
| **Wake NC Cary** | `wake_cary.json` | #353 OPEN | — | 🟡 adapter PREP not yet merged | WAIT |
| **Wake NC Raleigh** | `wake_raleigh.json` | #353 OPEN | — | 🟡 adapter PREP not yet merged | WAIT |
| **Wake NC N.Raleigh** | `wake_north_raleigh.json` | #353 OPEN | — | 🟡 adapter PREP not yet merged | WAIT |
| **Highlands Ranch CO** | `douglas_highlands_ranch.json` | #355 OPEN | — | 🟡 adapter PREP not yet merged | WAIT |
| **Cherry Hills Village CO** | `arapahoe_cherry_hills.json` | #355 OPEN | — | 🟡 adapter PREP not yet merged | WAIT |
| **Golden CO** | `jefferson_golden.json` | #355 OPEN | — | 🟡 adapter PREP not yet merged | WAIT |
| **Miami-Dade Pinecrest** | `miami_dade_pinecrest.json` | #351 MERGED | — | 🟡 PREP merged, fire PR pending | WAIT for Agent 11 fire signal |
| **Lake Oswego OR** | `clackamas_lake_oswego.json` | **#358 MERGED** | — | 🟡 PREP merged, fire PR pending | WAIT for fire signal |
| **Summit UT Park City corridor** | `summit_park_city_corridor.json` | (Agent TBD — Phase 6 outlier rank 2) | — | 🔴 no adapter PR yet | WAIT + POLYGON CONFIRMATION GATE |
| **Westport CT** | `fairfield_westport.json` | (Agent 9 Phase 2 probe v2 PR #361 MERGED) | — | 🟢 source verified — Lane A ready to fire | WAIT for Lane A Westport fire signal |
| **New Canaan CT** | `fairfield_new_canaan.json` | (Agent 9 Phase 2 probe v2 PR #361 MERGED) | — | 🟢 source verified — Lane A ready to fire | WAIT for Lane A New Canaan fire signal |
| **Wilton CT** | `fairfield_wilton.json` | (Agent 9 Phase 2 probe v2 PR #361 MERGED) | — | 🟢 source verified — Lane A ready to fire | WAIT for Lane A Wilton fire signal (Master approval on Wilton as 58-list/wealth-band first) |
| **Englewood CO** | `arapahoe_englewood.json` | (Agent — Phase 6 secondary PR #360 MERGED) | — | 🟢 source verified — VIABLE per probe | WAIT for Lane A Englewood fire signal |
| **Greenwood Village CO** | `arapahoe_greenwood_village.json` | (Agent — Phase 6 secondary PR #360 MERGED) | — | 🟡 PIVOT — authority QA needed on Urban "existing zoning" service | WAIT for authority QA + fire signal |

**Refreshed substrates (live distinct list verification post-adapter merge, 2026-06-23):**
- `williamson_brentwood.json`: 10 → **21 codes** (case fix R1→R-1; added 11 codes including /SR Special Review variants + AR-IP/OSRD-IP/SI-3/SI-4)
- `williamson_franklin.json`: 8 → **22 codes** (added 14 codes including R1/R2/R3/R4/R6 + RC4/RC6/RC12 + OR/MR/NC/HI/1ST/5TH)

**Legend:** 🟢 fire-signal received | 🟡 partial (PREP merged or adapter open) | 🔴 no adapter activity yet

---

## HAND-OFF substrates for nache (Burlington NJ Phase 1 — DO NOT apply via orchestrator)

Per Master 2026-06-23 ACTION 2 dispatch: Burlington NJ Phase 1 closer-out substrates are HAND-OFF artifacts. nache owns Burlington execution; substrate sits ready for him to single-POST when his adapter fires.

| Polygon | Pre-stage file | Owner | Source PR | Apply gate |
|---|---|---|---|---|
| **Medford township NJ** | `burlington_nj_medford.json` (3 codes: GD/CC/PD) | **nache** | #369 Burlington NJ probe MERGED | Matrix-near-ready; nache completes 3 missing rows then per-muni registration + audit |
| **Mount Laurel township NJ** | `burlington_nj_mount_laurel.json` (23 codes) | **nache** | #369 Burlington NJ probe MERGED | nache verifies GovPilot adapter (parcel-detail ZONING or ZM polygons), then matrix sprint |
| **Moorestown township NJ** | `burlington_nj_moorestown.json` (16 codes) | **nache** | #369 Burlington NJ probe MERGED | nache verifies GovPilot polygon adapter + bbox/parcel-match preflight, then matrix sprint |

**Orchestrator does NOT apply Burlington substrates.** They are pre-staged for nache's domain only.

---

## Updated combined totals (2026-06-23 post-Burlington extension)

- **24 polygons** in `backend/data/wave6_pre_stage/`
- **472 matrix rows / 1,888 use-cell decisions** all `prohibited` (Bergen catchall × 4)
- **3 Burlington NJ substrates** (hand-off for nache)
- **21 orchestrator-owned substrates** (Winnetka already applied via PR #367 → count 38 → 39; remaining 20 awaiting Lane A signals)

---

## Apply procedure (when signal arrives per polygon)

```bash
# 1. Verify cov gate clears 70%:
GET /api/admin/coverage?jurisdiction_id={jid}
#    parcel_zoning_code_coverage_pct >= 70

# 2. Verify codes match prediction:
GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={jid}&limit=500
#    compare against backend/data/wave6_pre_stage/<county>_<muni>.json zone_code list

# 3. Apply (single batch per polygon):
POST /api/jurisdictions/{jid}/_upload-matrix-rows
  Body: {"rows": <file contents>, "replace_existing": false}
  Note: factory_safe_write contract — preserves human_reviewed=true rows from nache

# 4. Verify endpoint truth:
GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={jid}&limit=500
#    uncovered_count should drop to 0 (or close to 0 if code-mismatch tail exists)

# 5. ONE refresh per polygon:
POST /api/admin/coverage/refresh?jurisdiction_id={jid}&source=wave6-prestage-{muni}-2026-06-XX

# 6. Update tracker:
# coordination/lane_state.json honest_operational_count.current_api_truth +=1
# docs/PHASE2_PROGRESS.md §15 entry per polygon
```

## Path A vs Path B vs Path C

- **Path A** (codes match): single 5-10 min apply; expected case
- **Path B** (codes mismatch): re-author missing codes at apply-time using same Bergen catchall × 4 pattern; ~30-60 min
- **Path C** (cov gate blocked): apply substrate anyway (substrate-armed-cov-gate-blocked), document blocker, wait for Lane A unblock (Fountain Hills pattern)

## Hygiene reminders

- ✅ `replace_existing=false` insert-only — idempotent across re-runs
- ✅ Bergen catchall × 4 prohibited holds — NO verdict-truth lift (halted Somerset sprint domain)
- ✅ Quote hard-cap 200 chars per Stamford 422 precedent
- ✅ Preserve `human_reviewed=true` rows from nache (Howard MD / Montgomery MD / Fairfax VA / etc.) — none of the wave-6 polygons overlap with nache's verdicted set, but factory_safe_write contract protects either way
- ✅ Quote sub-AOI caveat in §15 changelog (Buckhead/S.Charlotte/N.Raleigh/Summit unincorporated)
- ❌ DO NOT MERGE PR #349 — apply happens via runtime POST, not git merge

## Expected operational count delta

Current count: **38** (per `coordination/lane_state.json` honest_operational_count.current_api_truth)

| Phase | Polygons | Best-case +ops | Realistic +ops |
|---|---:|---:|---:|
| Cook IL | 1 (Winnetka, signaled) | +1 | +1 (signal received) |
| Allegheny PA recovery | 1 (Fox Chapel) | +1 | +1 |
| Williamson TN | 2 (Brentwood + Franklin) | +2 | +1-2 |
| Fulton GA | 2 (Sandy Springs + Buckhead) | +2 | +1-2 (Buckhead needs KMZ) |
| Mecklenburg NC | 2 (Charlotte + S.Charlotte) | +2 | +1-2 (S.Charlotte needs KMZ) |
| Wake NC | 3 (Cary + Raleigh + N.Raleigh) | +3 | +2-3 (N.Raleigh needs KMZ) |
| CO Front Range | 3 (Highlands Ranch + Cherry Hills + Golden) | +3 | +2-3 |
| Miami-Dade Pinecrest | 1 | +1 | +1 |
| Lake Oswego OR | 1 | +1 | +1 (clean city zoning) |
| Summit UT corridor | 1 | +1 | +0-1 (polygon confirmation gate) |
| **TOTAL** | **17** | **+17 → 55** | **+11-17 → 49-55** |

(Winnetka counted once at +1; if Master picks "South Charlotte" as separate jurisdiction from Charlotte, count would be +1 more per sub-AOI registered as separate jid)

## Standing posture

- Substrate ready for 17 polygons across PR #349 (this branch) + Winnetka pre-stage (separate branch)
- Lane A signals being monitored; auto-fire blocked by need for prod API auth credentials
- Halt rule on verdict-truth stands — NO UPDATEs without source-access unlock
- Awaiting Master go-ahead on Winnetka apply (signal arrived, outside ACTION 1 scope)
