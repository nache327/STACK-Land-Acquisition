# Wayzata GeoPDF Hatch QA Resolution

Date: 2026-06-23

Outcome: **HALT** for fully automatic production backfill from the PDF alone.

## Scope

This extends PR #339's GeoPDF extraction proof. The PDF remains a viable
georeferenced vector source for zoning boundaries, but this pass tested whether
the shared-fill legend classes can be resolved into a production-ready
`zone_code -> polygon` mapping for all 21 expected Wayzata codes.

No ingest was fired. No parcel, matrix, or production files were touched.

## Paths Tested

### B. PDF text extraction fallback

Result: **HALT**.

`pdfplumber` finds 16 zone-like words, but all are in the right-side legend.
There are zero zone-code text hits inside the map body (`x0 < 980` in page
coordinates). This cannot assign zone codes to polygons.

Observed:

- `zone_like_word_hits`: 16
- `zone_like_map_hits`: 0
- Missing from clean text extraction due PDF text splitting: `C-2`, `C-3`,
  `C-3A`, `C-4`, `C-4A`

### A. Hatch overlay disambiguation

Result: **HALT**.

The rendered legend visibly uses hatch patterns, but the GeoPDF does not expose
those patterns as a clean semantic field. The base polygon fills map to these
shared candidates:

| Fill | Candidate codes | Finding |
|---|---|---|
| `#FCD6D9` | `C-1`, `C-1A`, `C-1B` | 23 noisy overlay signature groups for 3 codes |
| `#FF0000` | `C-3`, `C-3A` | 14 noisy overlay signature groups for 2 codes |
| `#8F1F26` | `C-4`, `C-4A` | partial overlay signal, still requires QA |
| `#FFFFE0` | `R-1`, `R-1A` | 97 noisy overlay signature groups for 2 codes |
| `#FFAA00` | `R-3`, `R-3A` | 60 noisy overlay signature groups for 2 codes |
| `#896129` | `R-4`, `R-4A` | one vector overlay signature group for two codes |

The `R-4` / `R-4A` case is the hard blocker. The rendered legend shows `R-4A`
with white diagonal hatching, but `Layers_Zoning_Designation1` exposes all
`#896129` polygons with no distinguishing vector overlay signal. A raster
sampling heuristic can see some white pixels in the rendered map, but that
signal is contaminated by labels, roads, anti-aliasing, small polygons, and
duplicated geometries. It is not a defensible production classifier.

### C. Alternative source probe

Result: **no pivot found**.

Quick probes found no public non-PDF source:

- Wayzata Planning page links the zoning code and the March 2025 zoning map PDF;
  no `shapefile`, `GeoJSON`, `FeatureServer`, `ArcGIS`, or CSV zoning source was
  exposed in the page HTML.
- ArcGIS Online search API totals were zero for:
  - `Wayzata zoning`
  - `Wayzata zoning map`
  - `Wayzata MN zoning`
  - `Wayzata FeatureServer`
  - `Hennepin Wayzata zoning`
  - `Hennepin zoning Wayzata`
- Web search did not surface a Wayzata zoning shapefile/FeatureServer. Minnesota
  GeoCommons blocked automated browser access during this probe, so official
  data request remains the correct escalation path.

## Recommendation

Do not use an automatic hatch heuristic as a production backfill source.

Use one of these paths instead:

1. Request the source GIS zoning feature class from Wayzata Community
   Development / Hennepin GIS.
2. Use operator-assisted QA in QGIS against the rendered GeoPDF, especially for
   the shared-fill classes.
3. If a production adapter is still desired from the PDF, treat raster hatch
   classification as an assistive review layer only. Require human confirmation
   for `C-1/C-1A/C-1B`, `C-3/C-3A`, `C-4/C-4A`, `R-1/R-1A`, `R-3/R-3A`, and
   `R-4/R-4A` before any parcel backfill.

## Reproduction

```bash
python3 -m py_compile backend/scripts/_drafts/_wayzata_hatch_qa_resolution.py
python3 backend/scripts/_drafts/_wayzata_hatch_qa_resolution.py \
  --pdf /tmp/wayzata_zoning_map_2025.pdf \
  --pretty > /tmp/wayzata_hatch_qa_resolution.json
```

The script outputs the HALT verdict, text-hit counts, shared-fill overlay
signature summaries, rendered legend color profiles, ArcGIS search totals, and
Wayzata Planning page map-link probe.
