# Op-5 Proof Results

**Status:** PRE-CP1 STOP  
**Executor:** OP5 proof orchestrator  
**Date:** 2026-06-01  
**Scope:** Garfield calibration plus Hackensack, Fort Lee, and Fair Lawn pre-flight proof discovery/extraction only. No ingest, no UI work, no Lane B Sprint-2 structural coverage, no factory authorization.

## Decision

**Recommended CP3 decision:** NO-GO redesign.

This run did not reach CP1. Garfield calibration cleared the numeric proof-start gate, but the proof towns did not produce a complete CP1 review packet:

- Hackensack raster extraction could not run because `ANTHROPIC_API_KEY` is unset in the workspace. The planned raster georeference path depends on Claude vision through `backend/app/api/pdf_parser.py::_parse_with_claude_vision`, which returns `None` without the key.
- Fort Lee vector extraction required linework polygonization rather than the Garfield direct-polygon path. It produced reviewable page-coordinate polygons, but not georeferenced ingest-ready polygons.
- Fair Lawn's plan URL returned 404. A current official Borough PDF was found from the Fair Lawn zoning page, but extraction from the named `ZoneBoundries` CAD layer produced only 9 substantive multipolygons. This is too thin to treat as operational without visual review.

Do not start the 25-agent factory.

## Garfield Calibration

Artifact path: `/tmp/op5_proof/garfield/`

| Metric | Result |
|---|---:|
| Baseline auto-pair | 34/88 = 38.6% |
| Calibration auto-pair | 71/88 = 80.7% |
| Numeric proof-start gate | PASS |
| Method mix | 68 legend-color, 3 in-polygon |
| Low-confidence polygons | 17 |
| Color/in-polygon signal disagreements | 26 |

Key artifacts:

- `/tmp/op5_proof/garfield/source.pdf`
- `/tmp/op5_proof/garfield/source_render.png`
- `/tmp/op5_proof/garfield/baseline_prepare_report.json`
- `/tmp/op5_proof/garfield/baseline_starter.geojson`
- `/tmp/op5_proof/garfield/legend.json`
- `/tmp/op5_proof/garfield/polygons_labeled.geojson`
- `/tmp/op5_proof/garfield/pairing_metrics.json`
- `/tmp/op5_proof/garfield/calibration_report.md`

Calibration note: the 80.7% result is numeric only. It uses rendered-PDF legend color swatches before in-polygon labels because Garfield's labels are often offset or embedded in larger polygons. The preserved 26 signal disagreements need visual review before this method is promoted into a factory path.

## Proof Town Status

### Hackensack

Artifact path: `/tmp/op5_proof/hackensack/`

Status: STOP, raster lane blocked.

Classification:

- Class: raster
- Page count: 1
- Page size: 1224 x 792
- Rotation: 0 degrees
- PDF counts: 54 chars, 12 words, 0 lines, 0 curves, 1 image
- OGR feature count: 0

Artifacts:

- `/tmp/op5_proof/hackensack/source.pdf`
- `/tmp/op5_proof/hackensack/source_render.png`
- `/tmp/op5_proof/hackensack/classification.json`
- `/tmp/op5_proof/hackensack/raster_attempt.json`

Failure mode: **F1** triggered as an execution blocker. Raster auto-georeference/extraction could not run from this workspace because the required Claude vision credential is unavailable.

### Fort Lee

Artifact path: `/tmp/op5_proof/fort_lee/`

Status: partial vector extraction, visual review needed.

Classification:

- Class: vector
- Page count: 1
- Page size: 3456 x 2592
- Rotation: 270 degrees
- PDF counts: 1,331 chars, 251 words, 8,491 lines, 7,868 curves, 0 images
- OGR default extraction: 2,771 `LineString` features, 0 polygons after Garfield filter

Extraction:

- Method: OGR linework polygonization
- Clean polygons: 137
- Valid polygons: 137/137 = 100.0%
- Coordinate space: PDF page units, not georeferenced

Artifacts:

- `/tmp/op5_proof/fort_lee/source.pdf`
- `/tmp/op5_proof/fort_lee/source_render.png`
- `/tmp/op5_proof/fort_lee/polygons_raw.geojson`
- `/tmp/op5_proof/fort_lee/polygons_clean.geojson`
- `/tmp/op5_proof/fort_lee/extraction_metrics.json`
- `/tmp/op5_proof/fort_lee/cp1_polygon_overlay.png`
- `/tmp/op5_proof/fort_lee/prepare_report.json`
- `/tmp/op5_proof/fort_lee/classification.json`

Failure mode: not final, but **F2 risk** is active because the direct vector path did not produce polygons and downstream auto-pair has not run.

### Fair Lawn

Artifact path: `/tmp/op5_proof/fair_lawn/`

Status: partial vector extraction, visual review needed.

Source discovery:

- Plan URL returned 404: `https://www.fairlawn.org/sites/default/files/field/files-docs/official_zoningmap_3-1-2017_0.pdf`
- Current official source used: `https://www.fairlawn.org/uploads/dm/21105/Official_Zoning_Map_9152023`

Classification:

- Class: vector
- Page count: 1
- Page size: 2592 x 1728
- Rotation: 270 degrees
- PDF counts: 2,117 chars, 311 words, 14,449 lines, 8,816 curves, 0 images
- OGR default extraction: 6 features; GDAL reports named CAD layers including `ZoneBoundries`

Extraction:

- Method: OGR named layer `ZoneBoundries`
- Clean polygons: 9
- Valid polygons: 9/9 = 100.0%
- Coordinate space: PDF page units, not georeferenced

Artifacts:

- `/tmp/op5_proof/fair_lawn/source.pdf`
- `/tmp/op5_proof/fair_lawn/source_render.png`
- `/tmp/op5_proof/fair_lawn/zone_boundaries.geojson`
- `/tmp/op5_proof/fair_lawn/polygons_raw.geojson`
- `/tmp/op5_proof/fair_lawn/polygons_clean.geojson`
- `/tmp/op5_proof/fair_lawn/extraction_metrics.json`
- `/tmp/op5_proof/fair_lawn/cp1_polygon_overlay.png`
- `/tmp/op5_proof/fair_lawn/prepare_report.json`
- `/tmp/op5_proof/fair_lawn/classification.json`

Failure mode: **F2 risk** is active. The refreshed source is vector, but extracted zoning polygons are too sparse to treat as CP1-complete without visual review and likely extractor redesign.

## S1-S7 Status

| Criterion | Status | Evidence |
|---|---|---|
| S1 operational readiness | NOT RUN | No ingest/audit; CP1 not reached |
| S2 parcel zoning code coverage >= 70% | NOT RUN | `DATABASE_URL` unset; no ingest |
| S3 polygon validity >= 95% | PARTIAL | Fort Lee 100.0%; Fair Lawn 100.0%; Hackensack none |
| S4 auto-pair >= 80% | CALIBRATION ONLY PASS | Garfield 80.7%; proof towns not paired |
| S5 spot-check >= 90% | NOT RUN | No ingest and no dashboard spot-check |
| S6 wall-clock <= 4h/town | INCONCLUSIVE | Pre-CP1 work was under threshold, but core raster/vector proof incomplete |
| S7 human review <= 30 min/town | INCONCLUSIVE | CP1 packet incomplete; review burden cannot be measured |

## CP1 Status

CP1 is **not ready for approval**.

Available review artifacts:

- Fort Lee source render and overlay: `/tmp/op5_proof/fort_lee/source_render.png`, `/tmp/op5_proof/fort_lee/cp1_polygon_overlay.png`
- Fair Lawn source render and overlay: `/tmp/op5_proof/fair_lawn/source_render.png`, `/tmp/op5_proof/fair_lawn/cp1_polygon_overlay.png`
- Hackensack source render only: `/tmp/op5_proof/hackensack/source_render.png`

Missing CP1 requirements:

- Hackensack raster georef output
- Hackensack raster polygon output
- Complete source-vs-polygon packet for all three proof towns
- Any label-pairing metrics for proof towns

Required Master/user review: yes. Continue only after deciding whether to redesign the raster credential path and vector extractor path. Do not proceed to CP2 or CP3 from this run.

## Coordination Update Proposal

Proposal only; no coordination files were edited.

```json
{
  "op5_proof": {
    "status": "pre_cp1_stop",
    "recommended_decision": "NO-GO redesign",
    "summary": "Garfield calibration cleared numeric auto-pair gate at 80.7%, but Hackensack raster lane could not run without ANTHROPIC_API_KEY and vector proof towns required extractor redesign/review before CP1.",
    "blocked_factory_build": true,
    "next_required_master_action": "Decide whether to provision raster vision credentials and authorize a narrow vector extractor redesign, or abandon fully unattended Op-5 for the current sprint."
  }
}
```
