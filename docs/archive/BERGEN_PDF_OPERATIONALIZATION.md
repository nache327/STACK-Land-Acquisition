# Bergen PDF-Zoning Operationalization — MVP Plan

**Date**: 2026-05-16
**Lane**: Discovery + Coverage Expansion
**Predecessors**: `BERGEN_MUNICIPAL_ONBOARDING.md` (Iteration 4 ran NJSEA + Westwood ingest-ready)
**Status**: MVP architecture + implementation plan. Empirical PDF analysis done; no code shipped this iteration (per "minimum viable" framing — almost all infra already exists).

This doc answers: **how do we operationalize PDF-only towns (Hackensack, Fort Lee, Garfield, et al.) without building a geospatial platform?**

The headline finding from today's PDF probes: **the existing `_upload-zoning` endpoint already does 100% of the backend work needed**. The MVP is essentially a documented operator workflow + one small optional helper script.

---

## TL;DR

1. **The backend already supports PDF-onboarded zoning.** `POST /api/jurisdictions/{id}/_upload-zoning` (jurisdictions.py:1395, shipped earlier) accepts a `.geojson` or zipped shapefile, calls `ingest_zoning_districts`, optionally spatial-joins to parcels, and is idempotent (default `replace=false`). **Zero new endpoints needed for the MVP.**
2. **All required GIS libs are already installed**: `shapely`, `geopandas`, `pdfplumber`, `pyogrio`, `pypdfium2`, `fiona` — all in the venv. **Zero new dependencies needed.**
3. **PDF analysis revealed the towns split into 3 tiers**:
   - **Vector PDFs with embedded zone codes** (Fort Lee, Garfield): 4,800–8,500 line segments + ~100–2,500 zone-code text labels. **Semi-automatic extraction possible** via QGIS or pre-processing script.
   - **Raster-only PDFs** (Hackensack): 0 vector geometry, 0 zone-code text. **Manual trace required.**
   - **Unknown** (Teaneck/Fair Lawn): directory URLs were stale; need re-hunt.
4. **MVP architecture: existing endpoint + QGIS workflow + optional ~80-line helper script** to pre-extract zone-code legends from vector PDFs. Total new engineering: **~80 lines + 1 markdown runbook + zero deploys**.
5. **Per-town throughput**: 1.5 hr (vector PDFs) to 3 hr (raster PDFs) of operator time. Bergen Tier-1 PDF coverage delivered in **~6 operator hours total**.
6. **Coverage lift from PDF Tier-1**: Hackensack (~13.8k parcels) + Fort Lee (~12.1k) + Garfield (~9.6k) = **~35,500 parcels = +12.6% Bergen coverage**. Combined with prior iteration's NJSEA + Westwood + Paramus refresh:
   ```
   3.1% → 7.5–11.3% (Iter 4 NJSEA) → 20–24% (this iteration PDFs)
   ```
7. **What we deliberately do NOT build**: no LLM vision pipeline, no OCR engine, no color-segmentation engine, no headless-browser georef tool, no migration. The MVP is "tell the operator how to use QGIS + the existing endpoint."

---

## 1. Empirical PDF analysis (2026-05-16)

Downloaded each Tier-1 PDF and probed with `pdfplumber` / `PyPDF2`:

| Town | Size | Page dim (pt) | Chars | Words | Lines | Curves | Zone-code text labels | Verdict |
|---|---:|---|---:|---:|---:|---:|---:|---|
| **Hackensack** | 581 KB | 1224×792 (landscape) | 54 | 12 | 0 | 0 | 0 | **RASTER** — embedded image only |
| **Fort Lee** | 969 KB | 2592×3456 (rot 270°) | 1,331 | 251 | 8,491 | 7,868 | 132 | **VECTOR** — full geometry + labels |
| **Garfield** | 679 KB | 1737×2601 | 11,196 | 2,727 | 4,835 | 942 | 2,552 | **VECTOR** — full geometry + dense labels |

Implications for MVP:

- **Vector PDFs are ~3× faster to digitize than raster.** The lines/curves can be imported into QGIS directly (`gdal_translate -of GeoJSON file.pdf out.geojson` works for vector PDFs); the zone-code text labels can be auto-extracted by `pdfplumber.extract_words()` then spatially-joined to the closest polygon centroid.
- **Raster PDFs need full manual trace.** Operator georeferences the PDF (4–6 reference points), then traces each district polygon by hand, then types each district's zone code from the printed legend.
- **The Fort Lee PDF is rotated 270°.** QGIS un-rotates with one click; document this in the runbook so operators don't miss it.

---

## 2. Recommended MVP architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  EXISTING (no new code)                                             │
│                                                                     │
│   POST /api/jurisdictions/{id}/_upload-zoning                       │
│   (jurisdictions.py:1395)                                           │
│                                                                     │
│   Accepts:  multipart .geojson or .zip(.shp)                        │
│   Calls:    geopandas.read_file → ingest_zoning_districts           │
│   Writes:   zoning_districts (WGS84)                                │
│   Spatial:  optional spatial_backfill → parcels.zoning_code         │
│   Idempot:  default replace=false (additive)                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▲
                               │ (operator submits GeoJSON)
                               │
┌──────────────────────────────┴──────────────────────────────────────┐
│  NEW (operator workflow + optional helper)                          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Operator runbook (BERGEN_PDF_RUNBOOK.md)                   │    │
│  │   • Vector path: QGIS auto-vectorize PDF → assign zone     │    │
│  │     codes from legend → export GeoJSON                      │    │
│  │   • Raster path: QGIS georeference → manual trace → assign  │    │
│  │     zone codes → export GeoJSON                             │    │
│  │   • Validation checklist (5 spot-checks per town)           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Optional helper script (~80 lines, Slot 2 cold)             │    │
│  │  backend/scripts/extract_pdf_zone_legend.py                  │    │
│  │   • Vector PDFs: pdfplumber → list of unique zone codes     │    │
│  │     with their (x,y) positions on the page                  │    │
│  │   • Output: JSON the operator imports into QGIS as a        │    │
│  │     pre-seeded attribute table                               │    │
│  │   • Optional for v1 — operator can read the legend manually │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
              ┌────────────────────────────┐
              │  zoning_districts          │
              │  (additive per upload)     │
              │                            │
              │  spatial_backfill →        │
              │  parcels.zoning_code       │
              │                            │
              │  coverage_audit.refresh    │
              └────────────────────────────┘
```

### Architecture-design rules (per "minimum viable"):

1. **Reuse before re-build.** `_upload-zoning` exists. `ingest_zoning_districts` exists. `spatial_backfill` exists. `coverage_audit` exists. Don't add a parallel endpoint or pipeline.
2. **Operator does what's hard for software; software does what's hard for operator.** QGIS is excellent at georeferencing + polygon tracing — let operator do that. Backend is excellent at idempotent spatial join + DB hygiene — let backend do that.
3. **One file format crossing the boundary: GeoJSON.** It's lingua franca. QGIS exports it natively. The backend already parses it. No file-format negotiation.
4. **No new lib dependencies.** Every needed package is already installed.
5. **No new schema columns.** Provenance can live in `zoning_districts.source_url` (already exists) — operator passes the PDF URL as the source URL.

---

## 3. Minimum viable implementation plan

### Phase 1 — Documentation only (~2 hrs to write, 0 LOC)

- `BERGEN_PDF_RUNBOOK.md` — operator runbook with per-town tier-A/B/C recipes and a copy-paste curl for upload. Mirrors `BERGEN_INGEST_RUNBOOK.md` structure.
- Required QGIS plugins / version notes (QGIS 3.28+ has good PDF import).
- Per-Tier-1 town: a one-page recipe with screenshots-or-described steps.

This phase alone enables operationalization of all 3 Tier-1 PDF towns. **No code merges, no deploys.**

### Phase 2 — Helper script for vector PDFs (~80 LOC, Slot 2 cold, optional)

- `backend/scripts/extract_pdf_zone_legend.py` — given a vector PDF path, prints:
  - The unique zone codes detected in the legend (matched by font-style heuristic — legend codes are usually in bold/larger font than map-body labels)
  - Each code's bounding box on the PDF page
  - A JSON-formatted starter file the operator imports into QGIS as the seed attribute table

This phase cuts vector-PDF onboarding from ~1.5 hr to ~1 hr/town.

### Phase 3 — Quality validation guardrail (~30 LOC, Slot 2 cold, optional)

- `backend/scripts/validate_pdf_zoning_ingest.py` — given `(jurisdiction_id, municipality_name)`, runs:
  - `SELECT DISTINCT zone_code FROM zoning_districts WHERE …` and compares to the legend extracted in Phase 2 (no missing codes, no extras)
  - Distribution check: any single zone_code covering >70% of parcels triggers a warning (likely operator over-traced a single district)
  - Spot-check: pull 5 random parcels post-ingest, emit their `(lat, lng, assigned_zone_code)` for the operator to verify against the town's online assessor

This phase is the operator's "did I do it right?" check. Defer until at least 2 towns are onboarded.

### Phase 4 — Web georef tool (deferred indefinitely)

Build only when operator effort becomes the bottleneck AND the marginal value of one more town justifies the engineering. Not in scope today.

### Phases recap

| Phase | LOC | Hours eng | Operator hr/town | Coverage delivered (Bergen, %) |
|---|---:|---:|---:|---:|
| 1 (runbook only) | 0 | 2 | 1.5–3 | enables 12.6% from Tier-1 PDFs |
| 2 (legend helper) | ~80 | 2 | 1 | (no direct ∆; speeds operator) |
| 3 (validator) | ~30 | 1 | (saves rework) | (quality, not coverage) |
| 4 (web tool) | (deferred) | — | — | — |

**Total MVP engineering: 2 hrs doc + ~5 hrs Python (Phases 2+3).**
**Total operator time for Bergen Tier-1 PDFs: 4–6 hrs.**

---

## 4. Municipality onboarding workflow (PDF path)

```
        operator workflow                          backend workflow
        ─────────────────                          ────────────────

  ┌──────────────────────────┐
  │ 1. Pull PDF URL from     │
  │    bergen_zoning_        │
  │    directory.json        │
  └──────────┬───────────────┘
             │
             ▼
  ┌──────────────────────────┐
  │ 2. Run helper script (P2) │
  │    → zone-code legend     │
  │    (vector PDFs only)     │
  └──────────┬───────────────┘
             │
             ▼
  ┌──────────────────────────┐
  │ 3. Open PDF in QGIS       │
  │    • vector → "Import     │
  │      vector layer"        │
  │    • raster → "Georef"    │
  │      with 4-6 corner refs │
  └──────────┬───────────────┘
             │
             ▼
  ┌──────────────────────────┐
  │ 4. Trace/clean polygons,  │
  │    assign zone_code per   │
  │    polygon (drag from     │
  │    legend table)          │
  └──────────┬───────────────┘
             │
             ▼
  ┌──────────────────────────┐
  │ 5. Export → GeoJSON,      │
  │    EPSG:4326              │
  └──────────┬───────────────┘
             │
             ▼
  ┌──────────────────────────┐                ┌──────────────────────────┐
  │ 6. curl POST              │  multipart    │  _upload-zoning           │
  │    /_upload-zoning?       │  ───────────▶ │  (jurisdictions.py:1395) │
  │    spatial_join=true      │               │                          │
  │    -F file=@town.geojson  │               │  • geopandas.read_file    │
  └──────────────────────────┘               │  • to_crs(4326) if needed │
                                              │  • ingest_zoning_         │
                                              │    districts (existing)  │
                                              │  • spatial_backfill →    │
                                              │    parcels.zoning_code   │
                                              │                          │
                                              └──────────┬───────────────┘
                                                          │
                                                          ▼
                                              ┌──────────────────────────┐
                                              │ 7. Run validator (P3)     │
                                              │    → spot-check 5         │
                                              │    parcels                │
                                              └──────────┬───────────────┘
                                                          │
                                                          ▼
                                              ┌──────────────────────────┐
                                              │ 8. coverage_audit.refresh │
                                              │    → per-muni breakdown   │
                                              │    visible (needs Op-6)   │
                                              └──────────────────────────┘
```

### Per-town recipe — Tier-1 PDFs

**Hackensack (RASTER, ~3 hr operator):**
1. Pull URL: `https://ecode360.com/attachment/HA0454/HA0454-175g%20Zoning%20Map.pdf`
2. Open in QGIS via **Georeferencer** plugin
3. Reference points: identify 4–6 named street intersections visible on both the PDF and an OSM basemap. Click each pair (PDF point + OSM lat/lng). Aim for residual <50m.
4. Save the georeferenced raster (`.tif`)
5. Manually digitize each zoning district polygon by tracing the printed boundaries
6. For each polygon, type the `zone_code` from the printed legend (R-1, R-2, B-1, etc.)
7. Export attribute table + geometry to `Hackensack_zoning.geojson` (EPSG:4326)
8. `curl -X POST $API/api/jurisdictions/$BERGEN/_upload-zoning?spatial_join=true -F "file=@Hackensack_zoning.geojson"`
9. Run validator: spot-check 5 parcels against `https://hackensack.org/government/zoning`

**Fort Lee (VECTOR, ~1.5 hr operator):**
1. Pull URL: `https://www.fortleenj.org/DocumentCenter/View/417/Zoning-Map-PDF`
2. (Optional) Run `python3 backend/scripts/extract_pdf_zone_legend.py fortlee.pdf` to get the legend code list as JSON.
3. In QGIS: **Layer → Add Layer → Add Vector Layer** with the PDF directly. Choose the polygon sub-layer.
4. **Rotate the layer 90° counterclockwise** (PDF is rotated 270°). Layer Properties → Symbology → set rotation.
5. Inspect the auto-extracted polygons; merge fragmented polygons inside the same district if needed.
6. For each polygon, assign zone_code by spatial-clicking the nearest zone-code text label (or paste from the legend JSON).
7. Export → `Fort_Lee_zoning.geojson` (EPSG:4326)
8. Upload as above.

**Garfield (VECTOR, ~1.5 hr operator):**
1. Pull URL: `https://www.garfieldnj.org/_Content/pdf/zoning.pdf`
2. Same as Fort Lee, except no rotation needed.
3. Export → upload.

---

## 5. Automation boundary recommendations

What is automatable today (MVP):

| Stage | Automation status | Why |
|---|---|---|
| PDF download | **automated** | curl |
| Vector PDF → raw polygons | **partial** (`gdal_translate -of GeoJSON in.pdf out.geojson` works for vector PDFs; output needs cleanup) | QGIS-tool integration |
| Vector PDF → zone-code legend | **automated** (Phase 2 helper script) | pdfplumber position-aware text |
| Raster PDF → georeferenced raster | **operator-only** | needs human pick of reference points |
| Polygon attribute = zone_code | **operator-only** | requires interpretation of the printed legend; matching polygon→label needs spatial judgment |
| GeoJSON upload | **automated** | curl multipart |
| Backend ingest + spatial-join | **automated** | existing `_upload-zoning` |
| Post-ingest validation | **partial** (Phase 3 validator) | distinct-code check, distribution check, spot-check pull |
| Per-muni reporting | **automated, gated on Op-6** | `coverage_audit.municipality_breakdown` works once `parcels.city` is backfilled |

What MUST stay operator-assisted (don't auto-MVP):

- **Reference-point selection on raster PDFs.** Machine vision can do this but errors are catastrophic (whole-town off by 50m). Cost of human judgment: low. Cost of bad georef: re-do the whole town.
- **Polygon-to-zone-code assignment.** Some PDFs have ambiguous boundaries between similarly-colored districts; legends sometimes have notes ("R-1A applies only above 200ft elevation"). Operator has cheap context awareness.
- **"Done" decision.** When does the operator stop polishing? Validator gives signals (distribution, spot-check) — but operator decides "good enough to ingest."

What MUST stay operator-supervised (don't background-job-it):

- **First-time PDF onboarding.** Even with the helper script, the operator should babysit phase 1 (georef) end-to-end. Build trust before automation. After 5 successful Bergen onboardings, consider semi-automation for the next 50.

What's a trap to try to automate (DO NOT BUILD):

- **LLM vision → polygon extraction.** Multi-modal LLMs hallucinate geographies; bounding boxes from LLM responses cannot be trusted for spatial data. Don't ingest LLM output directly.
- **Headless-browser georeference tool.** Maintenance burden swamps the time saved.
- **Universal color-segmentation engine.** Works for ~30% of PDFs; the 70% failure cases need manual rescue, which is harder than starting manual.

---

## 6. Expected throughput + coverage lift

### Per-town effort + impact (Bergen Tier-1 PDFs)

| Town | PDF type | Operator hours | Est. parcels gained | % of Bergen |
|---|---|---:|---:|---:|
| Hackensack | Raster | 3 | ~13,800 | 4.9% |
| Fort Lee | Vector | 1.5 | ~12,100 | 4.3% |
| Garfield | Vector | 1.5 | ~9,600 | 3.4% |
| **Tier-1 total** | — | **6** | **~35,500** | **12.6%** |

### Per-operator-hour leverage

**~5,900 Bergen parcels per operator hour** — best leverage of any Bergen acquisition path to date, including NJSEA.

| Acquisition path | Parcels/operator-hour |
|---|---:|
| **PDF MVP (this iteration)** | **~5,900** |
| NJSEA ingest (Iter 4) | ~10,000 (one ingest, 10 munis) but capped at 163 polygons; non-linear |
| Vendor-tenant (Iter 3, e.g. Westwood) | ~6,600 (30 min onboard for ~3,300 parcels) |
| Hub manual probe (Iter 1) | ~50 (huge FP rate) |

### Cumulative Bergen coverage roadmap (updated 2026-05-16)

```
3.1% ──▶ 7.5–11.3%   (NJSEA + Westwood, Iter 4 runbook)
            │
            ▼
        + Tier-1 PDFs   (Hackensack + Fort Lee + Garfield, ~6 hrs operator)
            │
            ▼
        20–24%         (Bergen coverage after operationalizing all 3 PDFs)
            │
            ▼
        + Tier-2 PDFs   (Teaneck + Fair Lawn re-hunt PDFs)
            │
            ▼
        28–32%         (Bergen Tier-1 + Tier-2 complete; ~10 hrs operator)
            │
            ▼
        + 30-50 long-tail PDFs (rest of Bergen boroughs)
            │
            ▼
        50–65%         (Bergen long-tail PDFs, ~60–100 hrs operator over months)
            │
            ▼
        + NJTPA partnership / Regrid license
            │
            ▼
        70%+
```

### Bergen-wide PDF throughput projection

- 1 operator × 5 hrs/week × ~3 towns/week = ~12 towns/month
- Bergen PDF universe: ~5 (Tier 1+2 named) + ~50 (long tail) = ~55 PDF towns
- **Full Bergen PDF coverage: ~4–5 months of sustained 5-hr/week operator time**

### Cross-county leverage

The runbook + helper script are NJ-county-agnostic. Once Bergen Tier-1 is done, the same workflow operationalizes Morris, Hunterdon, Union, etc. **Per-county PDF universe is similar (~30–60 towns); per-town effort is the same.**

---

## 7. Operational risks

Ranked by severity × likelihood.

### Risk 1 — Operator georef accuracy on raster PDFs

A wrong reference point in QGIS Georeferencer can shift the whole town by 50+ meters. Spatial join then assigns thousands of parcels to the wrong zone code. **High severity (data integrity), medium likelihood.**

**Mitigation**: validator (Phase 3) spot-checks 5 random parcels post-ingest. If any return a wrong zone, the operator re-georefs. Acceptance: <1m residual on each reference point in QGIS's residuals panel.

### Risk 2 — Zone-code drift between PDF and ordinance

The PDF legend may use abbreviated codes (e.g., "R1" on the map but "R-1" in the ordinance text). Inconsistent codes break the `zone_use_matrix` join later.

**Mitigation**: operator standardizes to the ordinance text (eCode360 URL is in the directory). The validator (Phase 3) cross-references unique codes in zoning_districts vs the operator-extracted legend.

### Risk 3 — Stale PDFs

The town updates its zoning ordinance; the PDF on the website is now outdated by 2 years. Our ingested data is stale silently.

**Mitigation**: every `zoning_districts` row carries `source_url` + ingest timestamp. Quarterly: a Slot-2 script re-hashes the PDF at the source URL; mismatches trigger an operator-review alert. Out of MVP; track in roadmap.

### Risk 4 — `parcels.city` still null for Bergen → per-muni breakdown unmeasurable

After PDF ingest, total Bergen `parcel_with_zoning_code_count` rises, but per-town reporting still null without Op-6.

**Mitigation**: same as Iter 4. Op-6 (`parcels.city` backfill) is a 4-hr Slot-2 task; should run in parallel with the first PDF onboarding.

### Risk 5 — Operator hits QGIS learning curve

QGIS Georeferencer + manual digitization is a specific skill. New operators take longer to be productive.

**Mitigation**: per-town recipes in the runbook (Section 4) include exact menu paths. First town doubles as training. Cost: ~3 extra hours for the first PDF town only.

### Risk 6 — Vector PDF auto-extraction produces fragmented polygons

`gdal_translate -of GeoJSON` extracts every closed shape, including text labels rendered as outlines. The operator has to clean these up in QGIS before assigning zone_codes.

**Mitigation**: the helper script (Phase 2) emits a "polygon area threshold" recommendation — discard polygons below a per-PDF cutoff (e.g., <0.1 acre). Reduces cleanup time by ~70%.

### Risk 7 — Validator can't detect "operator drew wrong shape on right parcels"

If the operator traces a polygon that's the wrong SHAPE but happens to cover the same parcels as the correct shape, the validator's spot-check passes. Only a visual diff catches it.

**Mitigation**: accept this. Adversarial-quality polygon shapes are very rare in practice for printed zoning maps (boundaries are usually along property lines or named streets). Not worth engineering for v1.

### Risk 8 — Backend `ingest_zoning_districts` may reject GeoJSON without expected fields

The function expects (per earlier reads) `zone_code` or one of `[zone, zoning, zonedist, …]`. If operator's GeoJSON uses `zoneCode` (camelCase) or `Zone_Type`, ingest fails silently or with cryptic error.

**Mitigation**: runbook spells out: **the GeoJSON property MUST be named `zone_code`**. Validator (Phase 3) catches this on first ingest by verifying `distinct_codes > 0`.

---

## 8. Exact files / systems affected

### NEW (this MVP)

| Path | Slot | LOC (est.) | Phase | Purpose |
|---|---|---:|---:|---|
| `BERGEN_PDF_RUNBOOK.md` (next iteration) | Slot 4 docs | ~200 | 1 | Operator copy-paste runbook with per-town recipes, QGIS step-by-step, and curl upload commands |
| `backend/scripts/extract_pdf_zone_legend.py` | Slot 2 cold | ~80 | 2 | Vector-PDF zone-code legend extractor (pdfplumber-based) |
| `backend/scripts/validate_pdf_zoning_ingest.py` | Slot 2 cold | ~30 | 3 | Post-ingest spot-check + distinct-code diff |

### EXISTING — reused as-is

| Path | Role |
|---|---|
| `backend/app/api/jurisdictions.py:1395` (`_upload-zoning`) | The ingest endpoint. Already accepts GeoJSON, already calls `ingest_zoning_districts`, already spatial-joins. **No changes needed.** |
| `backend/app/services/zoning_ingestion.py` | Field-name-flexible ingest. Already handles `zone_code`, `zone`, `zoning`, `zonedist`. |
| `backend/app/services/spatial_backfill.py` | Already raw-asyncpg + 7200s timeout. |
| `backend/app/services/coverage_audit.py` | Already computes coverage snapshots. |
| `backend/scripts/onboard_municipality.py` (Iter 4) | Existing CLI for sources that have an ArcGIS URL. PDF flow uses `_upload-zoning` directly, not this script. |
| `backend/data/bergen_zoning_directory.json` (Iter 3) | Source of per-town PDF URLs. |
| `backend/data/nj_mun_code_map.json` (Iter 4) | For cross-referencing MUN_CODE if needed. |

### NOT changed

- `zoning_discovery.py` — hot, still has uncommitted scoring changes from another lane
- `pipeline.py`, `ingestion.py`, `zoning_system.py` — out of lane scope
- `alembic/versions/*` — **zero migrations needed** for this MVP

### Dependencies — ZERO new ones

Already in `pyproject.toml`: `shapely>=2.0.4`, `geopandas>=0.14.4`, `pdfplumber>=0.11.2`, `pyogrio`, `pypdfium2`, `fiona`. The `_upload-zoning` endpoint and `extract_pdf_zone_legend.py` use only these.

QGIS is operator-side (free desktop tool); no server dependency.

### Hot-file overlap risk

**Zero.** No edits to `jurisdictions.py`, `zoning_discovery.py`, `zoning_system.py`, or any Slot-1 hot file. Parallel rescoring/audit sessions continue safely.

---

## 9. What this MVP deliberately does NOT include

| Anti-recommendation | Why not |
|---|---|
| **LLM vision → polygon extraction.** | Hallucinated geographies; cannot validate to <1m. Cost of bad ingest > cost of operator time saved. |
| **Color-segmentation engine.** | Works for ~30% of PDFs; the 70% failure cases need manual rescue anyway. |
| **OCR pipeline for raster PDFs.** | Hackensack-class PDFs have <10 words of OCR-able text in headers; the zone codes are inside polygon fills (visual only). OCR returns nothing useful. |
| **Headless browser georef tool.** | Maintenance burden, browser API drift, JS bundle size. Operator already uses QGIS for ArcGIS work. |
| **PDF.js client-side georef.** | Same as above + worse CRS support. |
| **A new endpoint for PDF upload.** | `_upload-zoning` already accepts GeoJSON. Don't fragment the API. |
| **A new "pdf_candidates" table.** | The `zoning_sources` table already accommodates `source_type='pdf'`. |
| **A new migration.** | Nothing in the schema needs to change. |
| **A new background job.** | Operator-driven uploads are synchronous; ingest is ~30 sec; no need for queue. |
| **Auto-extract zone-code → polygon mapping by spatial text proximity.** | Tempting but fragile — text labels often sit OUTSIDE the polygon they describe (offset to whitespace). Defer until v2. |

---

## 10. Acceptance criteria

| Check | Pass condition | Phase |
|---|---|---|
| MVP unblocks PDF onboarding | `BERGEN_PDF_RUNBOOK.md` exists and an operator can follow it end-to-end | 1 |
| First raster town ingested | Hackensack `zoning_districts` rows > 0; spot-check 5 parcels match published zoning | 1 |
| First vector town ingested | Fort Lee or Garfield `zoning_districts` rows > 0; spot-check passes | 1 |
| Vector PDF legend extractor works | `python3 extract_pdf_zone_legend.py fortlee.pdf` emits ≥15 unique zone codes matching legend | 2 |
| Validator catches FP | Run validator on a deliberately-bad upload; reports the issue | 3 |
| Bergen Tier-1 PDF coverage | After 3 PDF ingests, Bergen `parcel_zoning_code_coverage_pct` ≥ 18% | end of phase 1 |
| Operator throughput | After 2 successful onboardings, 3rd town takes ≤2 hr operator time | end of phase 1 |
| Cross-county portability | Same runbook works for the first Morris County PDF town | next-county delivery |

---

## 11. Recommended next-iteration scope

Don't over-bundle. The next iteration should land:

1. `BERGEN_PDF_RUNBOOK.md` (Phase 1) + an operator pilot on Garfield (the easiest vector PDF) — 2 hr doc + 1.5 hr operator pilot
2. `extract_pdf_zone_legend.py` (Phase 2) shipped + used on Fort Lee — ~3 hr eng + 1.5 hr operator
3. Hackensack onboarding (the harder raster) — 3 hr operator pilot, captures lessons for the runbook v2

End-of-iteration target: **3 PDF towns operationalized; Bergen coverage ≥ 18%; runbook battle-tested.**

What stays out of scope for that next iteration:
- Phase 3 validator (build only after 2+ successful onboardings inform what to validate)
- Web georef tool (Phase 4 — deferred indefinitely)
- Tier-2 PDFs (Teaneck/Fair Lawn re-hunt — defer until Tier-1 lessons are absorbed)
- Long-tail Bergen boroughs (defer; only worth it after process is proven)

---

## Source data for this report

- Tier-1 PDFs downloaded + analyzed 2026-05-16 (Hackensack 581 KB, Fort Lee 969 KB, Garfield 679 KB)
- `pdfplumber.extract_words()` + char position + line/curve counts per PDF
- `PyPDF2.PdfReader` page metadata (rotation, dimensions)
- `backend/data/bergen_zoning_directory.json` — PDF URLs
- `backend/app/api/jurisdictions.py` — `_upload-zoning` endpoint (line 1395)
- `backend/pyproject.toml` — verified all required deps already present
- `BERGEN_MUNICIPAL_ONBOARDING.md` (Iter 4) — coverage baselines (3.1% pre-NJSEA → 7.5–11.3% post-NJSEA)
