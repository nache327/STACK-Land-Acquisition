# Bloomfield Twp MI vector-PDF zoning digitize — STOP (confidence: UNUSABLE) (2026-07-15)

jid 15ecf7aa. Pre-staged confirmed: 18,224 parcels, zoned=0, ring 16,991 dt10, centroids 100%, extent
= Oakland Co MI (-83.325..-83.207, 42.529..42.621, #38 ✓). **Did NOT bind — the vector-PDF digitize is not
reliable enough to bind 18k parcels without poisoning; the ML needle cannot be located from this PDF.**
No DB writes made (all extraction read-only). This trips the task's own "#38 mismatch = STOP" guardrail.

## PDF confirmed vector + extractable — but the zone semantics are NOT recoverable
Source `bloomfieldtwp.org/media/rkspljft/zoningmap.pdf` (6.1 MB, 1 page, 1224×792pt, **42,926 curves**,
1,326 rects, 33,503 chars). Fill colors extract fine (~10 distinct RGB fills). Three fatal problems:

1. **ML and RP labels do NOT exist as text (count = 0).** So do A-1..A-6 (0). Only R-1(50)/R-2(79)/R-3(161)
   + implausible O(326)/C(211)/B(135)/LB(3) appear as chars. A residential township cannot have 326 Office
   + 211 "C" areas — these single letters are fragments of OTHER map text (streets/title/notes), not zone
   labels. **The actual zone labels + the legend are rendered as VECTOR OUTLINES (ArcMap label-to-curve),
   not extractable text** — so color→zone cannot be read authoritatively, and the ML needle zone is
   invisible to text extraction.
2. **Fills are shattered into fragments** (42,926 curves for a zoning map = each zone area is hundreds of
   tiny path fragments, not clean polygons). Per-fragment "smallest containing polygon" label assignment is
   noise → the derived color→zone map has purity **0.44 on the dominant color** (gray 0.882, 337k area →
   O/C/B mixed) and 20-30% contamination on the residential yellows. The dominant gray is implausibly
   "office" — almost certainly a base/ROW/section-grid layer, not a zone, whose fragments overlap everything.
3. **No color reliably = ML.** The needle (ML light-manufacturing, warehousing-by-right → ss/mw conditional
   per §42-3.1.12) cannot be isolated by color or label. Binding would produce wrong zones AND still miss
   the needle — worst of both.

## No reliable alternative zoning source
- **Oakland County GIS** (gisservices.oakgov.com) — Enterprise has `EnterpriseOpenPlanningMapService`
  (Development Authority / Student Safety / **Current Land Use**) + `EnterpriseLandUseMapService`. **Land USE,
  not zoning** — no ML/RP regulatory districts, no municipal zoning polygons. Confirms the memory's
  "Bloomfield = PDF-only" ([[project_bloomfield_twp_mi]]).
- No municipal zoning FeatureServer found.

## CONFIDENCE: UNUSABLE for an autonomous bind. Recommended unblock (in order):
1. **Obtain the Bloomfield Twp zoning SHAPEFILE/geodatabase** from the Township planning dept (FOIA / direct
   ask) — the authoritative georeferenced source; then centroid-bind (trivial, reliable).
2. **OCR digitize**: rasterize the PDF at ~300 DPI, OCR the LEGEND swatch key (color→zone incl. ML/RP/A-#)
   AND the on-map labels (they're vector outlines, so pixel-OCR is required, not text extraction); then
   union fill fragments by color, georeference (affine via township boundary + road-intersection control
   points), centroid-join. Larger build; still needs the gray-base-layer disambiguation.
3. **Paste-spec**: a human reads the PDF legend → provides the color→zone key (esp. which color = ML) + the
   ML district location(s); then the fragment-union + centroid-join is straightforward.

## Handoff
- **jid 15ecf7aa: grounded needles = 0 (STOP — not bound).** The digitize is UNUSABLE at the accuracy
  needed; ML needle unlocatable from this PDF; no GIS zoning layer exists. Parcels/ring/PIN/ML-verdict-text
  remain pre-staged and ready the moment a reliable zoning geometry (shapefile or OCR'd+validated digitize)
  is in hand. No DB writes; no re-score/CoStar.
