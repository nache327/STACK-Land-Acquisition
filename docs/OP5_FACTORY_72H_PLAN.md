# Op-5 Factory 72-Hour Build Plan

**Owner:** Master Planning Thread
**Authorized:** 2026-06-04 via `docs/OP5_PROOF_DECISION.md` (GO WITH RASTER CARVE-OUT)
**Target:** 210 NJ municipalities across 5 Tier-S counties — vector-class to factory, raster-class to operator queue.

---

## Scope

**In scope (factory):**
- Bergen (70), Essex (22), Middlesex NJ (25), Monmouth (53), Burlington (40) = **210 munis** nominally
- **Phase 1A — Bergen factory** (~70 munis). Bergen munis have map_url populated from prior archive work AND have ArcGIS coverage via the verified-tenant catalog (`backend/data/zoning_source_tenants.json`) + NJSEA (10 Meadowlands towns). The runner's ArcGIS-first branch (CP-Pre Finding 5) handles these without PDF/vision-LLM.
- **Phase 1B — non-Bergen with discovered map_url** (~18 munis across Essex/Middlesex/Monmouth/Burlington). Per CP-Pre Finding 3, only 18/140 non-Bergen munis had a discoverable `map_url`; these route through the PDF path.
- **Operator queue (parallel, NOT factory)** — ~122 non-Bergen `absent`-classified munis + any Bergen raster/text-only-legend carve-outs. Per CP-Pre Decision 3, Master accepted the 12.9% non-Bergen discovery rate as-is and routes the remainder to operator-assisted Op-5.
- Expected factory-routable total: **~88 munis** (70 Bergen + 18 non-Bergen). Down from the original 178-189 estimate after CP-Pre measurements.

**Out of scope (operator-assisted track, parallel):**
- Hackensack-class raster munis (no vision-LLM georef path)
- Fair Lawn-class text-only-legend munis (no color→zone mapping)
- All 4 of these get standard QGIS operator workflow per `docs/archive/BERGEN_PDF_OPERATIONALIZATION.md`

**Explicitly not in this 72-hour window:**
- NY counties (Westchester, Nassau) — Phase 2
- CT (Fairfield) — Phase 2
- Wake/Mecklenburg NC, Fulton GA, etc. — Phase 3

---

## Pre-build (≈24h before H+0)

### Pre-build A — Factory orchestrator generalization

Lift the Op-5 proof orchestrator into a per-county runner:

- `backend/scripts/op5_factory_orchestrator.py` — accepts `--county <name>`, dispatches a swarm against that county's muni list
- `backend/scripts/op5_discovery_classify.py` — discovery Phase 0: for each muni in a county, classify source as `vector|raster|text_only|absent`. Output: per-county JSON.
- `backend/scripts/op5_per_muni_runner.py` — single-muni pipeline (discovery confirmation → polygon extraction → label assignment → matrix adjudication → preview ingest → audit). Idempotent per muni.

Reuses (no new code needed):
- `backend/app/services/ordinance_fetcher.py`
- `backend/app/services/ordinance_parser.py`
- `backend/app/api/pdf_parser.py` (vision + pdfplumber)
- `backend/app/services/zoning_ingestion.py`
- `backend/app/services/spatial_backfill.py` (with `nearest_within_meters=100.0` default)
- Color-segmentation + label-assignment from the proof
- `backend/scripts/pattern_*_adjudication.py` template

### Pre-build B — Review queue UI for batch matrix sign-off

Build a minimal admin surface for batch matrix review:
- `/admin/op5-review` page
- Per-muni adjudication table: zone_code, proposed verdicts, confidence, citations
- Bulk-approve at ≥90% confidence + per-row review for <90%
- ~250 LOC frontend, reuses existing admin auth
- **Critical:** without this, review burden at 210 munis ≈ 1,500 zone-code decisions kills throughput

### Pre-build C — Per-county directory builds

Replicate `backend/data/bergen_zoning_directory.json` for the other 4 counties:
- `backend/data/essex_zoning_directory.json`
- `backend/data/middlesex_nj_zoning_directory.json`
- `backend/data/monmouth_zoning_directory.json`
- `backend/data/burlington_zoning_directory.json`

Per-muni fields: `muni_code, muni_name, in_statewide_aggregator (bool), map_url, ordinance_url, website_url`. Source: NJDCA muni directory (already merged via PR #170) + per-town website probes via Playwright.

Estimated build: 2 hours per county (8 hours total), parallel agents.

### Pre-build D — DB capacity check

Confirm Supabase preview branch can sustain ~25 parallel ingest jobs:
- Connection pool sized for 25+ concurrent writers
- PostGIS `zoning_districts` table indexes verified (already done in PR #149 overlay subdivide+index)
- Snapshot the preview state pre-factory so we can roll back if anything goes sideways

**Pre-build total budget:** ~24 hours of focused work. Allocate ~5 agents.

---

## Execution (72h sprint)

### Phase 0 — Discovery classify (H 0–4)

5 discovery agents run `op5_discovery_classify.py` per county. Output: 210 munis classified into `vector | raster | text_only | absent`.

**Output:** `/tmp/op5_factory/{county}_classification.json` per county.

### Phase 1 — Vector-class extraction (H 4–48)

14-agent swarm runs `op5_per_muni_runner.py` against the ~88 in-scope munis (Phase 1A Bergen 70 + Phase 1B non-Bergen 18). Cap was 20 in the original plan; reduced to 14 at CP-Pre after `docs/OP5_DB_CAPACITY_REPORT.md` measured the Supavisor session-mode pool capped at 15 client connections — 25 concurrent agents failed ~44% at connect time. See CP-Pre Finding 1 in `docs/OP5_PRE_BUILD_REPORT.md`.

Each agent:
1. Pulls a muni from the queue
2. Classifier (CP-Pre Finding 5) routes to one of:
   - ArcGIS-verified (operator-confirmed tenant) → call `ingest_zoning_districts` directly with the FeatureServer URL
   - ArcGIS-candidate (vendor catalog hint) → probe FeatureServer, ingest if alive
   - NJSEA (Bergen Meadowlands) → use shared 20200609_Zoning service with `MUN_CODE LIKE '<code>%'`
   - PDF path (color-seg → label-assign → matrix-adjudicate)
3. Matrix adjudicate, preview ingest with F2 protect-list (CP-Pre Finding 4 — refuses to delete proof-state rows lacking `op5_factory='true'`)
4. Spatial backfill via `backfill_parcel_zoning_from_districts(nearest_within_meters=100.0)`
5. Audit + per-muni summary: coverage %, spot-check sample, binding-method distribution
6. Releases lock, picks next muni

**Per-muni budget:** ArcGIS path ~30-60 min; PDF path ~3.5 h (proven on Fort Lee/Garfield). Throughput at 14 agents:
- ArcGIS-routed munis (most of Bergen, including the 10 NJSEA Meadowlands towns): ~30 munis/day per agent
- PDF-routed munis (~20-30 of Bergen + all 18 non-Bergen Phase 1B): ~6 munis/agent/day
**Full ~88 munis complete in ~24-36 hours** assuming the mix is ~60% ArcGIS / ~40% PDF. Comfortably inside the 72-hour budget.

### Phase 2 — Operator queue handoff (H 48–60, in parallel with Phase 1 tail)

For raster + text-only munis: route to operator-assisted Op-5 queue. **This is YOUR (human) workflow**, not the agent swarm's. Per `docs/archive/BERGEN_PDF_OPERATIONALIZATION.md`, 55-80 min per muni in QGIS. ~21-32 munis = 19-43 operator hours.

The operator queue is decoupled from factory execution — operator can work it any time post-launch.

### Phase 3 — Audit + promote (H 60–72)

After all factory ingests complete on preview:
1. Run `backend/scripts/audit_zoning_coverage.py` against preview, full output JSON
2. Identify which munis flipped operational (`operational_readiness="operational"`)
3. Identify carve-outs (failed coverage despite factory completion)
4. Spot-check 1 random muni per county (5 spot-checks) for cross-county quality
5. **Master review checkpoint** — final go/no-go before prod promotion
6. If GO: promote preview state to prod via standard migration path
7. Audit refresh on prod, update `docs/PHASE2_PROGRESS.md` §1 KPI snapshot

---

## Success criteria

| # | Metric | Threshold | Reason |
|---|---|---:|---|
| F1 | Vector-class munis successfully ingested | ≥85% of vector-class total | Anything below means systemic factory failure |
| F2 | Per-muni `operational_readiness` flip rate | ≥75% of vector-class | Coverage + matrix + accuracy all clear |
| F3 | Aggregate spot-check accuracy on factory output | ≥95% on bound parcels | Proven 100% on Fort Lee + Garfield; sustain at scale |
| F4 | Factory wall-clock | ≤72 hours (Phase 1 ≤48h) | Throughput model holds |
| F5 | DB integrity post-ingest | zero `ST_IsValid` failures | Polygon hygiene preserved |
| F6 | Per-county audit shows expected operational flip count | ≥75% of vector-class per county | No county systemically worse than others |

If any of F1-F6 fail: pause factory, diagnose, decide whether to continue or roll back preview.

---

## Failure modes + mitigations

| Failure | Mitigation |
|---|---|
| Discovery classify mislabels vector as raster (false-carve-out) | Spot-check 5% of carve-outs by hand; correct + re-classify |
| Per-muni runner stalls on edge-case PDF | Per-muni wall-clock cap of 6h; auto-fail to carve-out queue |
| DB write contention slows the swarm | Reduce parallelism to 10-15 agents; throughput stays viable |
| Color-segmentation misses zones systematically in a specific county | Per-county fallback radius tuned higher (200m) per OP5_PROOF_DECISION.md |
| Review queue UI not ready by H+0 | Postpone factory launch by 24h; hard dependency |
| Operator queue overflows | Carve-out munis are non-blocking for prod promotion of factory munis |

---

## Authorized resources

- **Agents:** 25 specialized agents (5 discovery + 20 extraction). Estimated cost: ~1,200 agent-hours over 72h wall-clock.
- **Human review burden:** ≤20 hours over 72h, batched. Distribution: ~5h pre-build review + ~10h batch matrix adjudication review during Phase 1 + ~5h Phase 3 audit review.
- **DB:** Supabase preview branch `bbvywbpxwsoyvdvygvyw`. Prod-readiness check at Phase 3.

---

## What does NOT ship in this factory build

- NY (Westchester, Nassau) — Phase 2 work
- CT (Fairfield) — Phase 2 work
- Customer-facing UI changes beyond `ParcelDrawer.tsx` binding-method badge
- Operator-assisted Op-5 tooling improvements (existing QGIS workflow stands)
- Any matrix changes for existing operational munis (separate Lane E work)
- Any non-NJ Cat-B unlock work

---

## What ships AFTER the factory (next-stage queue)

In approximate order:
1. `ParcelDrawer.tsx` binding-method badge (frontend PR, ~50 LOC)
2. Operator queue runbook for carve-out munis (docs PR)
3. NY counties (Westchester + Nassau) via same factory pattern (Phase 2)
4. CT Fairfield County (Phase 2)
5. Customer onboarding flow for paying buyers in newly operational NJ Tier-S counties
6. Per-jurisdiction `nearest_within_meters` overrides UI

---

## Master review checkpoints

| CP | When | What | Time |
|---|---|---|---|
| **CP-Pre** | Before H+0 | Pre-build A/B/C/D complete; smoke test on 1 known-vector Bergen muni | ~30 min |
| **CP-Phase0** | H+4 | Discovery classify output: are the class distributions sane? | ~15 min |
| **CP-Phase1-mid** | H+24 | First 60 munis ingested; sample 5 for spot-check; confirm trajectory | ~30 min |
| **CP-Phase3** | H+60 | Full audit; review carve-outs; go/no-go for prod promotion | ~60 min |

Total CP burden: ~2.5 hours master time over 72h wall-clock.

---

## Stop conditions

The factory MUST halt and surface to master if any of the following trigger:

1. F3 (spot-check accuracy on bound parcels) drops below 90% on any sampled batch
2. F1 (success rate) drops below 70% after first 30 munis ingested
3. DB integrity errors (`ST_IsValid` failures, write timeouts) exceed 5%
4. Discovery classify mis-categorizes a known-vector Bergen muni (red flag for systemic issue)
5. Per-muni wall-clock exceeds 8h on more than 5 munis in a row

---

## What this plan does NOT contain

- Specific orchestrator prompt text (will be authored as a separate dispatch after Pre-build A-D land)
- Per-agent assignment script (orchestrator's job to allocate)
- Prod promotion runbook (separate PR after Phase 3 review)

This is the master-planning spec. Execution is the factory orchestrator's job.


---

### Pre-build C contract precondition

When building county zoning directories (essex / middlesex_nj / monmouth / burlington / future), directory rows MUST include `map_url` where it can be discovered from `website_url` via lightweight HTTP scanning (the same logic used by `op5_discovery_classify.py::discover_map_url_from_website`). It is acceptable to ship some rows with `map_url=null` if the website genuinely does not expose a zoning map, but a directory that ships with 0/N `map_url` populated is non-compliant and must be re-built before factory launch.

Historic note: Pre-build C PR #179 initially shipped 0/140 — see `docs/OP5_PRE_BUILD_REPORT.md` Finding 3 for the resolution. This precondition was codified as a result.
