# Oakland County, MI - Wealth-Pocket Citation Directory (Pre-Stage)

**Date:** 2026-06-16
**Purpose:** Pre-stage citation sources for the Oakland MI matrix sprint after Lane A lands the Oakland parcel adapter and municipal zoning backfills. Target municipalities are Birmingham and Bloomfield Hills from the 57-list, plus Bloomfield Township, Franklin, and Beverly Hills as adjacent Detroit-metro wealth-band candidates.
**Status:** Read-only diagnostic. **Not authoritative until Lane A's Oakland ingest output lands.** `prod_city_value` values below are predictions from Oakland County parcel `CVTTAXDESCRIPTION`, not postal `SITECITY`; verify them against prod after ingest before authoring matrix rows.

---

## Bottom line

| Muni set | Count |
|---|---:|
| Municipalities staged | 5 |
| Target-muni parcels in Oakland source | 35,329 |
| Direct 57-list polygon coverage | **YES**: Birmingham + Bloomfield Hills |
| Bergen-pattern fit | 1 YES / 4 PARTIAL / 0 NO |
| Zoning-layer availability | 3 live FeatureServer/MapServer sources / 2 PDF-code workflows / 0 no-public-source |
| SEMCOG multi-county carry | **NO verified carry**. No authoritative Oakland + Wayne + Macomb parcel/zoning REST source was found; use Oakland County direct parcels. |
| Expected matrix sprint hours at 5-10 min/code | 11-21h raw authoring |
| Expected total with source friction | 16-30h |
| Recommended proof scope | Bloomfield Hills + Birmingham first: both direct 57-list polygons and both have live zoning geometry |
| Recommended add-on scope | Beverly Hills, then Bloomfield Township, then Franklin |

**Recommendation:** Stage Oakland as a **single-county parcel adapter plus per-muni zoning sources**, not a SEMCOG regional clone. Birmingham and Bloomfield Hills remain the proof pair. Beverly Hills is a better add-on than expected because its official ArcGIS Experience exposes a live `Zoning_Dissolved/FeatureServer/0`. Bloomfield Township and Franklin remain PDF/code workflows unless Lane A finds hidden municipal GIS endpoints.

**Class A/C gate note:** Oakland County parcels do **not** carry embedded municipal zoning codes. Do not treat `CLASSCODE`, `CVTTAXCODE`, `CVTTAXDESCRIPTION`, or `SITECITY` as zoning. The usable primitive is Class A-style municipal zoning geometry for Birmingham, Bloomfield Hills, and Beverly Hills; Bloomfield Township and Franklin are Class B/PDF until proven otherwise. Birmingham and Bloomfield Hills bbox primitives were already accepted in `docs/OAKLAND_MI_ACQUISITION_SPEC.md`; Beverly Hills bbox also matches the village parcel bbox in this pre-stage, but Lane A still must run the required preview `ST_Within` gate before production backfill.

---

## Live source probes used

- Oakland County parcel source: `https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1`
- Oakland acquisition spec baseline: `docs/OAKLAND_MI_ACQUISITION_SPEC.md`
- Birmingham zoning layer: `https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0`
- Birmingham ordinance: `https://online.encodeplus.com/regs/birmingham-mi/doc-viewer.aspx`
- Bloomfield Hills zoning layer: `https://services9.arcgis.com/jGlVpYnGiHmSg9fR/arcgis/rest/services/Zoning_BloomfieldHills/FeatureServer/0`
- Bloomfield Hills ordinance page: `https://www.bloomfieldhills.gov/241/Zoning-Ordinance`
- Bloomfield Township zoning ordinance: `https://www.bloomfieldtwp.org/clerk/zoning-ordinance/`
- Bloomfield Township zoning map PDF: `https://www.bloomfieldtwp.org/media/tynlmzsz/zoning-map-11x17.pdf`
- Franklin municipal code: `https://codelibrary.amlegal.com/codes/franklin/latest/overview`
- Franklin maps page: `https://www.franklin.mi.us/community/maps.php`
- Beverly Hills planning/zoning page: `https://www.villagebeverlyhills.com/department/planning___zoning/index.php`
- Beverly Hills zoning viewer: `https://experience.arcgis.com/experience/5b815c30b384412a9dae562b32a58691`
- Beverly Hills zoning layer: `https://services5.arcgis.com/1PnnJue8khcujdxm/arcgis/rest/services/Zoning_Dissolved/FeatureServer/0`
- Beverly Hills Municode Chapter 46: `https://library.municode.com/mi/beverly_hills/codes/code_of_ordinances?nodeId=PTIICOOR_CH46ZO`

Oakland parcel counts by `CVTTAXDESCRIPTION`:

| Display name | Predicted prod_city_value | Oakland parcel filter | Parcel count |
|---|---|---|---:|
| Birmingham | `CITY OF BIRMINGHAM` | `UPPER(CVTTAXDESCRIPTION)='CITY OF BIRMINGHAM'` | 9,786 |
| Bloomfield Hills | `CITY OF BLOOMFIELD HILLS` | `UPPER(CVTTAXDESCRIPTION)='CITY OF BLOOMFIELD HILLS'` | 1,833 |
| Bloomfield Township | `CHARTER TOWNSHIP OF BLOOMFIELD` | `UPPER(CVTTAXDESCRIPTION)='CHARTER TOWNSHIP OF BLOOMFIELD'` | 18,224 |
| Franklin | `VILLAGE OF FRANKLIN` | `UPPER(CVTTAXDESCRIPTION)='VILLAGE OF FRANKLIN'` | 1,312 |
| Beverly Hills | `VILLAGE OF BEVERLY HILLS` | `UPPER(CVTTAXDESCRIPTION)='VILLAGE OF BEVERLY HILLS'` | 4,174 |

Layer availability:

| Muni | Zoning layer status | Verified code field | Distinct code estimate |
|---|---|---|---:|
| Birmingham | Live MapServer | `district` | 21 |
| Bloomfield Hills | Live FeatureServer | `Zoning` | 13 |
| Bloomfield Township | No live layer verified; Clearzoning PDF + zoning-map PDF | N/A | ~10-12 from map/PDF |
| Franklin | No live layer verified; American Legal code + zoning-map PDF | N/A | ~10 from code/map |
| Beverly Hills | Live FeatureServer | `Zoning` | 12 nonblank codes |

---

## How to use this directory

1. After Lane A lands Oakland parcels, re-pull actual uncovered `(city, zoning_code)` pairs for the staged munis.
2. Use `CVTTAXDESCRIPTION` as the predicted city/municipality key unless Lane A normalizes it deliberately. `SITECITY` is postal and over-selects Bloomfield-area parcels.
3. Do not classify Oakland as Class C. The county parcel source has tax and assessing fields, not zoning.
4. If Lane A uses a municipal zoning layer, matrix rows should match that layer's exact code field: Birmingham `district`, Bloomfield Hills `Zoning`, Beverly Hills `Zoning`.
5. Keep Birmingham AL false positives out of source discovery. The accepted spec already flagged an Alabama `Birmingham_Zoning` item as irrelevant.
6. Author residential districts conservatively; business/office/mixed-use/industrial codes need use-table or district-specific citation reads.

---

## Birmingham

| Field | Value |
|---|---|
| Display name | Birmingham, MI |
| Predicted prod_city_value | `CITY OF BIRMINGHAM` |
| Oakland parcel coverage | YES: 9,786 rows |
| Canonical ordinance URL | `https://online.encodeplus.com/regs/birmingham-mi/doc-viewer.aspx` |
| Live zoning layer | `https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0` |
| Verified code field | `district`; description field `descript`; standards link field `standards` |
| Zoning section anchors | Article 2 Zoning Districts and Regulations; Appendix A Land Use Matrix; district standards links in the city layer |
| Bergen-pattern fit | **YES** |
| Estimated sprint scope | 21 live layer codes; 3-5h after zone codes are populated |

Birmingham is the cleanest Oakland matrix target. The city zoning layer exposes district values and direct ordinance/PDF anchors, and enCodePlus exposes an Appendix A Land Use Matrix. The only source caveat is code spelling: the live layer uses `0-1` / `0-2` for office districts in sampled rows, while ordinance text/search uses `O1` / `O2`. Matrix rows must match the post-ingest value exactly.

Sample live zoning rows and citation pattern:

| Sample code | Source description | Citation pattern |
|---|---|---|
| `R1` | Single Family Residential | Cite Article 2 district standards via layer `standards` link and Appendix A Land Use Matrix. |
| `R2` | Single Family Residential | Same residential district + Appendix A pattern. |
| `B-1` | Office / Neighborhood Business | Cite `B1 Neighborhood Business District` section and Appendix A Land Use Matrix. |
| `B-2` | General Business | Cite `B2 General Business District` section and Appendix A Land Use Matrix. |
| `MX` | Mixed Use | Cite `MX Mixed Use District` section and Appendix A before classifying any storage/industrial-adjacent use. |

Sprint note: start Birmingham after Bloomfield Hills if Lane A wants the direct-join proof first; start Birmingham first if orchestrator wants the fastest matrix authoring because Appendix A is the strongest use-table source in this Oakland set.

---

## Bloomfield Hills

| Field | Value |
|---|---|
| Display name | Bloomfield Hills, MI |
| Predicted prod_city_value | `CITY OF BLOOMFIELD HILLS` |
| Oakland parcel coverage | YES: 1,833 rows |
| Canonical ordinance URL | `https://www.bloomfieldhills.gov/241/Zoning-Ordinance` |
| Municode source | `https://library.municode.com/mi/bloomfield_hills/codes/code_of_ordinances` |
| Zoning map PDF | `https://www.bloomfieldhills.gov/DocumentCenter/View/30/Zoning-Map-PDF` |
| Live zoning layer | `https://services9.arcgis.com/jGlVpYnGiHmSg9fR/arcgis/rest/services/Zoning_BloomfieldHills/FeatureServer/0` |
| Verified code field | `Zoning`; parcel identity field `PIN` is present in the layer |
| Zoning section anchors | Chapter 54 Zoning / city zoning ordinance; district-specific sections for A, B, C, I, O, P, and RR zones |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | 13 live layer codes; 2-4h after zone codes are populated |

Bloomfield Hills is the best technical proof city because the municipal zoning layer is parcel-like and carries `PIN` plus `Zoning`. Lane A can try direct Oakland `PIN` to city `PIN` join before falling back to spatial backfill. The ordinance side is more district-section-oriented than Bergen, but the district count is small.

Sample live zoning codes and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `A-1` | Live `Zoning` value; city zoning ordinance/map | Cite one-family residential district section and map. |
| `A-2` | Live `Zoning` value; city zoning ordinance/map | Same residential district pattern. |
| `B-1` | Live `Zoning` value; city zoning ordinance/map | Cite business district section; use-level read required. |
| `I-1` | Live `Zoning` value; city zoning ordinance/map | Cite industrial district section; likely relevant for industrial/storage-like uses, but do not bulk-class. |
| `O-1` | Live `Zoning` value; city zoning ordinance/map | Cite office district section; use-level read required. |

Sprint note: this should be Lane A's first Oakland technical proof if Master values join quality over city size. Matrix sprint is small, but it is not enough to move countywide operational metrics by itself.

---

## Bloomfield Township

| Field | Value |
|---|---|
| Display name | Bloomfield Township, MI |
| Predicted prod_city_value | `CHARTER TOWNSHIP OF BLOOMFIELD` |
| Oakland parcel coverage | YES: 18,224 rows |
| Canonical ordinance URL | `https://www.bloomfieldtwp.org/clerk/zoning-ordinance/` |
| Zoning ordinance PDF | `https://www.bloomfieldtwp.org/media/4qbd0omj/2026-03-24-bloomfield-zoning-ordinance_secured.pdf` |
| Zoning map PDF | `https://www.bloomfieldtwp.org/media/tynlmzsz/zoning-map-11x17.pdf` |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Clearzoning ordinance; zoning map legend references Section 42-3 district standards |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~10-12 codes; 3-5h including PDF/source friction |

Bloomfield Township is a high-parcel adjacent add-on, but it is not a live-layer proof in this pass. The township publishes a current Clearzoning ordinance and zoning-map PDF. The map/search-indexed PDF exposes a compact code set, but Lane A needs a geometry source or extraction path before matrix work can bind to parcels.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R-1` | Zoning map PDF; one-family residential district | Cite Clearzoning Section 42-3 district standards and map legend. |
| `R-2` | Zoning map PDF; one-family residential district | Same residential district pattern. |
| `R-3` | Zoning map PDF; one-family residential district | Same residential district pattern. |
| `R-M` | Zoning map PDF; multiple-family residential district | Cite multifamily district standards and any use standards. |
| `B-2` | Zoning map PDF; business district | Cite business district standards and use table/standards in Clearzoning PDF. |
| `O-1` | Zoning map PDF; office district | Cite office district standards; use-level read required. |

Sprint note: do not put Township in the first Oakland proof unless Lane A finds a reliable zoning polygon layer. It is valuable for scale because of parcel count, but it is source-friction heavy.

---

## Franklin

| Field | Value |
|---|---|
| Display name | Franklin, MI |
| Predicted prod_city_value | `VILLAGE OF FRANKLIN` |
| Oakland parcel coverage | YES: 1,312 rows |
| Canonical ordinance URL | `https://codelibrary.amlegal.com/codes/franklin/latest/overview` |
| Village code page | `https://www.franklin.mi.us/government/charter_%26_municipal_ordinances.php` |
| Zoning map source | Village maps page `https://www.franklin.mi.us/community/maps.php`; indexed zoning-map PDF `https://cms7files.revize.com/franklinmi/document_center/Government/Zoning%20Board%20of%20apeal/ZoningMap.pdf` |
| Verified public zoning FeatureServer | **NO** from this pass |
| Zoning section anchors | Title Four Zoning; Chapter 1248 Districts Generally and Zoning Map; Chapter 1250 Single-Family Residential Districts; Chapter 1254 RO-1; Chapter 1256 C-1; Chapter 1258 P-1; Chapter 1259 PI; Appendix B Schedule of Regulations |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~8-12 codes; 2-4h including PDF/source friction |

Franklin has a clean American Legal code structure but no live zoning layer found. The code is compact and residential-heavy, so matrix authoring should be modest once a zoning map/source extraction path exists.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R-E` | Chapter 1250 and Appendix B reference single-family residential districts | Cite Chapter 1250 permitted/prohibited/special approval uses plus Appendix B. |
| `R-L` | Chapter 1250 and Appendix B | Same single-family residential pattern. |
| `R-1` | Chapter 1250 and Appendix B | Same single-family residential pattern. |
| `R-2` | Chapter 1250 and Appendix B | Same single-family residential pattern. |
| `RO-1` | Chapter 1254 Restricted Office District | Cite Chapter 1254 permitted/accessory uses and parking/landscaping standards. |
| `C-1` | Chapter 1256 Commercial District | Cite Chapter 1256; commercial use-level read required. |
| `PI` | Chapter 1259 Public Institutional District | Cite Chapter 1259; likely public/institutional. |

Sprint note: Franklin is a small wealth-band add-on, not a proof target. Run it after the live-layer munis unless Master specifically wants village completeness around Birmingham/Bloomfield Hills.

---

## Beverly Hills

| Field | Value |
|---|---|
| Display name | Beverly Hills, MI |
| Predicted prod_city_value | `VILLAGE OF BEVERLY HILLS` |
| Oakland parcel coverage | YES: 4,174 rows |
| Canonical ordinance URL | `https://library.municode.com/mi/beverly_hills/codes/code_of_ordinances?nodeId=PTIICOOR_CH46ZO` |
| Planning/zoning page | `https://www.villagebeverlyhills.com/department/planning___zoning/index.php` |
| Zoning viewer | `https://experience.arcgis.com/experience/5b815c30b384412a9dae562b32a58691` |
| Live zoning layer | `https://services5.arcgis.com/1PnnJue8khcujdxm/arcgis/rest/services/Zoning_Dissolved/FeatureServer/0` |
| Verified code field | `Zoning` |
| Zoning section anchors | Municode Chapter 46 Zoning; village page links Chapter 46, zoning map, and planning/zoning materials |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | 12 nonblank live layer codes; 2-4h after zone codes are populated |

Beverly Hills is the best surprise in this pass. The official village planning page links an ArcGIS Experience zoning viewer, whose backing web map exposes a public `Zoning_Dissolved` FeatureServer. The layer has 322 polygons, 238 nonblank zoning polygons, and 12 distinct nonblank codes. Its WGS84 bbox effectively matches the Oakland parcel bbox for `VILLAGE OF BEVERLY HILLS`, so it is a plausible Class A add-on after Lane A's preview gates.

Sample live zoning codes and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R-A` | Live `Zoning` value; Chapter 46 residential districts | Cite Chapter 46 residential district section and schedule. |
| `R-1` | Live `Zoning` value; Chapter 46 residential districts | Same residential district pattern. |
| `R-2` | Live `Zoning` value; Chapter 46 residential districts | Same residential district pattern. |
| `R-3` | Live `Zoning` value; Chapter 46 residential districts | Same residential district pattern. |
| `B` | Live `Zoning` value; Chapter 46 business-related district section | Cite business district section; use-level read required. |
| `O-1` | Live `Zoning` value; Chapter 46 office-related district section | Cite office district section; use-level read required. |

Sprint note: Beverly Hills should be the first add-on after Birmingham/Bloomfield Hills. It has a live layer and moderate parcel count, with less source friction than Bloomfield Township or Franklin.

---

## Recommended Oakland sprint sequence

1. **Bloomfield Hills** - direct 57-list polygon, best technical proof because city layer carries `PIN` + `Zoning`. Expected 2-4h matrix after zoning ingest.
2. **Birmingham** - direct 57-list polygon, strongest ordinance/use-table source via enCodePlus Appendix A. Expected 3-5h matrix.
3. **Beverly Hills** - live FeatureServer add-on and adjacent wealth band. Expected 2-4h matrix.
4. **Bloomfield Township** - largest adjacent parcel count but PDF/Clearzoning source friction. Expected 3-5h after source extraction.
5. **Franklin** - small village add-on, American Legal code + zoning-map PDF. Expected 2-4h after source extraction.

Expected target-muni matrix backlog: **16-30h including source friction**, or **11-21h raw authoring** after clean `(city, zoning_code)` values are available.

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| SEMCOG multi-county carry remains unverified | Oakland should not jump King/Hennepin on regional ROI | Keep Oakland scoped to official Oakland County parcel source. |
| Postal `SITECITY` over-selects Bloomfield-area parcels | Wrong city mapping and failed matrix joins | Use `CVTTAXDESCRIPTION` / tax jurisdiction as the municipal key. |
| County parcel source has no embedded zoning | No Class C path | Use municipal zoning geometry or PDF/map extraction per muni. |
| Birmingham office code spelling may be `0-1`/`0-2` in source | Matrix rows could miss if authored as `O1`/`O2` | Match the exact post-ingest `zoning_code`; do not normalize silently. |
| Bloomfield Hills FeatureServer provenance is less obvious than city pages | Direct join needs validation | Cross-check against city zoning map PDF and run direct `PIN` join-rate gate. |
| Beverly Hills layer has blank `Zoning` polygons | Could backfill blank codes | Filter nonblank `Zoning`; document blanks in provenance. |
| Bloomfield Township and Franklin are PDF/code workflows | Higher source friction before matrix can start | Keep them after the live-layer proof munis. |

---

## Directory shape recommendation

Oakland's directory should key each municipal source by the predicted `CVTTAXDESCRIPTION` value and exact municipal zoning-code field:

```json
{
  "county": "Oakland",
  "state": "MI",
  "municipalities": {
    "CITY OF BIRMINGHAM": {
      "display_name": "Birmingham",
      "parcel_filter_field": "CVTTAXDESCRIPTION",
      "source_type": "arcgis_mapserver",
      "zoning_layer_url": "https://maps.bhamgov.org/arcgis/rest/services/Zoning/MapServer/0",
      "zone_code_field": "district",
      "zone_description_field": "descript",
      "ordinance_url": "https://online.encodeplus.com/regs/birmingham-mi/doc-viewer.aspx"
    },
    "CITY OF BLOOMFIELD HILLS": {
      "display_name": "Bloomfield Hills",
      "parcel_filter_field": "CVTTAXDESCRIPTION",
      "source_type": "arcgis_featureserver",
      "zoning_layer_url": "https://services9.arcgis.com/jGlVpYnGiHmSg9fR/arcgis/rest/services/Zoning_BloomfieldHills/FeatureServer/0",
      "zone_code_field": "Zoning",
      "parcel_join_field": "PIN",
      "ordinance_url": "https://www.bloomfieldhills.gov/241/Zoning-Ordinance"
    },
    "VILLAGE OF BEVERLY HILLS": {
      "display_name": "Beverly Hills",
      "parcel_filter_field": "CVTTAXDESCRIPTION",
      "source_type": "arcgis_featureserver",
      "zoning_layer_url": "https://services5.arcgis.com/1PnnJue8khcujdxm/arcgis/rest/services/Zoning_Dissolved/FeatureServer/0",
      "zone_code_field": "Zoning",
      "ordinance_url": "https://library.municode.com/mi/beverly_hills/codes/code_of_ordinances?nodeId=PTIICOOR_CH46ZO"
    },
    "CHARTER TOWNSHIP OF BLOOMFIELD": {
      "display_name": "Bloomfield Township",
      "parcel_filter_field": "CVTTAXDESCRIPTION",
      "source_type": "pdf_clearzoning",
      "zoning_map_url": "https://www.bloomfieldtwp.org/media/tynlmzsz/zoning-map-11x17.pdf",
      "ordinance_url": "https://www.bloomfieldtwp.org/clerk/zoning-ordinance/",
      "zone_code_field": null,
      "notes": "No public zoning FeatureServer verified in pre-stage."
    },
    "VILLAGE OF FRANKLIN": {
      "display_name": "Franklin",
      "parcel_filter_field": "CVTTAXDESCRIPTION",
      "source_type": "american_legal_plus_pdf_map",
      "zoning_map_url": "https://www.franklin.mi.us/community/maps.php",
      "ordinance_url": "https://codelibrary.amlegal.com/codes/franklin/latest/overview",
      "zone_code_field": null,
      "notes": "No public zoning FeatureServer verified in pre-stage."
    }
  }
}
```

This directory should not include matrix rows. It is only the acquisition/citation map that lets Lane A populate parcel `zoning_code` and lets orchestrator author matrix rows after ingest.
