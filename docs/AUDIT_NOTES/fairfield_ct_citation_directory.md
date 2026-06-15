# Fairfield County, CT - Wealth-Pocket Citation Directory (Pre-Stage)

**Date:** 2026-06-15
**Purpose:** Pre-stage citation sources for the Fairfield CT matrix sprint after Lane A schedules per-municipality Class B zoning ingest. Target municipalities are Greenwich from the 57-list, plus Westport, Darien, New Canaan, and Stamford as adjacent Fairfield County wealth-band and parcel-volume candidates.
**Status:** Read-only diagnostic. **Not authoritative until Lane A's Fairfield zoning ingest output lands.** `prod_city_value` values below are predictions from PR #228's `Town_Name` to `parcels.city` re-derivation and should be verified against prod after each municipal zoning source lands.

---

## Bottom line

| Muni set | Count |
|---|---:|
| Municipalities staged | 5 |
| Target-muni parcels in Fairfield prod today | 66,730 |
| Share of Fairfield parcels | 25.5% |
| Bergen-pattern fit | 1 YES / 4 PARTIAL / 0 NO |
| Zoning-source availability | 1 verified live ArcGIS MapServer / 3 public web-GIS or interactive maps without verified REST zoning layer / 1 PDF or hosted-code workflow |
| Expected matrix sprint hours at 5-10 min/code | 14-28h raw authoring |
| Recommended proof scope | Greenwich + Stamford first: direct 57-list wealth pocket plus largest target city and only verified live zoning layer |
| Recommended add-on scope | Westport, New Canaan, Darien in that order after source-field verification |

**Recommendation:** Stage Fairfield as **Class B per municipality**, not a countywide sprint. Connecticut zoning remains municipal under CGS Chapter 124, and PR #221 already dropped the CT CAMA embedded-zoning/Class C premise. PR #228 fixed the town join key by populating `parcels.city` from `raw->>'Town_Name'`, so the next gate is municipal zone-code acquisition.

**Layer-availability note:** Stamford is the only target with a verified public zoning service: `https://stamfordgis.org/public/rest/services/AGOL_Zoning/MapServer/3`, 377 polygons and 42 distinct `ZoningDistrict` values. Greenwich has an official interactive zoning app plus PDF maps, but the ArcGIS app item did not expose an operational zoning layer through the public item JSON. Westport uses AxisGIS and enCodePlus; Darien and New Canaan are mostly PDF/code workflows. Treat any hidden GIS endpoint discovered later as a Lane A preflight candidate, not as proven here.

---

## Live source probes used

- Fairfield city re-derivation baseline: `docs/OP5_FAIRFIELD_CT_CITY_REINGEST.md`
- Prior NY/CT structural diagnostic: `docs/PHASE2_NY_CT_DIAGNOSTIC.md`
- Greenwich building-zone regulations: `https://www.greenwichct.gov/442/Building-Zone-Regulations`
- Greenwich resource maps: `https://www.greenwichct.gov/440/Resource-Maps`
- Greenwich interactive zoning app: `https://greenwichgis.maps.arcgis.com/apps/instant/lookup/index.html?appid=dd08394df7544ef7862d946a2ad5d7a5`
- Westport zoning regulations: `https://online.encodeplus.com/regs/westport-ct/doc-viewer.aspx`
- Westport GIS map system: `https://www.axisgis.com/WestportCT/`
- Darien zoning regulations and map: `https://www.darienct.gov/301/Zoning-Regulations`
- New Canaan zoning regulations: `https://www.newcanaan.info/departments/land_use/planning___zoning/zoning_regulations.php`
- New Canaan 2025 zoning-regs update materials: `https://www.newcanaan.info/departments/land_use/planning___zoning/zoning_regs_update_2025.php`
- New Canaan web GIS: `https://hosting.tighebond.com/NewCanaanCT/`
- Stamford zoning regulations: `https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations`
- Stamford zoning map: `https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-map`
- Stamford live zoning layer: `https://stamfordgis.org/public/rest/services/AGOL_Zoning/MapServer/3`

PR #228 city distribution for target municipalities:

| Predicted prod_city_value | Parcel count |
|---|---:|
| `Greenwich` | 18,042 |
| `Westport` | 9,947 |
| `Darien` | 5,831 |
| `New Canaan` | 7,386 |
| `Stamford` | 25,524 |

---

## How to use this directory

1. After Lane A lands each Fairfield municipal zoning source, re-pull the actual uncovered `(city, zoning_code)` pairs from prod.
2. Use the PR #228 `parcels.city` values exactly: `Greenwich`, `Westport`, `Darien`, `New Canaan`, and `Stamford`.
3. Do not infer parcel zoning from CT CAMA `State_Use` or `Property_City`; PR #221 found no valid embedded zoning field.
4. For Stamford, prefer the city zoning layer's `ZoningDistrict` field if Lane A spatially backfills from `AGOL_Zoning/MapServer/3`.
5. For Greenwich, Westport, Darien, and New Canaan, expect a per-muni source adapter or manual source extraction unless Lane A finds and passes a hidden GIS layer through the strengthened preview gates.
6. Residential districts should default to prohibited for self-storage / mini-warehouse / light industrial / luxury garage condo unless a use table or district section explicitly permits the use.

---

## Greenwich

| Field | Value |
|---|---|
| Display name | Greenwich, CT |
| Predicted prod_city_value | `Greenwich` |
| Current Fairfield prod parcels | 18,042 |
| Canonical ordinance URL | `https://www.greenwichct.gov/442/Building-Zone-Regulations` |
| Zoning map / layer source | Interactive app plus official PDFs: `https://www.greenwichct.gov/440/Resource-Maps`; Town Zoning Map PDF `/DocumentCenter/View/14293/Town-Zoning-Map-PDF`; Business Zone Maps PDF `/DocumentCenter/View/42917/Business-Zone-Maps-PDF` |
| Verified public zoning FeatureServer | **NO**. App item `dd08394df7544ef7862d946a2ad5d7a5` did not expose public operational zoning layers in the item JSON. |
| Zoning section anchors | Division 9 Use Regulations; Section 6-100 Use Groups for Business Zones; Sections 6-103 through 6-108 for LBR, LB, GB, GBO, WB, and BEX-50; Division 21 schedule of open spaces/heights/bulk |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~25-35 codes; 4-6h after zone codes are populated |

Greenwich has strong official ordinance and map material but not a clean machine-readable public zoning layer from the live probe. The regulations are sectioned by district and use group rather than a single Bergen-style zone-code table. The business districts are citation-friendly; the residential districts need separate Division 9 and Division 21 reads.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `RA-4` | Greenwich Building Zone Regulations and Town Zoning Map | Cite Division 9 residence-use rules plus Division 21 area/height/bulk schedule. |
| `RA-2` | Greenwich Building Zone Regulations and Town Zoning Map | Same residence-zone pattern; verify area/bulk in Division 21. |
| `R-20` | Greenwich Building Zone Regulations and Town Zoning Map | Same residence-zone pattern; residential default unless a specific special use applies. |
| `LBR` | Section 6-103 use regulations and special requirements for LBR Zone | Cite Section 6-100 use groups plus Section 6-103. |
| `GB` | Section 6-105 use regulations and special requirements for GB Zone | Cite Section 6-100 use groups plus Section 6-105; commercial code needs use-level spot-check. |
| `BEX-50` | Section 6-108 use regulations for BEX-50 Zone | Cite Section 6-108 and any current text amendments affecting business-zone dwelling/unit rules. |

Sprint note: Greenwich is the direct 57-list wealth pocket, so it should lead the Fairfield sprint despite the less automated source. Lane A should try the official interactive map first, but this directory does not verify a public FeatureServer.

---

## Westport

| Field | Value |
|---|---|
| Display name | Westport, CT |
| Predicted prod_city_value | `Westport` |
| Current Fairfield prod parcels | 9,947 |
| Canonical ordinance URL | `https://online.encodeplus.com/regs/westport-ct/doc-viewer.aspx` |
| Town regulations page | `https://www.westportct.gov/government/departments-a-z/planning-and-zoning-department/zoning-and-subdivision-regulations` |
| Zoning map / layer source | Westport AxisGIS: `https://www.axisgis.com/WestportCT/` |
| Verified public zoning FeatureServer | **NO** from this pass. AxisGIS is reachable, and the town says the GIS map system can review zoning designations, but no ArcGIS REST zoning layer was verified. |
| Zoning section anchors | Section 14-2 Residence AAA District permitted uses; Sections 21-2, 24-2, 24A-2, 24B-2, 24C-2 for district-specific permitted uses; Section 32-7 prohibited uses; Section 42 map/amendment procedures |
| Bergen-pattern fit | **YES** |
| Estimated sprint scope | ~25-35 codes; 4-6h after zone codes are populated |

Westport is the cleanest ordinance-side target because enCodePlus exposes district chapters with permitted-use subsections. It is not county-standardized, but it is close enough to Bergen-style row authoring once Lane A can populate parcel zone codes from AxisGIS or another municipal source.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `AAA` | enCodePlus residence-district sections and Westport map/GIS | Cite Section 14-2 or corresponding residence district permitted-use section; residential default. |
| `AA` | enCodePlus residence-district sections and Westport map/GIS | Cite the corresponding residence district permitted-use section and residence summary schedule. |
| `A` | enCodePlus residence-district sections and Westport map/GIS | Same residence-district pattern. |
| `GBD` | Section 24 General Business District; Section 24-2 Permitted Uses | Cite Section 24-2 and Section 24-2.4 prohibited uses. |
| `GBD/S` | Section 24A General Business District/Saugatuck; Section 24A-2 Permitted Uses | Cite Section 24A-2 and related special-permit/prohibited-use subsections. |
| `RBD` | enCodePlus sign and district references; likely Retail Business District | Cite the specific RBD district chapter after ingest confirms exact code string. |

Sprint note: if AxisGIS can be exported or queried reliably, Westport should be fast. If AxisGIS remains UI-only, Lane A may need a map/PDF extraction path before matrix work can start.

---

## Darien

| Field | Value |
|---|---|
| Display name | Darien, CT |
| Predicted prod_city_value | `Darien` |
| Current Fairfield prod parcels | 5,831 |
| Canonical ordinance/map URL | `https://www.darienct.gov/301/Zoning-Regulations` |
| Regulations PDF | `https://www.darienct.gov/DocumentCenter/View/6613` |
| Zoning map PDF | `https://www.darienct.gov/DocumentCenter/View/6126` |
| Municode town code | `https://library.municode.com/ct/darien/codes/code_of_ordinances` |
| Verified public zoning FeatureServer | **NO**. The ArcGIS link found on the Darien page resolves to an AED Locator app/layer, not zoning. |
| Zoning section anchors | Town Zoning Regulations PDF; residential zones `R-2`, `R-1`, `R-1/2`, `R-1/3`, `R-1/5`; central/downtown business sections in the same PDF |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~15-25 codes; 3-5h after zone codes are populated |

Darien is a PDF workflow. The town page links current regulations, amendments, and zoning map PDFs, and the official page says the regulations are current through Amendment 104 effective May 10, 2026. There is no verified public zoning FeatureServer in this pass.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `R-2` | Darien regulations/map PDF; ADU rules also reference `R-2` | Cite the residential district section in the Zoning Regulations PDF; residential default. |
| `R-1` | Darien regulations/map PDF; ADU rules reference `R-1` | Same residential PDF pattern. |
| `R-1/2` | Darien regulations/map PDF; ADU rules reference `R-1/2` | Same residential PDF pattern. |
| `R-1/3` | Darien regulations/map PDF; ADU rules reference `R-1/3` | Same residential PDF pattern. |
| `R-1/5` | Darien regulations/map PDF; ADU rules reference `R-1/5` | Same residential PDF pattern. |
| `CBD` | Darien downtown materials and central business PDF references | Cite the Central Business District section in the regulations PDF; needs use-level spot-check. |

Sprint note: Darien should come after Greenwich/Westport/Stamford because it likely requires PDF-map extraction or manual district matching. It is still matrix-sprintable once zone codes exist because the district count appears modest.

---

## New Canaan

| Field | Value |
|---|---|
| Display name | New Canaan, CT |
| Predicted prod_city_value | `New Canaan` |
| Current Fairfield prod parcels | 7,386 |
| Canonical ordinance URL | `https://www.newcanaan.info/departments/land_use/planning___zoning/zoning_regulations.php` |
| eCode360 code/PDF | `https://www.ecode360.com/NE0075?needHash=true`; `https://ecode360.com/NE0075/laws/LF2192955.pdf` |
| Zoning map PDF | `https://www.newcanaan.info/Departments/Land%20Use/Zoning%20Map%2003.01.23.pdf` |
| Web GIS | `https://hosting.tighebond.com/NewCanaanCT/` |
| Verified public zoning FeatureServer | **NO** from this pass. The Tighe & Bond web GIS is reachable but no public REST zoning layer was verified. |
| Zoning section anchors | Section 3.5 Residence Zones; Section 4.8 Business Zones; Section 5 Special Zones; 2025 update page has "Existing Use Table Residence Zones", "Existing Use Conditions Residence Zones", and "Existing Permitted Uses" PDFs |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | ~25-35 codes; 4-6h after zone codes are populated |

New Canaan is mixed: current adopted regulations are PDF/eCode360-style, but the 2025 update page exposes cleaner use-table PDFs for residence zones and business-district work products. Treat those update materials as citation accelerators, not authoritative replacements, unless the town adopts them.

Sample code and citation pattern:

| Sample code | Source evidence | Citation pattern |
|---|---|---|
| `A Residence` | Current zoning regulations and map PDF | Cite Section 3.5 Residence Zones plus the residential area/bulk schedule. |
| `B Residence` | Current zoning regulations and map PDF; rear-lot PDF references B Residence Zone | Same residence-zone pattern. |
| `1/3 Acre Residence` | Current zoning regulations and map PDF | Cite Section 3.5 and schedule of residential requirements. |
| `Retail A` | Section 4.8 Business Zones | Cite Section 4.8 business-zone dimensional rules plus use/conditions section. |
| `Business A` | Section 4.8 Business Zones | Cite Section 4.8 and current business-zone use rules; update materials can help spot-check. |
| `Business B` | Section 4.8 Business Zones and update-material business PDFs | Same business-zone pattern; use-level spot-check required. |

Sprint note: New Canaan is not blocked, but the adopted-source vs 2025-update-source split is a real citation risk. Orchestrator should cite adopted code/regulations unless Master explicitly approves using update packets for pre-authoring hints.

---

## Stamford

| Field | Value |
|---|---|
| Display name | Stamford, CT |
| Predicted prod_city_value | `Stamford` |
| Current Fairfield prod parcels | 25,524 |
| Canonical ordinance URL | `https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations` |
| Zoning map URL | `https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-map` |
| Live zoning layer | `https://stamfordgis.org/public/rest/services/AGOL_Zoning/MapServer/3` |
| Verified public zoning FeatureServer/MapServer | **YES**. Layer 3 has 377 polygons and 42 distinct `ZoningDistrict` values. |
| District field | `ZoningDistrict`; description field `ZoningDescription` |
| Zoning section anchors | Section 4 Use Regulations and Standards; Section 5 Districts and District Regulations; Appendix A for moved district use regulations; Chapter 248 zoning code in Municode for local ordinances |
| Bergen-pattern fit | **PARTIAL** |
| Estimated sprint scope | 42 verified codes; 5-8h after zone codes are populated |

Stamford is the best Lane A source candidate among the five targets because the public MapServer exposes clean zoning polygon values. The ordinance side is more complex than Bergen: Stamford uses a long regulation PDF, district-specific sections, and recent moves of some use regulations to Appendix A.

Verified live sample from `AGOL_Zoning/MapServer/3`:

| Sample code | ZoningDescription | Citation pattern |
|---|---|---|
| `R-10` | One Family Residence | Cite Section 5 residential district regulations plus Section 4 use standards. |
| `R-20` | One Family Residence | Same residential district pattern. |
| `C-N` | Neighborhood Business | Cite the commercial district section and Section 4 use standards; spot-check prohibited/conditional uses. |
| `C-G` | General Commercial | Cite commercial district section plus Section 4; storage/industrial-adjacent uses require explicit read. |
| `M-G` | General Industrial | Cite industrial district section plus Section 4; likely most relevant non-residential code for storage/light industrial. |
| `MX-D` | Mixed Use Development | Cite district-specific section or Appendix A if moved; do not bulk-class from district name. |

Sprint note: if Lane A wants fastest technical proof inside Fairfield, Stamford should be first because the zoning layer is live and field names are known. If Master prioritizes the 57-list polygon, run Greenwich first and Stamford second.

---

## Recommended Fairfield sprint sequence

1. **Greenwich** - direct 57-list wealth pocket; ordinance is sectioned/PDF but official and stable. Expected 4-6h after zone-code ingest.
2. **Stamford** - largest target municipality and only verified live zoning MapServer. Expected 5-8h.
3. **Westport** - best ordinance-side fit through enCodePlus, but AxisGIS/source extraction needs Lane A verification. Expected 4-6h.
4. **New Canaan** - useful wealth-band add-on; adopted-source/update-source split needs care. Expected 4-6h.
5. **Darien** - small parcel count and PDF-heavy source; likely last. Expected 3-5h.

Expected target-muni matrix backlog: **20-31h including source verification friction**, or **14-28h raw authoring** after clean `(city, zoning_code)` values are available.

---

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Four of five targets lack a verified public zoning FeatureServer in this pass | Lane A cannot clone Stamford's spatial backfill blindly to all munis | Treat each muni as its own Class B source path; run strengthened preview gates before any spatial backfill. |
| Greenwich interactive app does not expose zoning layers through public item JSON | Direct 57-list target may need PDF/map extraction | Start Greenwich source acquisition early; do not defer until matrix sprint day. |
| Westport AxisGIS may be UI-only or export-limited | Clean enCodePlus citations still need parcel zone_code source | Probe AxisGIS export/API path before promising coverage. |
| New Canaan adopted regs and 2025 update materials diverge | Matrix citations could accidentally cite draft/work-product material | Cite adopted regulations for final rows; use update PDFs only as extraction aids unless adopted. |
| Stamford codes are clean but ordinance is complex | Incorrect bulk classifications for mixed-use/commercial/industrial districts | Author residential rows quickly; spot-check every business, industrial, mixed-use, and designed district. |
| CT town zoning is municipal under CGS Chapter 124 | No countywide directory or county zoning matrix applies | Directory file should key by `prod_city_value`, ordinance URL, source type, and zone-code field per muni. |

---

## Directory shape recommendation

Fairfield's directory should look like the Westchester Class B directory but with CT town values from PR #228:

```json
{
  "county": "Fairfield",
  "state": "CT",
  "municipalities": {
    "Greenwich": {
      "prod_city_value": "Greenwich",
      "source_type": "town_pdf_or_interactive_map",
      "ordinance_url": "https://www.greenwichct.gov/442/Building-Zone-Regulations",
      "map_url": "https://www.greenwichct.gov/440/Resource-Maps",
      "zone_code_field": null,
      "notes": "No verified public zoning FeatureServer in pre-stage."
    },
    "Stamford": {
      "prod_city_value": "Stamford",
      "source_type": "arcgis_mapserver",
      "zoning_layer_url": "https://stamfordgis.org/public/rest/services/AGOL_Zoning/MapServer/3",
      "zone_code_field": "ZoningDistrict",
      "zone_description_field": "ZoningDescription",
      "ordinance_url": "https://www.stamfordct.gov/government/boards-commissions/zoning-board/zoning-regulations"
    }
  }
}
```

This directory should not include matrix rows. It is only the acquisition/citation map that lets Lane A populate parcel `zoning_code` and lets orchestrator author matrix rows after ingest.
