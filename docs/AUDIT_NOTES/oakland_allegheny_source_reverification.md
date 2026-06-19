# Oakland MI + Allegheny PA Source Re-Verification

**Date:** 2026-06-19  
**Status:** Read-only diagnostic. No code, ingest, matrix authoring, or spatial joins performed.  
**Purpose:** Freshen source assumptions immediately before Lane A fires Oakland Phase 7E.3 and Allegheny Phase 7F.3. This responds to Maricopa source-quality drift and the Greenwich precedent where fire-time live probing promoted a LOW Path B muni to HIGH Path A.

## Bottom Line

| County / muni | Prior verdict | Fresh verdict | Live query result | Action |
| --- | --- | --- | --- | --- |
| Oakland / Birmingham | HIGH Path A | **Still HIGH Path A** | `400` polygons, `district` field, 21 distinct nonblank codes | Fire as planned |
| Oakland / Bloomfield Hills | HIGH Path A | **Still HIGH Path A** | `1,853` polygon/parcel-like features, `Zoning` field, 13 distinct codes | Fire as planned |
| Oakland / Beverly Hills | HIGH Path A | **Still HIGH Path A** | `322` polygons, `Zoning` field, 12 nonblank codes plus blank value | Fire as planned; filter blanks |
| Oakland / Bloomfield Township | LOW Path B | **Still LOW Path B** | No municipal zoning FeatureServer found; county composite plan is land-use, not zoning | Do not promote |
| Oakland / Franklin | LOW Path B | **Still LOW Path B** | No municipal zoning FeatureServer found; county composite plan is land-use, not zoning | Do not promote |
| Allegheny / Aspinwall | HIGH Path A from PR #317 | **Still HIGH Path A** | `1,242` features, `Zoning` field, 10 distinct codes | Fire as planned |
| Allegheny / Sewickley | HIGH Path A from PR #317 | **Still HIGH Path A** | `26` polygons, `ZONE` field, 9 distinct codes | Fire as planned with 2014 vintage QA |

**Verdict:** No source-quality regression found. Oakland 7E.3 can proceed with the original three Path A munis: Birmingham, Bloomfield Hills, and Beverly Hills. Bloomfield Township and Franklin remain LOW Path B. Allegheny's two promoted Path A sources from PR #317 are still live and queryable.

## Oakland MI

### Birmingham

| Field | Value |
| --- | --- |
| Source | `https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0` |
| Query status | **LIVE** |
| Geometry | `esriGeometryPolygon` |
| Code field | `district` |
| Count | `400` |
| Distinct nonblank codes | 21 |

Distinct values:

```text
0-1, 0-2, B-1, B-2, B-2B, B-3, B-4, MX, P, PP, R1, R1-A, R2, R3, R4, R5, R6, R7, R8, TZ-1, TZ-3
```

Source freshness verdict: **still fireable**. The `0-1` / `0-2` numeric-zero caveat from PR #260 remains active; matrix rows must match the ingested source value exactly.

### Bloomfield Hills

| Field | Value |
| --- | --- |
| Source | `https://services9.arcgis.com/jGlVpYnGiHmSg9fR/arcgis/rest/services/Zoning_BloomfieldHills/FeatureServer/0` |
| Query status | **LIVE** |
| Geometry | `esriGeometryPolygon` |
| Code field | `Zoning` |
| Count | `1,853` |
| Distinct codes | 13 |

Distinct values:

```text
A-1, A-2, A-3, A-3-1, A-4, A-6, B-1, C-1, I-1, O-1, O-2, P-1, RR
```

Source freshness verdict: **still fireable**. The layer still has parcel-like geometry and `PIN`/tax fields, matching the prior PR #260 characterization.

### Beverly Hills

| Field | Value |
| --- | --- |
| Source | `https://services5.arcgis.com/1PnnJue8khcujdxm/arcgis/rest/services/Zoning_Dissolved/FeatureServer/0` |
| Query status | **LIVE** |
| Geometry | `esriGeometryPolygon` |
| Code field | `Zoning` |
| Count | `322` |
| Distinct values including blank | 13 |

Distinct values:

```text
" ", B, O-1, P, PP, R-1, R-1A, R-2, R-2A, R-2B, R-3, R-A, RM
```

Source freshness verdict: **still fireable** with the same blank-value filter requirement from PR #260. Lane A should exclude blank/whitespace `Zoning` values during district ingest or backfill.

### Bloomfield Township + Franklin

ArcGIS Online searches rerun:

```text
"Bloomfield Township" "zoning" "FeatureServer"
"Bloomfield Township" "ArcGIS" zoning
"BloomfieldTwp" zoning FeatureServer
"Franklin MI" zoning FeatureServer
"Village of Franklin" "ArcGIS" zoning
"Franklin Michigan" "zoning" "FeatureServer"
```

No municipal zoning FeatureServer surfaced for either LOW Path B muni.

The only potentially relevant county-level hit was:

```text
https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseLandUseMapService/MapServer/15
```

That layer is **not zoning**. It is named `Composite Master Plan`, has `COMPOSITEPLAN` and `LOCALFIPS` fields, and returned sample values like:

```text
Commercial/Office
Single Family, 14,000 to 43,559 sq. ft.
Recreation/Conservation
```

with `557,327` countywide features. Treat it as planning/future-land-use data, not a zoning-code source. Do **not** promote Bloomfield Township or Franklin from this layer.

## Allegheny PA

### Aspinwall

| Field | Value |
| --- | --- |
| Source | `https://services6.arcgis.com/Fm86weLSHlxbP80W/arcgis/rest/services/Aspinwall_Borough_Zoning_Map/FeatureServer/11` |
| Query status | **LIVE** |
| Code field | `Zoning` |
| Count | `1,242` |
| Distinct codes | 10 |

Distinct values:

```text
A-CD, AC-1, AC-2, AI-1, AR-1, AR-2, AR-3, AR-4, AR-S, Riverfront Overlay District
```

Source freshness verdict: **still fireable**. Same caveat as PR #317: this layer is parcel-like, not dissolved district polygons, so Lane A should run the strengthened bbox + `ST_Within` preview gate before binding coverage.

### Sewickley

| Field | Value |
| --- | --- |
| Source | `https://services1.arcgis.com/Ps1YVQiv5JQLIFu2/arcgis/rest/services/SW_ZONING_5-5-14/FeatureServer/0` |
| Query status | **LIVE** |
| Code field | `ZONE` |
| Count | `26` |
| Distinct codes | 9 |

Distinct values:

```text
C-1, C-2, I, INST., OMU, OS, R-1, R-1A, R-2
```

Source freshness verdict: **still fireable** with the PR #317 vintage caveat. The `5-5-14` layer remains queryable, but Lane A should spot-check current eCode attachments before treating it as authoritative.

## Final Recommendation

1. **Oakland Phase 7E.3:** proceed with Birmingham + Bloomfield Hills + Beverly Hills as HIGH Path A. Keep Bloomfield Township and Franklin in LOW Path B / PDF-code workflow; no new promotion surfaced.
2. **Allegheny Phase 7F.3:** proceed with Aspinwall + Sewickley as HIGH Path A. Keep Fox Chapel and O Hara as LOW Path B, and Sewickley Heights deferred per PR #317.
3. **No emergency pivot needed.** The Maricopa/PV source-gating drift did not reproduce on these Oakland or Allegheny sources during this probe.

## Source Links

- Birmingham zoning layer: `https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0`
- Bloomfield Hills zoning layer: `https://services9.arcgis.com/jGlVpYnGiHmSg9fR/arcgis/rest/services/Zoning_BloomfieldHills/FeatureServer/0`
- Beverly Hills zoning layer: `https://services5.arcgis.com/1PnnJue8khcujdxm/arcgis/rest/services/Zoning_Dissolved/FeatureServer/0`
- Oakland county composite land-use layer: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseLandUseMapService/MapServer/15`
- Aspinwall zoning layer: `https://services6.arcgis.com/Fm86weLSHlxbP80W/arcgis/rest/services/Aspinwall_Borough_Zoning_Map/FeatureServer/11`
- Sewickley zoning layer: `https://services1.arcgis.com/Ps1YVQiv5JQLIFu2/arcgis/rest/services/SW_ZONING_5-5-14/FeatureServer/0`
- Prior Oakland pre-stage: `docs/AUDIT_NOTES/oakland_mi_citation_directory.md`
- Prior Allegheny source probe: `docs/AUDIT_NOTES/allegheny_pa_per_muni_source_probe.md`
