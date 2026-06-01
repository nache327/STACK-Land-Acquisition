# Op-5 Pre-Flight Proof Plan

**Owner:** Master Planning Thread
**Status:** Authorized 2026-06-01 (approved via plan `~/.claude/plans/you-are-the-master-peppy-rabbit.md`)
**Purpose:** Falsifiable test of whether AI-assisted automation can replace operator-assisted QGIS in the per-municipality PDF zoning acquisition pipeline. Three Bergen County NJ towns. Pass = authorize 25-agent factory. Fail = redesign or fall back to operator-assisted Op-5.

---

## Context

The Northeast coverage audit established that ~85-90% of NJ/NY/CT municipal zoning is theoretically acquirable via automation if a PDF georeference + zone-label pairing pipeline ("Op-5") exists. The previous Op-5 design (`docs/archive/BERGEN_PDF_OPERATIONALIZATION.md`, 2026-05-16) explicitly rejected machine-vision georeferencing as too costly and routed it through operator-assisted QGIS instead. A real Garfield pilot on 2026-05-18 (`docs/archive/BERGEN_PDF_PILOT_GARFIELD.md`) confirmed that the operator-assisted path works in 55-80 minutes per town but auto-paired only **38.6%** of polygons to zone codes — the remaining 61% needed manual QGIS assignment.

**Question this proof answers:** can Claude vision + parallel agents close the auto-pairing gap and remove the QGIS step, making per-town acquisition fully unattended? If yes, 11 NJ + 2 NY + 1 CT counties (~557 munis) become a 1-month factory job. If no, they remain a multi-month operator-staffed slog.

**This is not a coverage push.** It is a falsifiable test of the factory thesis on the 3 hardest-class jurisdictions before committing 20+ agents to scaling.

---

## Target towns

| Town | muni_code | PDF class | map_url | ordinance_url | Why include |
|---|---|---|---|---|---|
| Hackensack | 0223 | **RASTER** (0 vectors empirically) | `https://ecode360.com/attachment/HA0454/HA0454-175g%20Zoning%20Map.pdf` (581 KB) | `https://ecode360.com/13166949` | Hardest class. If raster fails, ~10-15% of NJ munis fall out of the factory. |
| Fort Lee | 0219 | **VECTOR rotated 270°** | `https://www.fortleenj.org/DocumentCenter/View/417/Zoning-Map-PDF` (969 KB) | `https://ecode360.com/10071645` | Tests rotation + label density. 8,491 lines / 132 zone-code labels per 2026-05-16 audit. |
| Fair Lawn | 0217 | **VECTOR (status TBD)** | `https://www.fairlawn.org/sites/default/files/field/files-docs/official_zoningmap_3-1-2017_0.pdf` | `https://ecode360.com/10052217` | Tests end-to-end discovery + acquire on a "fresh" source (URL re-hunted after prior 404). |
| Garfield | 0221 | VECTOR — *calibration only, not counted toward proof* | (per `bergen_zoning_directory.json`) | `https://ecode360.com/...` | 2026-05-18 baseline: ogr2ogr → 88 polygons in 0.49s, 38.6% auto-paired. Rerun through new pipeline to validate. |

All four ordinances are on eCode360 with confirmed URLs. Ordinance retrieval is not a failure mode for this proof.

---

## Success criteria (per town, all required)

| # | Metric | Threshold | Reason |
|---|---|---|---|
| S1 | Town reaches `operational_readiness="operational"` per `backend/scripts/audit_zoning_coverage.py::_operational_readiness` | YES | Existing audit logic |
| S2 | `parcel_zoning_code_coverage_pct` ≥ 70% post-ingest | ≥70 | Audit truthfulness gate (PR #98) |
| S3 | Polygon validity rate (`ST_IsValid`) on inserted districts | ≥95% | Topology must be clean for spatial joins |
| S4 | Auto-pair rate polygons → zone codes | **≥80%** | Beats Garfield baseline (38.6%) by 2.07×; required to remove QGIS dependency |
| S5 | Spot-check accuracy on 10 random parcels per town | ≥90% correct vs ordinance | Verdict trust — humans audit a sample, not all |
| S6 | Per-town wall-clock execution (agent-elapsed) | ≤ 4 hours | Factory throughput target: ~6 towns/agent/day |
| S7 | Human review burden per town | ≤ 30 min | At 210 munis = ~100 review hours total |

## Failure modes that invalidate the factory thesis

| # | Failure | Implication |
|---|---|---|
| F1 | Hackensack (raster) cannot auto-georeference within ≤ 4h | ~10-15% of NJ munis blocked → factory ceiling caps at ~85% |
| F2 | Auto-pair rate stuck < 60% on vector PDFs | Matrix authoring becomes the bottleneck → factory does not scale |
| F3 | Ingest produces >5% `ST_IsValid` failures | Per-town human review balloons; throughput model breaks |
| F4 | Spot-check accuracy < 75% on any town | Verdict trust below customer-usable threshold |
| F5 | Per-town wall-clock > 8h even for vector | Factory math doesn't work (would need 50+ agents not 25) |
| F6 | Audit reports `no_zoning_polygons` despite ingest | Pipeline didn't actually populate `zoning_districts` |

## Go/no-go decision tree

```
3/3 towns pass all criteria  → GO. Build 72-hour factory.
2/3 towns pass               → GO with carve-out. Factory addresses ~85% of munis;
                               failing class stays operator-assisted.
1/3 towns pass               → NO-GO. Redesign required (see table at bottom).
0/3 towns pass               → NO-GO. Op-5 automation thesis invalidated;
                               adopt operator-assisted QGIS workflow at scale.
```

---

## Lanes and agents

### Lane-PDF-DISCOVERY (1 agent)
**Purpose:** Verify PDF accessibility, classify vector vs raster, extract metadata.
**Inputs:** `backend/data/bergen_zoning_directory.json` entries for Hackensack/Fort Lee/Fair Lawn.
**Outputs:**
- `/tmp/op5_proof/{muni}/source.pdf` — downloaded file
- `/tmp/op5_proof/{muni}/classification.json` — `{class: vector|raster|hybrid, page_count, has_geo_metadata, page_size, rotation_deg}`
- `/tmp/op5_proof/{muni}/legend_image.png` — extracted legend region (if separable)
**Reuses:** `backend/app/services/ordinance_fetcher.py::fetch_from_url` (Playwright + httpx fallback).

### Lane-PDF-VECTOR (1 agent per vector town; Fort Lee + Fair Lawn run in parallel)
**Purpose:** Extract polygons from vector PDFs using `ogr2ogr` (proven in Garfield pilot).
**Inputs:** `/tmp/op5_proof/{muni}/source.pdf`
**Outputs:**
- `/tmp/op5_proof/{muni}/polygons_raw.geojson`
- `/tmp/op5_proof/{muni}/polygons_clean.geojson` — topology-fixed
- `/tmp/op5_proof/{muni}/extraction_metrics.json` — `{polygon_count, valid_pct, total_extract_seconds}`
**Reuses:** Garfield pilot scripts (`backend/scripts/extract_pdf_zone_legend.py` + `backend/scripts/validate_pdf_zoning_ingest.py` per Bergen archive).

### Lane-PDF-RASTER (1 agent for Hackensack — the critical experimental lane)
**Purpose:** Vision-LLM-driven georeference + polygon extraction from raster PDF.
**Inputs:** `/tmp/op5_proof/hackensack/source.pdf` (page-rendered to PNG ≥300 DPI)
**Outputs:**
- `/tmp/op5_proof/hackensack/georef.json` — `{anchor_points: [(pixel_x, pixel_y, lat, lon)...], affine_transform, rms_error_meters}`
- `/tmp/op5_proof/hackensack/polygons_raw.geojson` — vision-LLM-traced polygons + zone code labels
- `/tmp/op5_proof/hackensack/polygons_clean.geojson` — topology-cleaned
**Method:** Claude Opus 4.7 vision via existing `_parse_with_claude_vision` in `backend/app/api/pdf_parser.py`. New prompt at `backend/app/prompts/op5_raster_georef.md`. Multi-pass: (1) identify map extent + 4+ georeference anchors, (2) trace polygon boundaries by zone color, (3) extract zone code label per polygon.
**Net-new code:** ~150 LOC orchestrator + vision prompt.

### Lane-LABEL-PAIRING (1 agent, shared across 3 towns — the other critical lane)
**Purpose:** Pair extracted polygons with zone codes at ≥80% auto-rate.
**Inputs:** `polygons_clean.geojson` + `legend_image.png` + `source.pdf`
**Outputs:**
- `polygons_labeled.geojson` — polygons with `zone_code`, `zone_label_source` (`in_polygon|nearest|legend_color`), `confidence`
- `pairing_metrics.json` — `{auto_paired_pct, by_method, low_confidence_polygons}`
**Method:** (1) Color sampling of polygon interior → match to legend swatch. (2) OCR text inside polygon. (3) Nearest-label fallback (Voronoi). (4) Per-town color-code dictionary built from legend via vision-LLM.
**Net-new code:** ~200 LOC.

### Lane-ORDINANCE-FETCH (1 agent, shared)
**Purpose:** Retrieve eCode360 ordinance text + table-of-uses.
**Reuses:** `backend/app/services/ordinance_fetcher.py::fetch_from_url`, `backend/app/services/ordinance_parser.py::parse_ordinance_sections`, prompt at `backend/app/prompts/ordinance_parse.md`.
**Net-new code:** zero.

### Lane-MATRIX-ADJUDICATE (1 agent, shared)
**Purpose:** Author `zone_use_matrix` rows using `pattern_*_adjudication.py` precedent.
**Outputs:**
- `backend/scripts/pattern_bergen_hackensack_adjudication.py` (one per town, Norfolk MA pattern)
- `backend/scripts/pattern_bergen_fort_lee_adjudication.py`
- `backend/scripts/pattern_bergen_fair_lawn_adjudication.py`
- `matrix_rows.json` × 3 + `low_confidence_rows.json` × 3 (flagged for review)
**Reuses:** `backend/scripts/pattern_norfolk_ma_adjudication.py` + `backend/scripts/pattern_middlesex_ma_adjudication.py`.
**Net-new code:** ~50 LOC per town adjudication script.

### Lane-INGEST (1 agent, shared)
**Purpose:** Push labeled polygons → `zoning_districts` and matrix rows → `zone_use_matrix`.
**Method:** `POST /api/jurisdictions/{id}/_upload-zoning` (idempotent). Post-ingest auto-triggers `backfill_parcel_zoning_from_districts` per `backend/app/services/pipeline.py:1617`.
**Net-new code:** zero.

### Lane-VALIDATE (1 agent + human review)
**Purpose:** Run audit + spot-check verdicts.
**Outputs:**
- `audit_post_op5.json` per town
- `spot_check.json` × 3 (10 random parcels per town)
- `docs/OP5_PROOF_RESULTS.md` — final pass/fail report against S1-S7

### Lane-MASTER (you)
**Purpose:** Go/no-go decision after VALIDATE.
**Outputs:** `docs/OP5_PROOF_DECISION.md`; updates `coordination/lane_state.json` + `coordination/dispatch_queue.json`.

### Total: 8 specialized agents + 1 master review

---

## Human review checkpoints (yours — 3 total, ~60 min)

| CP | When | What you review | Time |
|---|---|---|---|
| **CP1** | After Lane-PDF-VECTOR + Lane-PDF-RASTER finish | Side-by-side per town: source PDF screenshot vs extracted polygons rendered on map. Do shapes match? Are colors mapped correctly? | ~15 min |
| **CP2** | After Lane-MATRIX-ADJUDICATE | 5 random zone-code adjudications per town with ordinance citations. Confirm verdicts defensible. | ~25 min |
| **CP3** | After Lane-VALIDATE | Final `OP5_PROOF_RESULTS.md` + 10-parcel spot-check per town. GO/NO-GO. | ~20 min |

---

## Hour-by-hour execution (target: 48h)

| Block | Lane(s) active | Output gate |
|---|---|---|
| **H 0-2** | Discovery | 3 source.pdf + classifications complete |
| **H 2-8** | Vector × 2 parallel (Fort Lee, Fair Lawn) | polygons_clean.geojson × 2 |
| **H 2-16** | Raster × 1 (Hackensack) — long-running vision-LLM | polygons_clean.geojson |
| **H 4-12** | Ordinance fetch + parse (all 3) | ordinance_sections.json × 3 |
| **H 8-20** | Label pairing (3 towns) | polygons_labeled.geojson × 3 |
| **H 16** | **CP1 — your polygon review** | Decision: proceed or stop & diagnose |
| **H 16-28** | Matrix adjudicate (3 towns) | matrix_rows.json × 3 + adjudication scripts |
| **H 28** | **CP2 — your matrix sample review** | Decision: proceed or rework prompts |
| **H 28-36** | Ingest (3 towns serial) | DB state for 3 munis |
| **H 36-42** | Validate (audit + spot-check) | OP5_PROOF_RESULTS.md |
| **H 42-44** | **CP3 — your audit review** | GO/NO-GO |
| **H 44-48** | Decision write-up | OP5_PROOF_DECISION.md + coordination update |

If Hackensack raster takes >16h, don't block vector flow: Fort Lee + Fair Lawn audit independently. Hackensack determines F1 carve-out only.

---

## Critical files

### Reused (no edits in proof phase)
- `backend/app/services/ordinance_fetcher.py` — Playwright + httpx fetch
- `backend/app/services/ordinance_parser.py` — Claude-driven section extraction
- `backend/app/prompts/ordinance_parse.md` — existing system prompt
- `backend/app/api/pdf_parser.py` — pdfplumber + Claude vision PDF handler
- `backend/app/services/zoning_ingestion.py` — `ingest_zoning_districts(gdf, jurisdiction_id, ...)`
- `backend/app/services/spatial_backfill.py` — `backfill_parcel_zoning_from_districts(...)` (auto-called post-ingest)
- `backend/app/services/pipeline.py:1617` — post-ingest backfill hook
- `backend/scripts/audit_zoning_coverage.py::_operational_readiness` — operational gate
- `backend/scripts/pattern_norfolk_ma_adjudication.py` — adjudication template
- `backend/scripts/pattern_middlesex_ma_adjudication.py` — adjudication template
- `POST /api/jurisdictions/{id}/_upload-zoning` (`backend/app/api/jurisdictions.py:1395`) — idempotent GeoJSON ingest
- `backend/data/bergen_zoning_directory.json` — directory rows for Hackensack/Fort Lee/Fair Lawn

### Net-new during proof (~600-700 LOC total)
- `backend/app/prompts/op5_raster_georef.md` — new vision prompt for raster georef
- `backend/app/prompts/op5_label_pairing.md` — new vision prompt for color→zone-code dictionary
- `backend/scripts/op5_proof_orchestrator.py` — orchestrates Discovery → Vector/Raster → Pairing → Ingest → Validate
- `backend/scripts/op5_raster_extract.py` — raster pipeline (vision-LLM georef + polygon trace)
- `backend/scripts/op5_label_pairing.py` — pairing algorithm (color + OCR + nearest)
- `backend/scripts/op5_spot_check.py` — 10-parcel sample generator
- `backend/scripts/pattern_bergen_hackensack_adjudication.py`
- `backend/scripts/pattern_bergen_fort_lee_adjudication.py`
- `backend/scripts/pattern_bergen_fair_lawn_adjudication.py`
- `docs/OP5_PROOF_RESULTS.md` — final pass/fail report
- `docs/OP5_PROOF_DECISION.md` — GO/NO-GO decision

### Coordination updates (after CP3)
- `coordination/lane_state.json` — record Op-5 proof outcome + master GO/NO-GO
- `coordination/dispatch_queue.json` — authorize 72-hour factory build OR record redesign
- `coordination/blockers.json` — close B4 carryover risk if proof succeeds

---

## Verification (end-to-end test before declaring GO)

1. **Garfield calibration:** rerun new pipeline against Garfield (2026-05-18 baseline) WITHOUT writing to DB. Expect auto-pair rate ≥80% (vs 38.6% baseline). If fails, abort proof.
2. **DB write isolation:** ingest to Postgres branch (Supabase preview) before prod. Confirm 3× `_operational_readiness == "operational"` against branch.
3. **Audit numerical check:** `python backend/scripts/audit_zoning_coverage.py --jurisdiction-id <bergen-county-id> --json | jq '.jurisdictions[] | select(.name=="Bergen County, NJ")'` shows Hackensack/Fort Lee/Fair Lawn parcels with `parcel_zoning_code_coverage_pct ≥ 70%` and zone_code populated.
4. **Spot-check:** open 10 random parcels per town in dashboard, confirm verdict + zone matches ordinance section.
5. **Idempotency:** rerun pipeline on one town. Expect zero net changes (existing `ON CONFLICT DO NOTHING`).

---

## If GO: 72-hour factory build (referenced for context after CP3)

- Pre-build ~24h: generalize `op5_proof_orchestrator.py` into per-county runner, scale `op5_raster_extract.py` for parallel concurrency, build review queue UI for batch matrix sign-off, build per-county directory generators for 14 more counties.
- Execution: 25 specialized agents × 72h targeting 5 priority counties (Essex → Middlesex NJ → Burlington → Monmouth → Bergen).
- Detailed plan goes into separate `docs/OP5_FACTORY_72H_PLAN.md` authored after GO.

## If NO-GO: redesign decision tree

| Failure | Redesign target |
|---|---|
| F1 only (raster broken) | Two-track factory: vector via Op-5 auto (~70% of munis), raster via operator QGIS at scale (~15%). 1-month vector + 6-month raster tail. |
| F2 (auto-pair <60%) | Reframe label pairing as fine-tuning: per-county color-code dictionary mined from ordinance text. +1 week pre-build. |
| F3 (polygon validity broken) | Topology-cleanup pass via `shapely.make_valid` + reject threshold. Small fix. |
| F4 (spot-check accuracy <75%) | Pipeline produces unsafe verdicts. Architecture issue. Return to operator-assisted Op-5. |
| F5 (wall-clock >8h) | Factory math doesn't close. More agents (cost) or accept 1→3 month timeline. |
| F6 (audit `no_zoning_polygons` despite ingest) | Ingest didn't write — debug, not architecture. |

---

## What you (Master) decide at CP3

1. **"GO"** — write `docs/OP5_FACTORY_72H_PLAN.md` + authorize 25-agent factory.
2. **"GO with carve-out"** — vector-only factory; raster towns stay operator-assisted; revise counts.
3. **"NO-GO redesign"** — implement specific failure-mode fix per tree; rerun proof.
4. **"NO-GO abandon"** — fall back to operator-assisted Op-5; acknowledge multi-month NJ timeline honestly.

Each decision updates `coordination/lane_state.json` and either authorizes Lane B Sprint-2 work (factory or operator-assisted) or pauses Northeast acquisition.
