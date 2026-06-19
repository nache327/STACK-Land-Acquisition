# Allegheny PA Per-Muni Source Probe

**Date:** 2026-06-19  
**Status:** Read-only diagnostic. No code, ingest, matrix authoring, or spatial joins performed.  
**Context:** Allegheny Phase 7F.1 parcel ingest merged in PR #315. Phase 7F.2 per-muni registrations are queued. This probe re-checks whether any of the five pre-staged LOW Path B munis from `docs/AUDIT_NOTES/allegheny_pa_citation_directory.md` can be promoted to live FeatureServer / HIGH Path A before Phase 7F.3.

## Bottom Line

| Muni | 57-list direct? | Verdict | Live source | Code field | Probe result | Lane A estimate |
| --- | --- | --- | --- | --- | --- | ---: |
| Fox Chapel Borough | **YES** | **DEFER LOW Path B / MapLink** | No ArcGIS FeatureServer found; eCode360 MapLink/ZoningHub exists | N/A | ZoningHub UI + PDFs/code only in this pass | 2-4h unless a ZoningHub extraction primitive exists |
| O Hara Township | No | **DEFER LOW Path B** | No FeatureServer found | N/A | eCode360 + zoning-map PDF | 2-4h |
| Aspinwall Borough | No | **PROMOTE to HIGH Path A** | `https://services6.arcgis.com/Fm86weLSHlxbP80W/arcgis/rest/services/Aspinwall_Borough_Zoning_Map/FeatureServer/11` | `Zoning` | 1,242 queryable polygon/parcel-like features; 10 distinct zoning values | 30-60 min plus preview gates |
| Sewickley Borough | No | **PROMOTE to HIGH Path A with vintage QA** | `https://services1.arcgis.com/Ps1YVQiv5JQLIFu2/arcgis/rest/services/SW_ZONING_5-5-14/FeatureServer/0` | `ZONE` | 26 queryable zoning polygons; 9 distinct zoning values; 2014 vintage | 45-75 min plus current-map spot check |
| Sewickley Heights Borough | No | **DEFER PDF-tooling** | No FeatureServer found | N/A | Land-ordinance Google Drive PDFs only | Defer or 3-6h PDF/manual source path |

**Net:** 2 of 5 munis promote from LOW Path B to HIGH Path A. The promotion does **not** solve the primary 58-list Fox Chapel polygon, but it can save 1-2h and produce cleaner add-on flips for Aspinwall and Sewickley. Fox Chapel remains the strategic proof target; Aspinwall and Sewickley are the best technical confidence targets.

## Phase 7F.3 Sequencing Recommendation

1. **Fox Chapel Borough** - keep first if Master prioritizes the direct 58-list polygon. Use eCode360 + ZoningHub/MapLink + PDF map workflow. No public FeatureServer found in this pass.
2. **Aspinwall Borough** - fire as the first Path A add-on. The source is public, queryable, and has direct ordinance links per feature.
3. **Sewickley Borough** - fire as the second Path A add-on after a quick vintage check against the current eCode zoning map/table attachments. The data is public and clean, but the service name and edit timestamp indicate 2014 source vintage.
4. **O Hara Township** - keep LOW Path B. It is larger than the boroughs, useful corridor breadth, but still PDF/code workflow.
5. **Sewickley Heights Borough** - defer unless Master specifically values the small high-end enclave; it resembles the Wayzata/GeoPDF tooling problem more than a Lane A Path A sprint.

If Master wants the fastest operational count rather than direct 58-list impact, Aspinwall + Sewickley can run before Fox Chapel. If Master wants the campaign polygon first, Fox Chapel remains first despite source friction.

## Probe Notes

### WPRDC / county search

WPRDC package search for `zoning Allegheny` returned county parcels, county boundary, hydro, parks, trails, etc., but no municipal zoning dataset for these five munis. The Allegheny County GIS open-data stack remains a parcel/municipal-boundary source, not a county zoning source.

## Fox Chapel Borough

| Field | Value |
| --- | --- |
| Predicted prod_city_value | `Fox Chapel Borough` |
| Parcel key from prior directory | `MUNICODE=868`, 2,179 parcels |
| Current source verdict | **DEFER LOW Path B / MapLink** |
| Public FeatureServer found? | **NO** |
| Best zoning UI source | `https://fo2332.zoninghub.com/` |
| eCode zoning chapter | `https://ecode360.com/31904910` |
| Fox Chapel forms page | `https://www.fox-chapel.pa.us/201/Forms-Applications` |
| Known district count | 5 core districts: `A`, `B`, `C`, `D`, `I-O` |

Evidence:

- Fox Chapel's forms page links **"MapLink: Visual Zoning Service"** to `fo2332.zoninghub.com`.
- eCode360 Chapter 400 states that an interactive zoning map is available online and includes zoning-map attachments.
- ArcGIS Online search for `"Fox Chapel" zoning`, `"Fox Chapel" "FeatureServer"`, and `"Fox Chapel" "zoninghub"` did not surface a relevant Fox Chapel zoning FeatureServer. The only `"Fox Chapel"` Feature Service result was an unrelated/test "Urban Design Database" item.
- `fo2332.zoninghub.com` loads a modern ArcGIS-powered UI bundle, but no stable public ArcGIS FeatureServer or documented bulk API endpoint surfaced in this time-box.

Recommendation:

Keep Fox Chapel as LOW Path B unless Lane A has or builds a ZoningHub extraction primitive. For the current Allegheny wave, treat MapLink as a high-quality visual/citation aid, not as a proven Class A polygon service. Because Fox Chapel is the direct 58-list polygon, it still leads the campaign-value sequence.

## O Hara Township

| Field | Value |
| --- | --- |
| Predicted prod_city_value | `O Hara Township` |
| Parcel key from prior directory | `MUNICODE=931`, 4,348 parcels |
| Current source verdict | **DEFER LOW Path B** |
| Public FeatureServer found? | **NO** |
| Zoning page | `https://www.ohara.pa.us/zoning-hearing-board/pages/zoning-code-zoning-map-and-zoning-hearing-board-application` |
| eCode zoning chapter | `https://ecode360.com/31391570` |
| Zoning map PDF | `https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf` |

Evidence:

- O'Hara's zoning page links the eCode360 Chapter 455 zoning code and a zoning-map PDF.
- ArcGIS Online searches for `"O Hara Township" "FeatureServer"`, `"O'Hara" zoning`, `"oharatwp" "ArcGIS"`, and Pittsburgh/Allegheny open-data searches did not surface a municipal zoning FeatureServer.
- Web search results pointed back to the eCode/PDF workflow.

Recommendation:

Keep O'Hara behind Fox Chapel and the two promoted Path A boroughs. It is valuable corridor breadth, but the current source path is still manual PDF/code extraction.

## Aspinwall Borough

| Field | Value |
| --- | --- |
| Predicted prod_city_value | `Aspinwall Borough` |
| Parcel key from prior directory | `MUNICODE=801`, 1,125 parcels |
| Current source verdict | **PROMOTE to HIGH Path A** |
| Dashboard | `https://www.arcgis.com/apps/dashboards/de9fef3f21a34f5ba63f9f398c32bf79` |
| Web map item | `ba1ae47775154cef876d7101403b41d2` |
| Feature service item | `0395f9ab078740a79553e7be98425d6d` |
| FeatureServer layer | `https://services6.arcgis.com/Fm86weLSHlxbP80W/arcgis/rest/services/Aspinwall_Borough_Zoning_Map/FeatureServer/11` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | `3365` |
| Code field | `Zoning` |
| Feature count | 1,242 |
| Distinct code values | 10 |
| Modified timestamp from ArcGIS item | 2023-09-08 UTC-equivalent from `1694183033000` |

Layer fields:

| Field | Meaning |
| --- | --- |
| `Zoning` | Zoning district code |
| `Ordinance` | eCode360 ordinance/deep link |
| `App` | Borough forms/applications link |
| `MAPBLOCKLO`, `PIN`, `MUNICODE` | Parcel identifiers / muni key |
| `FID` | Object ID |

Distinct codes from live query:

```text
A-CD, AC-1, AC-2, AI-1, AR-1, AR-2, AR-3, AR-4, AR-S, Riverfront Overlay District
```

Sample rows returned cleanly:

```json
{
  "Zoning": "AR-4",
  "Ordinance": "https://ecode360.com/31329828#31329828",
  "PIN": "0170N00054000900",
  "MUNICODE": 801
}
```

Important shape note:

The Aspinwall layer appears **parcel-like** rather than dissolved district polygons: 1,242 features for a 1,125-parcel muni, with `PIN` and `MAPBLOCKLO` populated. That is still usable for a spatial backfill or direct parcel-zone assignment if Lane A confirms geometry alignment, but it is not a classic small district-polygon layer. Run the strengthened preview gates before assuming 100% coverage:

- bbox covers >= 50% of Aspinwall parcel bbox
- 1,000-parcel or full-muni `ST_Within` dry-run >= 50% match
- verify `MUNICODE=801` or geometry confined to Aspinwall

Recommendation:

Promote Aspinwall to HIGH Path A. This is the cleanest newly discovered Allegheny source. Expected Lane A wall-clock: **30-60 min** after jurisdiction registration, plus audit refresh and matrix apply.

## Sewickley Borough

| Field | Value |
| --- | --- |
| Predicted prod_city_value | `Sewickley Borough` |
| Parcel key from prior directory | `MUNICODE=851`, 1,699 parcels |
| Current source verdict | **PROMOTE to HIGH Path A with vintage QA** |
| Borough official zoning map page | `https://www.sewickleyborough.org/391/Official-Zoning-Map` |
| Web map item | `2090974c68ca4175bcb4df423adbab70` |
| Feature service item | `f61bd1153f2e449ab5e9aa51fed5c634` |
| FeatureServer layer | `https://services1.arcgis.com/Ps1YVQiv5JQLIFu2/arcgis/rest/services/SW_ZONING_5-5-14/FeatureServer/0` |
| Geometry | `esriGeometryPolygon` |
| Spatial reference | Web Mercator `102100` / `3857` |
| Code field | `ZONE` |
| Description field | `Z_DESC` |
| Feature count | 26 |
| Distinct code values | 9 |
| Modified timestamp from ArcGIS item | 2014-07-28 UTC-equivalent from `1406560344000` |

The public Web Map exposes a full zoning layer plus parcel and overlay layers:

```text
ZONING: http://services1.arcgis.com/Ps1YVQiv5JQLIFu2/arcgis/rest/services/SW_ZONING_5-5-14/FeatureServer/0
LOT LINES: http://services1.arcgis.com/Ps1YVQiv5JQLIFu2/arcgis/rest/services/SW_PARCELS_5-5-14/FeatureServer/0
```

Distinct zoning values from live query:

```text
C-1, C-2, I, INST., OMU, OS, R-1, R-1A, R-2
```

Sample rows returned cleanly:

```json
{
  "ZONE": "C-2",
  "Z_DESC": "HIGHWAY COMMERCIAL",
  "ACRES": 2.7714
}
```

Vintage risk:

The service name is `SW_ZONING_5-5-14`, and ArcGIS item metadata indicates a 2014 modified timestamp. Sewickley's current eCode chapter has active attachments for the zoning map and land-use tables. Before binding operational coverage, Lane A should spot-check:

- current eCode attachment codes still match `C-1`, `C-2`, `I`, `INST.`, `OMU`, `OS`, `R-1`, `R-1A`, `R-2`
- no district was renamed or added since 2014
- service extent matches the current municipal boundary

Recommendation:

Promote Sewickley to HIGH Path A, but with **source-vintage QA** before final audit. Expected Lane A wall-clock: **45-75 min**.

## Sewickley Heights Borough

| Field | Value |
| --- | --- |
| Predicted prod_city_value | `Sewickley Heights Borough` |
| Parcel key from prior directory | `MUNICODE=869`, 452 parcels |
| Current source verdict | **DEFER PDF-tooling** |
| Public FeatureServer found? | **NO** |
| Land ordinances page | `https://www.sewickleyheightsboro.com/generalgovernment/land-ordinances` |
| Primary zoning source | Ordinance No. 294 amended/restated zoning ordinance PDF |

Evidence:

- The borough land-ordinance page lists Ordinance No. 294 as the amended/restated zoning ordinance, hosted as a Google Drive file.
- ArcGIS Online searches for `"Sewickley Heights" "FeatureServer"` and `"Sewickley Heights" "ArcGIS" "zoning"` did not surface a municipal zoning FeatureServer.
- This remains the highest-friction source in the five-muni Allegheny set.

Recommendation:

Defer Sewickley Heights unless Master specifically wants the tiny high-value enclave. It resembles the Wayzata GeoPDF/PDF-source problem more than an ArcGIS Path A sprint. Expected wall-clock is **3-6h minimum** if tackled manually, despite the small parcel count.

## Final Verdict

| Category | Munis |
| --- | --- |
| Promote to HIGH Path A | Aspinwall Borough, Sewickley Borough |
| Keep LOW Path B | Fox Chapel Borough, O Hara Township |
| Defer PDF-tooling | Sewickley Heights Borough |

The best tactical plan is **hybrid**:

- Run **Fox Chapel** first if Master wants direct 58-list progress.
- Run **Aspinwall + Sewickley** next as low-friction operational add-ons.
- Keep **O Hara** as optional corridor breadth.
- Defer **Sewickley Heights** until PDF/GeoPDF tooling exists or Master explicitly prioritizes it.

Expected savings versus the all-LOW baseline: **1-2h**, plus better truthfulness for Aspinwall and Sewickley because their zone values come from queryable live GIS rather than manual map interpretation.

## Source Links

- Fox Chapel forms page with MapLink: `https://www.fox-chapel.pa.us/201/Forms-Applications`
- Fox Chapel eCode Chapter 400: `https://ecode360.com/31904910`
- Fox Chapel ZoningHub / MapLink: `https://fo2332.zoninghub.com/`
- O'Hara zoning page: `https://www.ohara.pa.us/zoning-hearing-board/pages/zoning-code-zoning-map-and-zoning-hearing-board-application`
- O'Hara eCode Chapter 455: `https://ecode360.com/31391570`
- O'Hara zoning map PDF: `https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf`
- Aspinwall dashboard: `https://www.arcgis.com/apps/dashboards/de9fef3f21a34f5ba63f9f398c32bf79`
- Aspinwall FeatureServer layer: `https://services6.arcgis.com/Fm86weLSHlxbP80W/arcgis/rest/services/Aspinwall_Borough_Zoning_Map/FeatureServer/11`
- Aspinwall eCode Chapter 27: `https://ecode360.com/30911259`
- Sewickley official zoning map page: `https://www.sewickleyborough.org/391/Official-Zoning-Map`
- Sewickley Web Map item: `https://www.arcgis.com/home/item.html?id=2090974c68ca4175bcb4df423adbab70`
- Sewickley FeatureServer layer: `https://services1.arcgis.com/Ps1YVQiv5JQLIFu2/arcgis/rest/services/SW_ZONING_5-5-14/FeatureServer/0`
- Sewickley eCode Chapter 330: `https://ecode360.com/32411085`
- Sewickley Heights land ordinances: `https://www.sewickleyheightsboro.com/generalgovernment/land-ordinances`
- WPRDC search baseline: `https://data.wprdc.org/`
