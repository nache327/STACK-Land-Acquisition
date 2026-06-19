# Vessel Technologies B2B Opportunity Scoping

**Date:** 2026-06-19  
**Status:** Read-only diagnostic. No access negotiation, ingest, matrix authoring, or code changes performed.  
**Decision input:** **PURSUE, but as a business/legal access path first; do not dispatch Lane A for bulk ingest until Vessel grants usable service access and commercial-use terms.**

## Bottom Line

| Question | Verdict |
| --- | --- |
| ArcGIS org confirmed? | **YES** - ArcGIS Online org `KX6JS016gWFWiY6Y` resolves as `Vessel Technologies, Inc.` |
| Original service URL shape | `services.arcgis.com/.../services/?f=json` is not the working host shape; public item metadata points to `https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/.../FeatureServer` |
| Public service enumeration | **PARTIAL** - ArcGIS search exposes 203 public-indexed items, including 109 Feature Services and 85 zoning-title items. After dedupe, I found **47 unique zoning Feature Service titles**: **32 CT + 15 NJ** |
| Raw geometry/query access | **NO** for sampled endpoints - service roots and `/query` calls return ArcGIS `499 Token Required`; direct content item reads return `403 Subscription is disabled, the item is not accessible` |
| 85+ muni claim | **Not confirmed as 85 public zoning polygon services.** It is consistent with public-indexed zoning-related items including duplicate Service Definitions, Web Maps, and Web Experiences |
| 58-list overlap | **Useful but not campaign-dominating from public metadata alone.** Strongest immediate overlaps: Fairfield CT add-ons (`Westport`, `New Canaan`, `Fairfield`, `Norwalk`) and Burlington NJ direct wealth-tail (`Mount Laurel`). No public Vessel zoning layer found for direct Fairfield center `Greenwich`, nor for Darien/Stamford |
| Implementation if access is secured | **Class A spatial backfill candidate** via generic ArcGIS FeatureServer municipal-zoning adapter plus per-muni registration; likely 15-45 min/muni after field mapping and QA, not the 5-15 min/muni best-case until field homogeneity is proven |
| Master recommendation | **PURSUE** a Vessel access/license conversation plus a 3-muni technical pilot manifest request (`Westport CT`, `New Canaan CT`, `Mount Laurel NJ`). **Defer bulk ingest** until tokened access + commercial terms + field schema samples are available |

## Probe Summary

### ArcGIS org

Live probe:

```text
https://www.arcgis.com/sharing/rest/portals/KX6JS016gWFWiY6Y?f=json
```

Returned:

```json
{
  "name": "Vessel Technologies, Inc.",
  "id": "KX6JS016gWFWiY6Y",
  "urlKey": "vesseltechnologi",
  "customBaseUrl": "maps.arcgis.com",
  "portalHostname": "www.arcgis.com",
  "allSSL": true
}
```

The original discovery URL from the dispatch:

```text
https://services.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/?f=json
```

returned `Invalid URL`. The public item metadata uses the `services1.arcgis.com` host, for example:

```text
https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/Westport_CT_Zoning/FeatureServer
```

### Access behavior

Public ArcGIS search exposes item metadata, but sampled raw REST services are token-gated.

Examples:

```text
https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/Westport_CT_Zoning/FeatureServer?f=pjson
https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/New_Canaan_CT_Zoning/FeatureServer/0/query?f=pjson&where=1%3D1&returnCountOnly=true
https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/Mount_Laurel_NJ_Zoning/FeatureServer/0/query?f=pjson&where=1%3D1&returnCountOnly=true
https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/Connecticut_Town_Index/FeatureServer?f=pjson
https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/NJ_municipalities_shapefile/FeatureServer?f=pjson
```

All sampled service/query calls returned:

```json
{
  "error": {
    "code": 499,
    "message": "Token Required",
    "messageCode": "SB_0005",
    "details": ["Token Required"]
  }
}
```

Direct item reads also failed for sampled public-indexed items:

```text
https://www.arcgis.com/sharing/rest/content/items/1c74b596a68d4f378ee5f99590e43992?f=json
```

returned:

```json
{
  "error": {
    "code": 403,
    "messageCode": "SB_0005",
    "message": "Subscription is disabled, the item is not accessible",
    "details": []
  }
}
```

**Interpretation:** Vessel's ArcGIS search index is visible enough to enumerate candidates, but the actual FeatureServer data is not open-access through anonymous REST calls. This is a tokened/private access problem, not a Lane A adapter problem.

## Public-Indexed Inventory

Portal search:

```text
https://www.arcgis.com/sharing/rest/search?f=json&q=orgid:KX6JS016gWFWiY6Y&num=100
```

paged to 203 visible results:

| Item type | Count |
| --- | ---: |
| Feature Service | 109 |
| Service Definition | 58 |
| Web Map | 17 |
| Web Experience | 16 |
| Web Mapping Application | 1 |
| Layer Package | 1 |
| Code Attachment | 1 |

Search restricted to `zoning` returned 101 public-indexed results. The "85+" figure is plausible if counting zoning-title items and related apps/definitions, but it does **not** equal 85 unique publicly queryable zoning FeatureServer layers.

After deduping title-level Feature Services visible in the current search index, I found **47 unique zoning Feature Service titles**:

### CT zoning Feature Services visible in metadata

| Town | Feature service title |
| --- | --- |
| Avon | `Avon CT Zoning` |
| Bethel | `Bethel CT Zoning` |
| Bloomfield | `Bloomfield CT Zoning` |
| Cheshire | `Cheshire CT Zoning` |
| Cromwell | `Cromwell CT Zoning` |
| Essex | `Essex CT Zoning` |
| Fairfield | `Fairfield CT Zoning` |
| Farmington | `Farmington CT Zoning` |
| Glastonbury | `Glastonbury CT Zoning` |
| Granby | `Granby CT Zoning` |
| Groton | `Groton CT Zoning` |
| Hamden | `Hamden CT Zoning` |
| Middletown | `Middletown CT Zoning` |
| Milford | `Milford CT Zoning` |
| New Canaan | `New Canaan CT Zoning` |
| New Haven | `New Haven CT Zoning` |
| Newtown | `Newtown CT Zoning` |
| Norwalk | `Norwalk CT Zoning` |
| Old Saybrook | `Old Saybrook CT Zoning` |
| Orange | `Orange CT Zoning` |
| Oxford | `Oxford CT Zoning` |
| Rocky Hill | `Rocky Hills CT Zoning` |
| Shelton | `Shelton CT Zoning` |
| Simsbury | `Simsbury CT Zoning` |
| South Windsor | `South Windsor CT Zoning` |
| Stratford | `Stratford CT Zoning` |
| Trumbull | `Trumbull CT Zoning` |
| Wallingford | `Wallingford CT Zoning` |
| West Hartford | `West Hartford CT Zoning` |
| Westport | `Westport CT Zoning` |
| Wethersfield | `Wethersfield CT Zoning` |
| Windsor | `Windsor CT Zoning` |

### NJ zoning Feature Services visible in metadata

| Municipality | Feature service title |
| --- | --- |
| Belleville | `Belleville NJ Zoning` |
| Bloomfield | `Bloomfield_NJ_Zoning` |
| Bound Brook | `Bound_Brook_Zoning` |
| Carteret | `Carteret NJ Zoning` |
| East Orange | `EastOrange_Zoning` |
| Ewing | `Ewing Zoning` / `NJ_Zoning` service name |
| Hackensack | `Hackensack NJ Zoning` |
| Jersey City | `Jersey_City_Zoning` |
| Linden | `LindenZoning` |
| Mount Laurel | `Mount Laurel NJ Zoning` |
| Newark | `Newark Zoning Districts` |
| Orange | `Orange City Zoning` |
| Passaic | `Passaic Zoning` |
| Plainfield | `Plainfield Zoning` |
| Union City | `UnionCity_Zoning` |

Additional visible county Web Maps/Web Experiences:

| State | County map/app titles visible |
| --- | --- |
| CT | Hartford, Fairfield, New Haven, Middlesex CT, New London |
| NJ | Mercer, Middlesex NJ, Hudson, Essex, Union, Burlington, Bergen, Monmouth, Somerset, Passaic |

These county apps/maps may explain the broader "85+ munis" claim, but their data payloads were not anonymously readable through the direct item/data endpoints in this diagnostic.

## 58-List Overlap

### Direct or high-value overlap found

| 58-list geography | Vessel metadata overlap | Value |
| --- | --- | --- |
| Burlington NJ wealth-tail (`Moorestown`, `Medford`, `Mount Laurel`) | `Mount Laurel NJ Zoning` visible | **Direct 58-list muni overlap** for Mount Laurel |
| Fairfield CT (`Greenwich` direct; Westport/Darien/New Canaan/Stamford add-ons) | `Westport CT Zoning`, `New Canaan CT Zoning`, `Fairfield CT Zoning`, `Norwalk CT Zoning`, `Stratford CT Zoning`, `Trumbull CT Zoning`, `Shelton CT Zoning` visible | Useful Fairfield wedge add-ons; **does not solve Greenwich/Darien/Stamford from visible Vessel metadata** |
| Bergen NJ | County web map/app visible; `Hackensack NJ Zoning` visible | Possible NJ breadth, but Hackensack is not the known Bergen wealth center |
| Monmouth NJ | County web map/app visible; no visible Marlboro/Holmdel zoning layer in public-indexed Feature Services | Weak direct overlap |
| Somerset NJ | County web map/app visible; `Bound Brook`, `Plainfield` visible | Weak direct overlap |

### Important misses

Visible public-indexed zoning Feature Services did **not** include these known 58-list direct centers during this probe:

- Greenwich CT
- Darien CT
- Stamford CT
- Moorestown NJ
- Medford NJ
- Marlboro NJ
- Holmdel NJ
- Saddle River NJ
- Short Hills / Millburn NJ

This does not prove Vessel lacks those layers; it proves they were not visible as public-indexed zoning Feature Services in the current anonymous search results.

## Company / Access Model

Vessel Technologies is not presented publicly as a GIS data vendor. Its public website frames the company as a housing technology / attainable-housing developer; LinkedIn lists it in Real Estate, 11-50 employees, privately held, founded 2017, headquartered in New York. The ArcGIS org likely supports Vessel's internal site-acquisition / zoning analysis workflow rather than a commercial zoning-data SaaS.

Public contact path:

- Website: `https://www.vesseltechnologies.com/`
- Contact page: `https://www.vesseltechnologies.com/contact`
- Main phone from contact page: `+1 (212) 899 5353`
- Legal contact listed in footer: `legal@myvessel.com`
- Press contact listed: Jake Malcynsky / Gaffney Bennett PR, `jakemalcynsky@gbpr.com`

No public GIS-pricing page, API terms, freemium tier, redistribution terms, or commercial data license was found in the time-box.

**Access verdict:** **TOKEN-GATED / B2B.** The public metadata is enough to identify candidate services, but production use requires one of:

1. Vessel-issued ArcGIS token / shared group access with explicit commercial-use permission.
2. Written permission to use/export specific Feature Services.
3. A separate data-sharing agreement or purchase order.

Do **not** rely on public search visibility as a license or stable access grant.

## Implementation Complexity If Access Is Secured

### Expected adapter shape

If Vessel grants access, the technical path is familiar:

1. Build a Vessel ArcGIS municipal-zoning directory:
   - `municipality`
   - `state`
   - `service_url`
   - `layer_id`
   - `zone_code_field`
   - `source_access` / token handling
   - `source_updated_at` if exposed
2. Ingest district polygons through the existing `zoning_ingestion.ingest_zoning_districts` / ArcGIS FeatureServer pattern.
3. Run strengthened Class A preflight:
   - district bbox covers >= 50% of target parcel bbox
   - 1000-parcel `ST_Within` dry-run >= 50% match
4. For wedge jurisdictions, register per-muni jurisdictions and move parcels via the proven per-muni `UPDATE jurisdiction_id` pattern.
5. Refresh audit and apply matrix rows per municipality.

### Effort estimate

| Scope | Estimate | Notes |
| --- | ---:| --- |
| Access/legal diligence | Business decision | Required before any production ingest |
| Technical pilot on 3 services after access (`Westport CT`, `New Canaan CT`, `Mount Laurel NJ`) | 4-8h | Includes token setup, field audit, bbox/dry-run gates, one directory shape |
| Per additional muni with homogeneous schema | 15-45 min | Best case after adapter and field mapping are stable |
| Per additional muni with schema drift/source quirks | 1-2h | Field-name variance, unexpected geometry, or stale layer vintage |
| 47 visible zoning Feature Services | 12-30h after access | More realistic than 7-21h until field homogeneity is proven |
| 85+ private/unlisted munis if Vessel confirms manifest | 25-60h | Depends on whether those are true zoning polygon services and whether fields are consistent |

The dispatch's 5-15 min/muni estimate is plausible only after:

- tokened access works,
- layer schema is homogeneous,
- each layer passes bbox + dry-run gates,
- matrix/citation rows already exist or are pre-staged.

## Wedge Cohort Forecast

| Scenario | Operational-flip forecast |
| --- | --- |
| No Vessel access | 0 direct flips; metadata only helps source discovery |
| Access to 47 visible public-indexed zoning Feature Services | Roughly 25-35 plausible candidates after QA, but many are outside the canonical 58 and still need parcel/jurisdiction/matrix work |
| Access to a confirmed 85+ true zoning-service manifest | 60-65 candidates at 75% Path A success is plausible, but **not verified** by this public probe |
| 58-list direct impact from current visible metadata | Small immediate direct overlap: `Mount Laurel NJ`; Fairfield add-ons `Westport` and `New Canaan` are strong but not the direct `Greenwich` center |

This can still be a large strategic unlock, but it is better framed as a **Vessel partnership/data-rights opportunity** than an immediately dispatchable public FeatureServer ingestion sprint.

## Recommended Next Steps

1. **PURSUE business/legal access.** Master should decide whether to contact Vessel for data access and commercial-use terms. The public contact page supports general partnership/contact, but no negotiation was attempted in this diagnostic.
2. **Ask for a manifest before discussing price.** Minimum useful fields:
   - municipality
   - state
   - service URL
   - layer ID
   - zone code field
   - last updated date
   - intended license/terms
   - whether access is ArcGIS token, group share, export package, or API key
3. **Pilot three high-value services if access is granted:**
   - `Westport CT Zoning` - Fairfield wave add-on previously blocked on AxisGIS/source extraction.
   - `New Canaan CT Zoning` - Fairfield wave add-on previously blocked on Tighe & Bond/PDF workflow.
   - `Mount Laurel NJ Zoning` - direct Burlington 58-list wealth-tail target.
4. **Do not bulk ingest from public-indexed metadata alone.** The REST endpoints are token-gated and license-empty.
5. **Keep official municipal sources as fallback.** Vessel layers may be derived, stale, or internally normalized. Lane A still needs source-vintage and code-field QA against municipal sources before binding matrix rows.

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Token-gated REST services | Blocks immediate adapter work | Secure Vessel token/shared group/export first |
| No explicit commercial license | Legal/commercial-use risk | Master/legal review before production use |
| Public search index overstates available data | 85+ claim may include definitions/apps/duplicates/private services | Require Vessel manifest and sample layer access |
| Layer vintage drift | Zoning polygons may not match current municipal ordinances | Capture update timestamps and spot-check against town zoning maps |
| Field-name variance | Generic adapter may need per-layer mapping | Pilot 3 services and build directory field map |
| Derived/private analysis data | Vessel may have digitized from PDFs or internal planning assumptions | Validate geometry against official muni map before operational flip |
| Direct 58-list overlap is limited from visible metadata | Could deliver breadth but not near-term target count | Prioritize Mount Laurel + Fairfield add-ons first |
| ArcGIS subscription disabled / private sharing changes | Access may be unstable without formal share | Use explicit tokened or exported delivery with terms |

## Source Links

- Vessel ArcGIS portal probe: `https://www.arcgis.com/sharing/rest/portals/KX6JS016gWFWiY6Y?f=json`
- Vessel ArcGIS org search: `https://www.arcgis.com/sharing/rest/search?f=json&q=orgid:KX6JS016gWFWiY6Y&num=100`
- Vessel website: `https://www.vesseltechnologies.com/`
- Vessel contact page: `https://www.vesseltechnologies.com/contact`
- Vessel LinkedIn: `https://www.linkedin.com/company/vessel-technologies-inc`
- Canonical 58-list: `docs/TARGET_MARKETS.md`
- Fairfield pre-stage context: `docs/AUDIT_NOTES/fairfield_ct_citation_directory.md`
