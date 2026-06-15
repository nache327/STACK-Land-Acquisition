# Hennepin County, MN — Wealth-Pocket Citation Directory (Pre-Stage)

**Date:** 2026-06-15
**Purpose:** Pre-stage citation sources for the Hennepin MN matrix sprint after Lane A lands the Tier 2 MetroGIS parcel adapter + municipal zoning proof. Target municipalities are Edina and Wayzata from the 57-list, plus Minnetonka, Plymouth, and Eden Prairie as adjacent high-value Hennepin wealth-band candidates.
**Status:** Read-only diagnostic. **Not authoritative until Lane A's Hennepin ingest output lands.** `prod_city_value` values below are predictions from MetroGIS `CTU_NAME`; verify them against prod after ingest before authoring matrix rows.

---

## Bottom line

| Muni set | Count |
|---|---:|
| Municipalities staged | 5 |
| Estimated zoning-code backlog | ~121-125 codes |
| Bergen-pattern fit | 2 YES / 3 PARTIAL / 0 NO |
| Expected matrix sprint hours at 5-10 min/code | ~10-21h raw authoring |
| Direct 57-list proof scope | Edina + Wayzata: ~60 codes, roughly 5-10h |
| Adjacent wealth-band add-on | Minnetonka + Plymouth + Eden Prairie: ~61-65 codes, roughly 5-11h |

**Recommendation:** Start with **Edina** as the cleanest source-population proof because it has a city zoning layer with `PID` + `Zoning` values that match MetroGIS parcel identity. Add **Wayzata** for direct 57-list coverage, but treat Wayzata as ordinance/PDF-map unless Lane A finds a live zoning layer. If Lane A's adapter proof is healthy, **Plymouth** and **Eden Prairie** are strong adjacent add-ons because both publish public ArcGIS zoning layers with `ZONING` fields. **Minnetonka** has a public zoning app/service lead, but it needs Lane A source-query hardening before being treated as a clean Class A primitive.

**MetroGIS carry note:** The same MetroGIS `Parcels_2025` service covers Anoka, Carver, Dakota, Hennepin, Ramsey, Scott, and Washington County, MN. This citation directory only stages Hennepin munis. The carry counties become partial-with-parcels through the same adapter, but zoning remains municipal per county/city.

**Class A/C gate note:** MetroGIS parcels carry assessor use fields (`USECLASS1`, etc.), not zoning district codes. Do not treat `USECLASS1` as embedded zoning. The usable primitive is municipal Class A where a city zoning layer exposes a zone field, plus Class B ordinance/directory support for matrix citations.

---

## Live source probes used

- MetroGIS Hennepin parcels: `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels_2025/FeatureServer/3`
- Edina zoning layer: `https://utility.arcgis.com/usrsvcs/servers/6aeef36d107a4ff9aa765ad8d0baadfb/rest/services/Planning/Zoning/MapServer/2`
- Minnetonka zoning app: `https://logis.maps.arcgis.com/apps/webappviewer/index.html?id=3c97307f8b094eb7bda13873382b7ebc`
- Minnetonka zoning service lead: `https://utility.arcgis.com/usrsvcs/servers/94ae6a63554048f1a0ae99174eaab529/rest/services/Minnetonka/MI_City_Zoning/MapServer/5`
- Plymouth zoning layer: `https://plymap.plymouthmn.gov/webgis/rest/services/ParcelViewer/MapServer/2`
- Plymouth link-backed zoning map layer: `https://plymap.plymouthmn.gov/webgis/rest/services/ZoningMap/MapServer/4`
- Eden Prairie zoning layer: `https://gis.edenprairie.org/mapsb/rest/services/Public/Zoning/MapServer/7`

Live parcel counts by `UPPER(CTU_NAME)=<city>`:

| Predicted prod_city_value | Raw MetroGIS CTU | MetroGIS parcel count |
|---|---|---:|
| `Edina` | `Edina` | 21,372 |
| `Wayzata` | `Wayzata` | 1,976 |
| `Minnetonka` | `Minnetonka` | 20,971 |
| `Plymouth` | `Plymouth` | 29,201 |
| `Eden Prairie` | `Eden Prairie` | 23,019 |

Sample MetroGIS parcel rows confirm `CTU_NAME` is title case and `POSTCOMM` is uppercase. Matrix `municipality` should match the actual prod `parcels.city` after ingest; likely values are the title-case `CTU_NAME` strings above.

Machine-readable zoning-code estimates:

| Municipality | Source | Code count | Sample codes |
|---|---|---:|---|
| Edina | City zoning MapServer `Zoning` | 39 | `R-1`, `R-2`, `RMD`, `PCD-1`, `POD-1`, `MDD-4`, `APD`, `PUD` |
| Wayzata | Ordinance + March 2025 PDF map | ~21 | `R-1`, `R-1A`, `R-2`, `R-2A`, `R-3`, `R-4`, `R-5`, `C-1`, `C-2`, `C-3`, `PUD` |
| Minnetonka | City zoning app/service visible query | >=10 observed | `R-1`, `R-2`, `R-3 PURD`, `R-4`, `B-2`, `I-1`, `PUD` |
| Plymouth | City `ParcelViewer` zoning layer | 23 | `RSF-1`, `RSF-2`, `RSF-3`, `RMF-2`, `C-2`, `I-1`, `PUD`, `P-I` |
| Eden Prairie | City zoning MapServer `ZONING` | 28 | `R1-22`, `R1-13.5`, `RM-6.5`, `C-REG`, `I-GEN`, `OFC`, `P-PARK AND OPEN SPACE` |

---

## How to use this directory

1. After Lane A's Hennepin ingest lands, re-pull actual uncovered zone codes for Hennepin County.
2. Match matrix `municipality` to the actual prod `parcels.city` value. Predicted values here come from MetroGIS `CTU_NAME`, not a live prod row.
3. Confirm whether Lane A populated zoning from a city layer, from a direct `COUNTY_PIN`/`PID` join, or from manually digitized/PDF sources.
4. Watch for aggregator-source-code vs city-source-code drift. MetroGIS is parcel-only, but city zoning services can use parcel-like joined layers with local `PID` and local zone labels. Do not assume all city layers use the same field or vintage.
5. Bias against unclear. Residential, park, public, and institutional districts should default to prohibited for self-storage / mini-warehouse / light industrial / luxury garage condo unless the ordinance explicitly permits the use.

---

## Edina

| Field | Value |
|---|---|
| Display name | Edina, MN |
| Predicted prod_city_value | `Edina` |
| MetroGIS parcel coverage | YES: 21,372 rows |
| City zoning coverage | YES: `Planning/Zoning/MapServer/2`, 20,976 rows in prior spec; live `Zoning` field count 39 distinct codes |
| Canonical ordinance URL | `https://library.municode.com/mn/edina/codes/code_of_ordinances?nodeId=SPBLADERE_CH36ZO` |
| Zoning section anchors | Chapter 36 Zoning; district sections such as R-1 principal/conditional/accessory uses at Secs. 36-433 to 36-435; R-2 principal/accessory uses at Secs. 36-462 to 36-463; planned commercial/office/district articles by code family |
| Bergen-pattern fit | **PARTIAL** |

Edina is the strongest Hennepin proof municipality for zoning-code population. The city layer carries `PID`, `Zoning`, `LandUse`, and `GuidePlan`; `PID` aligns with MetroGIS `COUNTY_PIN` shape. The ordinance is online in Municode, but it is district-section based rather than a single all-zone use table.

Sample zoning rows and citation pattern:

| Sample code | Live/source meaning | Citation pattern |
|---|---|---|
| `R-1` | Single-family detached in city layer samples | Cite Chapter 36, R-1 principal uses Sec. 36-433, conditional uses Sec. 36-434, accessory uses Sec. 36-435. |
| `R-2` | Double dwelling unit district | Cite Chapter 36, R-2 principal/accessory uses Secs. 36-462 to 36-463. |
| `RMD` | Regional medical district family | Cite Chapter 36 district-specific article; spot-check before any permitted classification. |
| `PCD-1` | Planned commercial district family | Cite Chapter 36 planned commercial district sections; commercial edge case. |
| `POD-1` | Planned office district family | Cite Chapter 36 planned office district sections; office edge case. |
| `MDD-4` | Mixed development district family | Cite Chapter 36 MDD sections; mixed-use edge case. |

Sprint note: Edina should be first. Matrix authoring is likely 39 rows, but most residential/PUD variants can be handled with repeated district-section citation patterns.

---

## Wayzata

| Field | Value |
|---|---|
| Display name | Wayzata, MN |
| Predicted prod_city_value | `Wayzata` |
| MetroGIS parcel coverage | YES: 1,976 rows |
| City zoning coverage | No public machine-readable zoning layer found in accepted Hennepin spec time box |
| Canonical ordinance URL | `https://library.municode.com/mn/wayzata/codes/code_of_ordinances` |
| Zoning section anchors | Part IX Zoning; Chapter 937 Zoning Districts Use Table and Performance Standards; district chapters 951+ for residential/commercial districts |
| Zoning map backup | `https://www.wayzata.org/DocumentCenter/View/6010/Wayzata-Zoning-Map-Updated-March-2025` |
| Bergen-pattern fit | **YES** |

Wayzata is the cleanest direct 57-list matrix source, but the zoning-code population source remains manual/PDF unless Lane A finds a city layer. The March 2025 map lists the local zone codes; Municode Chapter 937 provides the permitted/conditional/interim/accessory use table.

Sample zone codes and citation pattern:

| Sample code | Source meaning | Citation pattern |
|---|---|---|
| `R-1A` | Low-density single-family estate | Cite Chapter 937 use table + Chapter 951 district chapter. |
| `R-1` | Low-density single-family residential | Cite Chapter 937 use table + Chapter 952 district chapter. |
| `R-2A` | Single-family residential | Cite Chapter 937 use table + Chapter 953 district chapter. |
| `R-5` | High-density multiple residential | Cite Chapter 937 use table + Chapter 959 district chapter. |
| `C-1` / `C-2` | Commercial district families | Cite Chapter 937 use table + relevant commercial district chapter; spot-check storage/warehouse-like uses. |
| `PUD` | Planned unit development | Cite Chapter 933 PUD and project-specific ordinance if needed. |

Sprint note: expect ~21 codes from the map/spec list. Use Wayzata as the direct 57-list companion after Edina, but do not assume automated zoning backfill without a layer.

---

## Minnetonka

| Field | Value |
|---|---|
| Display name | Minnetonka, MN |
| Predicted prod_city_value | `Minnetonka` |
| MetroGIS parcel coverage | YES: 20,971 rows |
| City zoning coverage | PARTIAL: public zoning app resolves to a city MapServer with joined zoning field; simple default query returned samples, but pagination/distinct querying is limited |
| Canonical ordinance URL | `https://codelibrary.amlegal.com/codes/minnetonka/latest/minnetonka_mn/0-0-0-20634` |
| Zoning section anchors | Chapter 3 Zoning Regulations; Sec. 300.10 R-1; Sec. 300.11 R-2; Sec. 300.12 R-3; Sec. 300.13 R-4; Sec. 300.14 R-5; Secs. 300.17 to 300.20 business/industrial; Sec. 300.22 PUD |
| City zoning page | `https://www.minnetonkamn.gov/government/departments/community-development/planning-zoning/zoning` |
| Bergen-pattern fit | **PARTIAL** |

Minnetonka is more source-ready than the initial acquisition spec implied, but still needs Lane A hardening. The city page links to a zoning map application, whose backing web map points to `MI_City_Zoning/MapServer/5`. That layer exposes `MI.CommDev_Zoning_LandUse.Zoning` joined to parcel `PID`, but the service rejects pagination and needs a careful adapter query strategy.

Sample zoning rows and citation pattern:

| Sample code | Live/source meaning | Citation pattern |
|---|---|---|
| `R-1` | Low-density residential | Cite Chapter 3, Sec. 300.10 R-1. |
| `R-2` | Low-density residential | Cite Chapter 3, Sec. 300.11 R-2. |
| `R-3 PURD` | Residential/PUD variant | Cite Sec. 300.12 plus Sec. 300.22 PUD if suffix survives ingest. |
| `R-4` | Medium-density residential | Cite Chapter 3, Sec. 300.13 R-4. |
| `B-2` | Limited business district family | Cite Chapter 3, Sec. 300.18 B-2; spot-check commercial/storage uses. |
| `I-1` | Industrial district | Cite Chapter 3, Sec. 300.20 I-1; likely the first code needing real use classification, not blanket prohibited. |
| `PUD` | Planned unit development | Cite Chapter 3, Sec. 300.22 and project-specific terms if available. |

Sprint note: treat observed code count as **>=10**, not a final unique-code count. The ordinance itself has roughly R-1 through R-5, B-1 through B-3, I-1, PUD, overlays, and hybrid PURD forms.

---

## Plymouth, MN

| Field | Value |
|---|---|
| Display name | Plymouth, MN |
| Predicted prod_city_value | `Plymouth` |
| MetroGIS parcel coverage | YES: 29,201 rows |
| City zoning coverage | YES: public `ParcelViewer/MapServer/2` exposes `ZONING`; `ZoningMap/MapServer/4` also exposes link-backed zoning rows |
| Canonical ordinance URL | `https://library.municode.com/mn/plymouth/codes/code_of_ordinances?nodeId=CICO_CHXXIZOOR` |
| Zoning section anchors | Chapter XXI Zoning Ordinance; Sec. 21350 FRD; Secs. 21355 to 21365 RSF; Sec. 21380 RMF; Sec. 21650 P-I; Sec. 21655 PUD; commercial/industrial sections by code family |
| City zoning page | `https://www.plymouthmn.gov/departments/community-economic-development/planning/zoning-ordinance` |
| Bergen-pattern fit | **YES** |

Plymouth is a strong adjacent add-on because its public zoning layer exposes `PID`, `ADDRESS`, and `ZONING`, and its link-backed map layer includes Municode `WebLink` values for district sections. Use full city qualifier in planning docs to avoid confusion with Plymouth County, MA.

Sample zoning rows and citation pattern:

| Sample code | Live/source meaning | Citation pattern |
|---|---|---|
| `RSF-1` | Single Family Detached 1 | Cite Municode Sec. 21355. |
| `RSF-2` | Single Family Detached 2 | Cite Municode Sec. 21360. |
| `RSF-3` | Single Family Detached 3 | Cite Municode Sec. 21365. |
| `RMF-2` | Multiple Family 2 | Cite Municode Sec. 21380 family; spot-check residential density/use. |
| `PUD` | Planned Unit Development | Cite Municode Sec. 21655 plus project-specific terms if needed. |
| `P-I` | Public/Institutional | Cite Municode Sec. 21650. |
| `I-1` | Industrial district | Cite relevant Chapter XXI industrial section; do not blanket-prohibit without use read. |

Sprint note: ParcelViewer returned 23 distinct `ZONING` values; ZoningMap link-backed layer returned 16 values with direct Municode URLs. Prefer the link-backed layer for citation lookup if Lane A can join it reliably.

---

## Eden Prairie

| Field | Value |
|---|---|
| Display name | Eden Prairie, MN |
| Predicted prod_city_value | `Eden Prairie` |
| MetroGIS parcel coverage | YES: 23,019 rows |
| City zoning coverage | YES: public `Public/Zoning/MapServer/7`, 28 distinct `ZONING` values |
| Canonical ordinance URL | `https://library.municode.com/mn/eden_prairie/codes/code_of_ordinances?nodeId=CH11LAUSREZO` |
| Zoning section anchors | Chapter 11 Land Use Regulations; R-1 one-family districts; RM multi-family districts; office/commercial/industrial sections; city zoning map at `https://gis.edenprairie.org/zoning` |
| Zoning map PDF | `https://gis.edenprairie.org/CommDev/Zoning.pdf` |
| Bergen-pattern fit | **PARTIAL** |

Eden Prairie has good machine-readable zoning, including `PID`, `ADDRESS`, and `ZONING`. The ordinance is chapter-based and use/district sections are spread across Chapter 11 rather than one compact use table, so matrix authoring should be treated as partial Bergen-pattern fit.

Sample zoning rows and citation pattern:

| Sample code | Live/source meaning | Citation pattern |
|---|---|---|
| `R1-22` | One-family, 22,000 sq ft min lot family | Cite Chapter 11 R-1 one-family residential district section. |
| `R1-13.5` | One-family, 13,500 sq ft min lot family | Cite Chapter 11 R-1 one-family residential district section. |
| `RM-6.5` | Multi-family residential family | Cite Chapter 11 residential/multiple-family district section. |
| `C-REG` | Regional commercial | Cite Chapter 11 commercial district section; spot-check storage/warehouse uses. |
| `I-GEN` | General industrial | Cite Chapter 11 industrial district section; likely use-specific, not blanket-prohibited. |
| `OFC` | Office | Cite Chapter 11 office district section. |
| `P-PARK AND OPEN SPACE` | Park/open space | Cite zoning map + public/open-space provisions. |

Sprint note: Eden Prairie is a good second-wave add-on after Edina/Wayzata if Master wants Hennepin footprint growth. It has a significant industrial/commercial tail, so bias-against-unclear will require more real use reads than Edina residential rows.

---

## Recommended Hennepin matrix sprint sequence

1. **Edina** — strongest direct zoning-source proof, direct 57-list polygon, 39 codes.
2. **Wayzata** — direct 57-list polygon, clean ordinance/use-table pattern, but manual zoning-source path.
3. **Plymouth, MN** — strong public zoning layer plus Municode links; use full qualifier to avoid Plymouth MA ambiguity.
4. **Eden Prairie** — strong public zoning layer, larger commercial/industrial tail.
5. **Minnetonka** — high-value adjacent suburb, but source query/pagination should be hardened before a broad matrix sprint.

If sprint time is tight, stop after Edina + Wayzata. If Lane A has already populated the three adjacent cities from public layers, Plymouth is the best first add-on.

---

## Known risks / follow-up checks

- **`prod_city_value` uncertainty:** Hennepin is not loaded today. Verify prod `parcels.city` after Lane A writes parcels; likely values are MetroGIS title-case `CTU_NAME`.
- **No Class C:** MetroGIS `USECLASS1` includes values such as Residential, Commercial, Apartment, and Industrial. These are assessor/use classes, not zoning codes.
- **City-layer code drift:** City zoning layers may expose current local codes, while ordinance examples and PDF maps may use legacy or project-specific district names. Confirm actual `parcels.zoning_code` before authoring.
- **Minnetonka service quirks:** The backing service exposes `Zoning` but rejects pagination; Lane A should test object-id batching or another query path before relying on it for county-scale backfill.
- **Wayzata manual source:** Wayzata remains Class B/PDF-map unless a public machine-readable zoning layer is found.
- **Industrial/commercial edge cases:** Eden Prairie `I-GEN`, Plymouth `I-1`, Minnetonka `I-1`, and business/commercial codes need explicit use-level reads.
- **MetroGIS carry overstatement:** Ramsey + five other metro counties are parcel-source carry only. Their matrix sprint queues still need municipal zoning source work.

---

## Status

Pre-stage only. No code, no ingest, no matrix authoring. Use this document as the citation checklist once Lane A's Hennepin Tier 2 adapter output is available.
