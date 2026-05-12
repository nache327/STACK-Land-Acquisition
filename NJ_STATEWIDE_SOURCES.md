# NJ Statewide Discovery Research

**Date**: 2026-05-12
**Status**: Read-only probe. No code in scope.

The Bergen 70-town sweep with scoring v2 produced a clean shortlist
(26 towns at confidence ≥ 70; 59% reduction in operator queue noise)
but only 2 verifiable per-town candidates surfaced via ArcGIS Hub
(Paramus, New Milford). Hub-only discovery for the remaining ~68
Bergen towns hits diminishing returns — most towns don't publish
zoning to Hub in a discoverable shape.

This doc probes higher-leverage non-Hub paths so future ingestion
sprints know which doors are worth opening. Read-only; produces
candidate URLs + access notes + expected coverage impact.

---

## 1. NJ Office of GIS (NJOGIS) — gisdata-njdep portal

**URL probed**: `https://gisdata-njdep.opendata.arcgis.com/api/feed/dcat-us/1.1.json`

**Result**: 573 published datasets. **0 zoning-titled.**

NJOGIS / NJDEP publish environmental, cadastral (tidelands only),
transportation, and habitat layers — no statewide zoning aggregator.

**Verdict**: No usable source. Skip.

---

## 2. NJDEP iMapNJ Land Use / Land Cover

**URL probed**:
`https://mapsdep.nj.gov/arcgis/rest/services/Features/Land_lu/MapServer`

**Result**: 17 polygon layers. The most relevant:
- Layer 1: **Land Use 2012 Generalized** (statewide, polygon)
- Layer 13: **Land Use 2015** (most recent statewide)
- Layer 0: Land Use Change 2007–2012
- Layer 2: Wetlands (2012)
- Layer 3: Impervious Surface (2012)

**Critical caveat**: This is **physical land cover** (residential,
commercial, forest, wetlands), **not regulatory zoning**.
Land-cover and zoning are different concepts — a "residential" land-
cover polygon doesn't tell you the regulatory zone (R-100 vs R-A1 vs
RM-2 etc.), and a vacant lot in a commercial zone shows up as
"upland" land cover.

**Use case**: Could feed `parcel_use_category` (a coarser categorical
field than `zone_code`) as a fallback signal for buybox queries when
real zoning data is missing. Would NOT replace per-town zoning ingest
for the self-storage matrix work.

**Expected coverage impact**: Adds a polygon-class signal to ALL ~3.2M
NJ parcels (statewide LULC is complete). Does NOT contribute to
`parcels.zoning_code` or `zoning_districts` populations.

**Verdict**: Moderate value as a fallback / supplementary signal.
Build cost: ~2-3 days for an LULC adapter that writes to a new
`parcel_lulc_class` column. **Recommend deferring** until per-town
ingest hits a hard ceiling AND buybox queries demonstrate value
from coarse land-cover.

---

## 3. data.nj.gov (Socrata open-data portal)

**URL probed**: `https://data.nj.gov/api/catalog/v1?q=zoning`

**Result**: 5,201 hits, but the catalog is the **Socrata DiscoverNet
federation** — the top-N hits are Cook County IL, Nova Scotia,
Annapolis County, and other non-NJ municipalities.

NJ-scoped open data on data.nj.gov is dominated by COVID, vaccination,
financial-disclosure, and education datasets — not GIS/zoning.

**Filtered search**: even after narrowing to "zoning municipal nj",
no statewide NJ zoning aggregator appears.

**Verdict**: No usable source. Skip.

---

## 4. NJ Geographic Information Network (NJGIN)

**URL probed**: `https://njgin.nj.gov/njgin/edata/njogis/`

**Result**: HTML portal with NOINDEX/NOFOLLOW. Not a programmatic API.
The portal is a human-facing data catalog that publishes ZIP-bundled
shapefiles via authenticated download links.

**Verdict**: Possible if we add a Shapefile-download + unzip adapter,
but the actual content overlaps with NJOGIS (1) and NJDEP (2). Skip
unless a specific NJGIN-only resource is identified.

---

## 5. Per-county MOD-IV (NJ Tax Records)

**Not directly probed**. NJ's MOD-IV (Modular Information Validation)
is the statewide parcel-and-tax data backbone, published per-county
annually. Bergen's MOD-IV is at
`https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0` — already in use as Bergen's `parcel_endpoint`.

MOD-IV gives parcels + assessed value + owner — but **no zoning_code**.
Some counties enrich their MOD-IV publish with municipal zoning
overlays; Bergen's published service does not include zoning fields.

**Verdict**: Already in use for parcels. No incremental value for
zoning.

---

## 6. NJ State Plan / SDRP (State Development & Redevelopment Plan)

**URL probed**:
`https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/New_Jersey_Planning_Viewer_Basemap/FeatureServer`

**Result**: 20 layers, all emergency-services and infrastructure
(FEMA facilities, fire stations, EOC, medical facilities).
**Zero zoning content.**

**Verdict**: No usable source. Skip.

---

## 7. Per-municipal town websites (last resort)

For the ~65 Bergen towns with no Hub-discoverable zoning, the last
remaining path is per-town website scraping. Pattern: each town's
`.gov` site has a `/zoning-map` or `/land-use` page that often embeds
an ArcGIS service URL (or links to a PDF zoning map).

**Feasibility**:
- Reliable for the larger Bergen towns (Englewood, Hackensack,
  Teaneck, Fair Lawn) — they all have public GIS portals.
- Smaller boroughs (Saddle River, Rockleigh, Norwood) often only
  publish PDF maps, which require manual digitization.

**Build cost**: ~4–8 hrs per town for the bigger ones (scrape +
schema-mapping); 0 for the long tail (skip until manual ingest is
worth the effort).

**Recommend**: Defer. The operator-manual-entry queue (Phase 2's
`POST /_sources/_review?action=verify` with a manual URL paste) is
sufficient for the ad-hoc cases.

---

## Roll-up: ranked recommendations

| Rank | Path | Build cost | Coverage impact | Recommend |
|---|---|---|---|---|
| 1 | NJDEP LULC as a fallback `parcel_lulc_class` adapter | Medium | Adds a coarse-class signal to ALL ~3.2M NJ parcels | **Defer** — only build if buybox queries demonstrate value |
| 2 | Per-town municipal-website scraper for top-10 Bergen towns | High (per-town) | +30–60k parcels potentially | **Defer** — manual-entry queue is sufficient for now |
| 3 | NJ MOD-IV per-county adapter (parcels only) | Already done | N/A | Skip |
| 4 | NJOGIS / data.nj.gov / SDRP statewide search | N/A | None — no zoning content exists | Skip |

**Conclusion**: There is **no public statewide NJ zoning aggregator**.
NJ's municipal-home-rule means zoning lives at the town level, and
the discovery service's per-town loop (now hardened with v2 scoring +
operator deny-list) is the right primitive.

The remaining lever for NJ coverage is **operational, not algorithmic**:
- Bulk-reject scoring v2's still-noisy 70-79 confidence bucket
- Manual-entry of known town zoning URLs for the towns operators care
  about (e.g. paste Englewood, Hackensack, Teaneck via `_review`)
- Per-town website scraping ONLY if a specific town becomes a sales
  priority

If a specific NJ deal requires a town not yet covered, the right move
is operator-driven manual URL entry, not building another adapter.

---

## Out-of-state extrapolation

For comparison, the pattern in other home-rule states:

| State | Statewide zoning? | Notes |
|---|---|---|
| NJ | None | This doc — pure per-town |
| NY | None | Similar to NJ; per-town/per-village |
| CT | None | Per-town; CT-ECO has LULC like NJDEP |
| MA | **MassGIS** has municipal boundaries + some zoning | Better source landscape; worth a future probe |
| PA | Per-municipality (130+ in Allegheny) | Mont PA covered via county-level; rest is per-muni |
| CO | County zones unincorporated + each city zones itself | Mixed |
| TX | None statewide; per-county or per-city | TN/AZ similar |

**MassGIS** (#4 above) appears to have a more mature statewide
zoning aggregation. If MA enters scope, probe that first before
committing to per-town work.
