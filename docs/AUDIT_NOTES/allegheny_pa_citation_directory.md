# Allegheny County, PA - Wealth-Pocket Citation Directory (Pre-Stage)

**Date:** 2026-06-16
**Purpose:** Pre-stage citation sources for the Allegheny PA matrix sprint after Lane A lands the Allegheny parcel adapter and municipal zoning source work. Target municipality is Fox Chapel Borough from the 57-list, plus O'Hara Township, Aspinwall, Sewickley, and Sewickley Heights as adjacent wealth-band candidates.
**Status:** Read-only diagnostic. **Not authoritative until Lane A's Allegheny ingest output lands.** `prod_city_value` values below are predictions from Allegheny parcel `MUNICODE` joined to the public municipal-boundary layer; verify actual prod formatting after ingest before authoring matrix rows.

---

## Bottom line

| Muni set | Count |
|---|---:|
| Municipalities staged | 5 |
| Direct 57-list polygon coverage | **YES**: Fox Chapel Borough |
| Bergen-pattern fit | 0 YES / 4 PARTIAL / 1 NO |
| Zoning-source availability | 0 verified live zoning FeatureServers / 4 eCode360 or structured online code sources / 1 land-ordinance/PDF workflow |
| Fox Chapel parcel gate | **PASS for parcels.** Accepted spec confirms `MUNICODE=868`, 2,179 parcels. |
| Fox Chapel zoning gate | **Manual Class B.** No public Fox Chapel zoning FeatureServer found; borough provides eCode360 zoning chapter, schedule attachment, and zoning map attachment. |
| Expected matrix sprint hours at 5-10 min/code | 10-20h raw authoring |
| Expected total with source friction | 16-30h |
| Recommended proof scope | Fox Chapel only if Master wants the single 57-list polygon; add O'Hara only if corridor breadth matters |

**Recommendation:** Keep Allegheny as a **low-ROI Class B/manual fallback**, not a near-term multi-polygon target. It is useful because Fox Chapel is a true 57-list polygon and parcel filtering is clean, but it will not flip countywide readiness. No municipal zoning FeatureServer surfaced in this pass.

**Class A/C gate note:** Allegheny parcels do **not** carry embedded zoning and no public municipal zoning FeatureServer was verified. Do not treat `MUNICODE` as zoning; it is the municipal join key. Lane A should ingest parcels from WPRDC/Allegheny, join `MUNICODE`, then source municipal zoning from eCode/PDF/map workflows.

---

## Live source probes used

- Allegheny parcel source: `https://gisdata.alleghenycounty.us/arcgis/rest/services/OPENDATA/Parcels/MapServer/0`
- Allegheny municipal boundaries: `https://services1.arcgis.com/vdNDkVykv9vEWFX4/arcgis/rest/services/AlleghenyCountyMunicipalBoundaries/FeatureServer/0`
- Allegheny acquisition spec baseline: `docs/ALLEGHENY_PA_ACQUISITION_SPEC.md`
- Fox Chapel eCode360 zoning chapter: `https://ecode360.com/31904910`
- Fox Chapel classifications page: `https://www.fox-chapel.pa.us/185/Classifications`
- Fox Chapel district schedule PDF: `https://ecode360.com/attachment/FO2332/FO2332-400a%20Sch%20of%20Dist%20Regs%20Uses%20and%20Structures.pdf`
- Fox Chapel zoning district map PDF: `https://ecode360.com/attachment/FO2332/FO2332-400b%20Zoning%20District%20Map.pdf`
- O'Hara Township eCode page: `https://www.ohara.pa.us/administration/pages/township-code-ecode360`
- O'Hara Chapter 455 zoning: `https://ecode360.com/31391570`
- O'Hara zoning districts: `https://ecode360.com/31391913`
- O'Hara zoning-map PDF: `https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf`
- Aspinwall Chapter 27 zoning: `https://ecode360.com/30911259`
- Aspinwall eCode entry: `https://ecode360.com/AS0229`
- Sewickley Chapter 330 zoning: `https://ecode360.com/32411085`
- Sewickley zoning district regulations: `https://ecode360.com/32411498`
- Sewickley official zoning map page: `https://www.sewickleyborough.org/391/Official-Zoning-Map`
- Sewickley Heights land ordinances: `https://www.sewickleyheightsboro.com/generalgovernment/land-ordinances`

Predicted municipal keys from the Allegheny municipal-boundary layer:

| Display name | Predicted prod_city_value | `MUNICODE` | Parcel count |
|---|---|---:|---:|
| Fox Chapel Borough | `Fox Chapel Borough` | 868 | 2,179 |
| O'Hara Township | `O Hara Township` | 931 | 4,348 |
| Aspinwall Borough | `Aspinwall Borough` | 801 | 1,125 |
| Sewickley Borough | `Sewickley Borough` | 851 | 1,699 |
| Sewickley Heights Borough | `Sewickley Heights Borough` | 869 | 452 |

Source availability:

| Muni | Source status | Verified code field | Distinct code estimate |
|---|---|---|---:|
| Fox Chapel | eCode360 + schedule/map PDFs | N/A | 5 core districts |
| O'Hara | eCode360 + zoning-map PDF | N/A | ~12-16 |
| Aspinwall | eCode360 + zoning-map attachment | N/A | ~9-12 |
| Sewickley | eCode360 + zoning-map attachment/page | N/A | ~8-12 |
| Sewickley Heights | Google Sites land ordinances / PDF workflow | N/A | unknown, likely small |

---

## How to use this directory

1. After Lane A lands Allegheny parcels, re-pull actual uncovered `(city, zoning_code)` pairs for the staged munis.
2. Use `MUNICODE` for municipal filtering. Postal place names are not the authoritative join key.
3. Do not classify Allegheny as Class C. Parcel rows carry parcel identity and municipality metadata, not zoning.
4. Do not claim Class A unless Lane A finds a municipal zoning polygon source and runs bbox + `ST_Within` preview gates.
5. Expect matrix rows to be keyed by municipal display name plus manually sourced zone code.
6. Treat Fox Chapel as the only required 57-list proof; all other staged munis are optional corridor breadth.

---

## Fox Chapel Borough

| Field | Value |
|---|---|
| Display name | Fox Chapel Borough, PA |
| Predicted prod_city_value | `Fox Chapel Borough` |
| Allegheny parcel key | `MUNICODE=868` |
| Parcel coverage | YES: 2,179 rows in accepted spec |
| Canonical ordinance URL | `https://ecode360.com/31904910` |
| Borough classifications page | `https://www.fox-chapel.pa.us/185/Classifications` |
| Zoning map/source | eCode360 zoning district map attachment: `https://ecode360.com/attachment/FO2332/FO2332-400b%20Zoning%20District%20Map.pdf` |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Chapter 400 Zoning; Article III Districts; Attachment 1 schedule of district regulations/uses/structures; Attachment 2 zoning district map |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | 5 core districts; 1-2h after zoning source is converted/populated |

Fox Chapel is the only direct 57-list polygon. It is small and citation-friendly, but not a live-layer sprint. The borough classifications page lists five districts, and eCode360 exposes both the zoning schedule and map attachments.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `A` | Class "A" Residence District, minimum lot size 3 acres | Cite Chapter 400 Article III and Attachment 1 schedule. |
| `B` | Class "B" Residence District, minimum lot size 2 acres | Same Article III + Attachment 1 pattern. |
| `C` | Class "C" Residence District, minimum lot size 1 acre | Same Article III + Attachment 1 pattern. |
| `D` | Class "D" Residence District, recorded lots / 1 acre minimum for post-1989 lots | Same Article III + Attachment 1 pattern. |
| `I-O` | Institutional/Open Space District | Cite Article III plus Attachment 1 schedule; use-level read required. |

Sprint note: this is the fallback proof. It is small enough to author manually, but Lane A still needs a zoning-code source before matrix rows can bind to parcels.

---

## O'Hara Township

| Field | Value |
|---|---|
| Display name | O'Hara Township, PA |
| Predicted prod_city_value | `O Hara Township` |
| Allegheny parcel key | `MUNICODE=931` |
| Parcel coverage | YES: 4,348 rows |
| Canonical ordinance URL | `https://ecode360.com/31391570` |
| Township eCode page | `https://www.ohara.pa.us/administration/pages/township-code-ecode360` |
| Zoning map PDF | `https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf` |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Chapter 455 Zoning; Article III Zoning Districts; §455-3.2 Zoning districts; district articles for residential/conservation/commercial/manufacturing; §455-15 supplemental regulations |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~12-16 codes; 3-5h after source extraction |

O'Hara is the most useful add-on near Fox Chapel because it surrounds much of the same wealth corridor. The ordinance is online and searchable, with a clear district list and zoning-map PDF. It is not a Bergen-style single use table.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R-1` | §455-3.2 Special Residential District | Cite §455-3.2 and the R-1 district article. |
| `R-2` | §455-3.2 Suburban Residential District | Cite §455-3.2 and the R-2 district article. |
| `R-3` | §455-3.2 Urban Residential District | Cite §455-3.2 and the R-3 district article. |
| `R-4` | §455-3.2 Special Moderate-Density Residential District | Cite §455-3.2 and the R-4 district article. |
| `C` | §455-3.2 Commercial District | Cite commercial district article and supplemental use sections. |
| `SM` | Suburban Manufacturing District references in Chapter 455 | Cite district article plus §455-15 supplemental regulations; storage/industrial uses need explicit read. |

Sprint note: add O'Hara after Fox Chapel only if Master wants corridor breadth. It has more row volume and more code complexity than Fox Chapel.

---

## Aspinwall Borough

| Field | Value |
|---|---|
| Display name | Aspinwall Borough, PA |
| Predicted prod_city_value | `Aspinwall Borough` |
| Allegheny parcel key | `MUNICODE=801` |
| Parcel coverage | YES: 1,125 rows |
| Canonical ordinance URL | `https://ecode360.com/30911259` |
| Borough eCode entry | `https://ecode360.com/AS0229` |
| Zoning map/source | Chapter 27 Attachment 2 zoning map |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Chapter 27 Zoning; Part 3 Schedule of District Regulations; §27-301 Establishment of District Classifications; §§27-303 through 27-311 district sections |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~9-12 codes; 2-4h after source extraction |

Aspinwall has a clean eCode360 zoning chapter and a zoning-map attachment. It is a compact borough, but still a code/map workflow rather than a live zoning layer.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `AR-1` | §27-303 Single Family Residential Districts | Cite Part 3 schedule and §27-303. |
| `AR-2` | §27-304 Residential Districts | Cite Part 3 schedule and §27-304. |
| `AR-3` | §27-305 Single and Multiple Family Districts | Cite Part 3 schedule and §27-305. |
| `AR-4` | §27-306 Multifamily Residential Districts | Cite Part 3 schedule and §27-306. |
| `AC-2` | §27-309 General Commercial Districts | Cite Part 3 schedule and §27-309; use-level read required. |
| `AI-1` | §27-310 Limited Industrial Districts | Cite §27-310; likely relevant for industrial/storage-like uses, but do not bulk-class. |

Sprint note: small and citation-friendly, but not a direct 57-list polygon. Keep behind Fox Chapel/O'Hara.

---

## Sewickley Borough

| Field | Value |
|---|---|
| Display name | Sewickley Borough, PA |
| Predicted prod_city_value | `Sewickley Borough` |
| Allegheny parcel key | `MUNICODE=851` |
| Parcel coverage | YES: 1,699 rows |
| Canonical ordinance URL | `https://ecode360.com/32411085` |
| Zoning district regulations | `https://ecode360.com/32411498` |
| Official zoning map page | `https://www.sewickleyborough.org/391/Official-Zoning-Map` |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Chapter 330 Zoning; Article II Zoning Map; Article IV Zoning District Regulations; §330-401 Establishment of zoning districts; attachments for zoning map and land-use tables |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~8-12 codes; 2-4h after source extraction |

Sewickley is the strongest add-on citation source because Chapter 330 includes zoning-map and principal/accessory use table attachments. It is still a borough-level Class B workflow, not a live-source sprint.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R-1` | Article IV Single-Family Residential district | Cite §330-401 and principal land-use table attachment. |
| `R-1A` | Article IV Single-Family Residential district | Same Article IV + use-table attachment pattern. |
| `R-2` | Article IV Multifamily Residential district | Cite Article IV and principal/accessory use tables. |
| `C-1` | Article IV General Commercial district | Cite Article IV and principal land-use table; use-level read required. |
| `C-2` | Article IV Highway Commercial district | Same commercial pattern; use-level read required. |
| `Inst.` | Article IV Institutional district | Cite Article IV and use table attachment. |

Sprint note: Sewickley is not the Fox Chapel polygon, but it is a good optional add-on if Lane A wants a complete Ohio River wealth-corridor proof.

---

## Sewickley Heights Borough

| Field | Value |
|---|---|
| Display name | Sewickley Heights Borough, PA |
| Predicted prod_city_value | `Sewickley Heights Borough` |
| Allegheny parcel key | `MUNICODE=869` |
| Parcel coverage | YES: 452 rows |
| Canonical ordinance URL | `https://www.sewickleyheightsboro.com/generalgovernment/land-ordinances` |
| Zoning source | Ordinance No. 294 Amended and Restated Zoning Ordinance from borough land-ordinance page |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Ordinance No. 294; borough land-ordinance page; zoning-map/source not cleanly exposed as eCode360 |
| Bergen-pattern fit | **NO** |
| Estimated sprint scope | Unknown code count; 3-6h source-friction minimum despite small parcel count |

Sewickley Heights is high-value but not source-clean. The borough page lists land ordinances, including Ordinance No. 294 as the amended/restated zoning ordinance, but no eCode360-style structured code or public zoning FeatureServer was verified in this pass.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `Residential estate district` | Ordinance No. 294 likely district structure; exact code not verified | Do not author until the PDF/ordinance text is obtained and district names/codes are confirmed. |
| `Conservation/open-space district` | Borough land-ordinance workflow; exact code not verified | Same: source extraction required before matrix. |
| `Institutional/club-related district` | Local land-use context; exact code not verified | Same: source extraction required before matrix. |

Sprint note: do not include Sewickley Heights in a first Allegheny proof unless Master explicitly values the small high-end enclave over clean execution. It is only 452 parcels and has the highest citation/source friction in this set.

---

## Recommended Allegheny sprint sequence

1. **Fox Chapel Borough** - direct 57-list polygon; clean parcel key and small district count. Expected 1-2h matrix after zoning source is populated, plus map/source conversion.
2. **O'Hara Township** - adjacent corridor breadth and 4,348 parcels; eCode360 + zoning-map PDF. Expected 3-5h.
3. **Sewickley Borough** - strongest optional add-on citation structure via eCode tables/attachments. Expected 2-4h.
4. **Aspinwall Borough** - compact eCode360 add-on. Expected 2-4h.
5. **Sewickley Heights Borough** - high-value but source-friction heavy. Expected 3-6h minimum after ordinance extraction.

Expected target-muni matrix backlog: **16-30h including source friction**, or **10-20h raw authoring** after clean `(city, zoning_code)` values are available.

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| No public municipal zoning FeatureServer found | No immediate Class A backfill | Treat every target as Class B/manual unless Lane A finds a hidden source. |
| Parcel source has no embedded zoning | No Class C path | Use `MUNICODE` for municipality, not zoning. |
| Fox Chapel is tiny relative to county | No countywide operational flip | Scope as borough proof only. |
| Zoning maps are PDFs/attachments | More source conversion before matrix | Archive source PDFs and add provenance before backfill/matrix. |
| O'Hara/Sewickley add code complexity | Manual row count grows quickly | Keep proof to Fox Chapel first unless breadth is explicitly requested. |
| Sewickley Heights source is weak | Could burn time for only 452 parcels | Defer unless Master wants enclave-specific completeness. |

---

## Directory shape recommendation

Allegheny's directory should key each municipal source by `MUNICODE`, with display names coming from the municipal-boundary layer:

```json
{
  "county": "Allegheny",
  "state": "PA",
  "municipalities": {
    "868": {
      "display_name": "Fox Chapel Borough",
      "municipality_field": "MUNICODE",
      "source_type": "ecode360_plus_pdf_map",
      "ordinance_url": "https://ecode360.com/31904910",
      "zoning_map_url": "https://ecode360.com/attachment/FO2332/FO2332-400b%20Zoning%20District%20Map.pdf",
      "zone_code_field": null,
      "notes": "No public zoning FeatureServer verified in pre-stage."
    },
    "931": {
      "display_name": "O Hara Township",
      "municipality_field": "MUNICODE",
      "source_type": "ecode360_plus_pdf_map",
      "ordinance_url": "https://ecode360.com/31391570",
      "zoning_map_url": "https://www.ohara.pa.us/sites/g/files/vyhlif6181/f/uploads/zoningmap.pdf",
      "zone_code_field": null
    },
    "851": {
      "display_name": "Sewickley Borough",
      "municipality_field": "MUNICODE",
      "source_type": "ecode360_plus_map_attachment",
      "ordinance_url": "https://ecode360.com/32411085",
      "zoning_map_url": "https://www.sewickleyborough.org/391/Official-Zoning-Map",
      "zone_code_field": null
    },
    "801": {
      "display_name": "Aspinwall Borough",
      "municipality_field": "MUNICODE",
      "source_type": "ecode360_plus_map_attachment",
      "ordinance_url": "https://ecode360.com/30911259",
      "zoning_map_url": "https://ecode360.com/AS0229",
      "zone_code_field": null
    },
    "869": {
      "display_name": "Sewickley Heights Borough",
      "municipality_field": "MUNICODE",
      "source_type": "land_ordinance_pdf_workflow",
      "ordinance_url": "https://www.sewickleyheightsboro.com/generalgovernment/land-ordinances",
      "zone_code_field": null,
      "notes": "No eCode-style structured source or public zoning FeatureServer verified in pre-stage."
    }
  }
}
```

This directory should not include matrix rows. It is only the acquisition/citation map that lets Lane A populate parcel `zoning_code` and lets orchestrator author matrix rows after ingest.
