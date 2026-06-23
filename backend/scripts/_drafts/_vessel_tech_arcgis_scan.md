# Vessel Tech ArcGIS scan

Date: 2026-06-23  
Scope: read-only source discovery probe for Vessel Technologies ArcGIS org `KX6JS016gWFWiY6Y`. No ingest, no code changes, no matrix work, and no access negotiation performed.

## Verdict

**HALT for anonymous ingest. PURSUE as a B2B/tokened-access opportunity.**

Live ArcGIS search still exposes Vessel Technologies, Inc. metadata and 47 true municipal zoning Feature Service titles. The actual FeatureServer REST roots all return ArcGIS `499 Token Required`, so the 50-feature field audit cannot be performed anonymously.

Operator signal:

- **0/47 true zoning Feature Services are anonymously queryable.**
- **47/47 should be treated as tokened Class B per-muni FeatureServer candidates**, not public dispatch-ready sources.
- The best B2B pilot set remains **Mount Laurel NJ + Westport CT + New Canaan CT**, with **Fairfield CT + Norwalk CT** as second-wave add-ons if Vessel access is granted.
- Expected lift without Vessel access: **0 ops**.
- Expected lift if Master secures tokened pilot access: **+3 high-confidence candidates** (`Mount Laurel`, `Westport`, `New Canaan`), with a plausible **+3-5 total** if Fairfield/Norwalk-style add-ons are accepted into the Fairfield/Burlington waves.

## Live access probes

Portal probe:

`https://www.arcgis.com/sharing/rest/portals/KX6JS016gWFWiY6Y?f=json`

Result:

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

The original service-host shape is invalid:

`https://services.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/?f=json`

returns:

```json
{"error":{"code":400,"message":"Invalid URL","details":["Invalid URL"]}}
```

Public item metadata points to the `services1.arcgis.com` host. Example:

`https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/Westport_CT_Zoning/FeatureServer?f=json`

returns:

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

Direct item metadata for sampled public-indexed items is also blocked. Example:

`https://www.arcgis.com/sharing/rest/content/items/1c74b596a68d4f378ee5f99590e43992?f=json`

returns:

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

## Inventory method

Two searches were used:

1. `q=orgid:KX6JS016gWFWiY6Y type:"Feature Service" zoning` returned 47 Feature Service results, but included `Belleville Avoid Zone` and missed `LindenZoning`.
2. Full-org paging over 203 visible items, filtered to Feature Services with `zon` in title or URL, returned 48 zoning-like services.

`Belleville Avoid Zone` is not a municipal zoning district source, so it is excluded from the 47 true zoning-candidate table below. `LindenZoning` is included.

## Full 47-title table

Sample-quality shorthand:

- `499 root`: service root returned `Token Required`; no 50-feature sample possible.
- `Field`: unknown until tokened access is granted.
- `Class`: `B-tokened` means a per-muni FeatureServer candidate behind access. It is not a statewide Class A source and not embedded parcel Class C.

| # | State | Muni | Feature Service title | Source class | 58-list match | Sample quality | ROI rank |
|---:|---|---|---|---|---|---|---|
| 1 | NJ | Mount Laurel | `Mount Laurel NJ Zoning` | B-tokened per-muni FeatureServer | **Direct Burlington NJ wealth-tail** | 499 root; field unknown | **1** |
| 2 | CT | Westport | `Westport CT Zoning` | B-tokened per-muni FeatureServer | Fairfield CT add-on; deferred source path | 499 root; field unknown | **2** |
| 3 | CT | New Canaan | `New Canaan CT Zoning` | B-tokened per-muni FeatureServer | Fairfield CT add-on; deferred source path | 499 root; field unknown | **3** |
| 4 | CT | Fairfield | `Fairfield CT Zoning` | B-tokened per-muni FeatureServer | Fairfield County breadth, not named center | 499 root; field unknown | 4 |
| 5 | CT | Norwalk | `Norwalk CT Zoning` | B-tokened per-muni FeatureServer | Fairfield County breadth, not named center | 499 root; field unknown | 5 |
| 6 | CT | Trumbull | `Trumbull CT Zoning` | B-tokened per-muni FeatureServer | Fairfield County breadth, not named center | 499 root; field unknown | 6 |
| 7 | CT | Shelton | `Shelton CT Zoning` | B-tokened per-muni FeatureServer | Fairfield County breadth, not named center | 499 root; field unknown | 7 |
| 8 | CT | Newtown | `Newtown CT Zoning` | B-tokened per-muni FeatureServer | Fairfield CT adjacent/background only | 499 root; field unknown | 8 |
| 9 | NJ | Hackensack | `Hackensack NJ Zoning` | B-tokened per-muni FeatureServer | Bergen NJ breadth, not known direct wealth center | 499 root; field unknown | 9 |
| 10 | NJ | Bloomfield | `Bloomfield_NJ_Zoning` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 10 |
| 11 | NJ | Belleville | `Belleville NJ Zoning` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 11 |
| 12 | NJ | Newark | `Newark Zoning Districts` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 12 |
| 13 | NJ | Jersey City | `Jersey_City_Zoning` | B-tokened per-muni FeatureServer | Hudson NJ breadth only | 499 root; field unknown | 13 |
| 14 | NJ | Passaic | `Passaic Zoning` | B-tokened per-muni FeatureServer | Passaic NJ breadth only | 499 root; field unknown | 14 |
| 15 | NJ | Plainfield | `Plainfield Zoning` | B-tokened per-muni FeatureServer | Somerset/Union breadth only | 499 root; field unknown | 15 |
| 16 | NJ | Bound Brook | `Bound_Brook_Zoning` | B-tokened per-muni FeatureServer | Somerset NJ breadth only | 499 root; field unknown | 16 |
| 17 | NJ | Ewing | `Ewing Zoning` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 17 |
| 18 | NJ | Carteret | `Carteret NJ Zoning` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 18 |
| 19 | NJ | East Orange | `EastOrange_Zoning` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 19 |
| 20 | NJ | Orange City | `Orange City Zoning` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 20 |
| 21 | NJ | Union City | `UnionCity_Zoning` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 21 |
| 22 | NJ | Linden | `LindenZoning` | B-tokened per-muni FeatureServer | NJ breadth only | 499 root; field unknown | 22 |
| 23 | CT | Avon | `Avon CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 23 |
| 24 | CT | Bethel | `Bethel CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 24 |
| 25 | CT | Bloomfield | `Bloomfield CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 25 |
| 26 | CT | Cheshire | `Cheshire CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 26 |
| 27 | CT | Cromwell | `Cromwell CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 27 |
| 28 | CT | Essex | `Essex CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 28 |
| 29 | CT | Farmington | `Farmington CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 29 |
| 30 | CT | Glastonbury | `Glastonbury CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 30 |
| 31 | CT | Granby | `Granby CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 31 |
| 32 | CT | Groton | `Groton CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 32 |
| 33 | CT | Hamden | `Hamden CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 33 |
| 34 | CT | Middletown | `Middletown CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 34 |
| 35 | CT | Milford | `Milford CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 35 |
| 36 | CT | New Haven | `New Haven CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 36 |
| 37 | CT | Old Saybrook | `Old Saybrook CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 37 |
| 38 | CT | Orange | `Orange CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 38 |
| 39 | CT | Oxford | `Oxford CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 39 |
| 40 | CT | Rocky Hill | `Rocky Hills CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 40 |
| 41 | CT | Simsbury | `Simsbury CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 41 |
| 42 | CT | South Windsor | `South Windsor CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 42 |
| 43 | CT | Stratford | `Stratford CT Zoning` | B-tokened per-muni FeatureServer | Fairfield County breadth, not named center | 499 root; field unknown | 43 |
| 44 | CT | Wallingford | `Wallingford CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 44 |
| 45 | CT | West Hartford | `West Hartford CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 45 |
| 46 | CT | Wethersfield | `Wethersfield CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 46 |
| 47 | CT | Windsor | `Windsor CT Zoning` | B-tokened per-muni FeatureServer | CT breadth only | 499 root; field unknown | 47 |

Excluded from the 47 true-zoning table:

| Title | Reason |
|---|---|
| `Belleville Avoid Zone` | Zoning-like title but not a municipal zoning district source. Also token-gated. |

## Top 5 B2B pilot candidates

| Rank | Candidate | Why Master should ask for it | Expected lift if access works |
|---:|---|---|---:|
| 1 | Mount Laurel NJ | Direct Burlington NJ wealth-tail target; prior Burlington source manifest had Mount Laurel acquisition-blocked | +1 |
| 2 | Westport CT | Fairfield CT deferred add-on; prior Fairfield pre-stage flagged AxisGIS/source extraction friction | +1 |
| 3 | New Canaan CT | Fairfield CT deferred add-on; prior Fairfield pre-stage flagged adopted-regs/source split and no clean public layer | +1 |
| 4 | Fairfield CT | Same county as Greenwich/Stamford wave; useful breadth if parcel substrate is already clean | +0-1 |
| 5 | Norwalk CT | Large Fairfield County muni with visible Vessel title; not a canonical named center but useful if Master values county breadth | +0-1 |

Do not spend negotiation energy on the lower-ranked NJ breadth titles first unless Master has a separate customer signal for that municipality.

## Source-class rating

Per `docs/INGESTION_PIPELINE_PLAN.md`:

- Not Class A: no statewide or countywide public zoning polygon source.
- Not Class C: no parcel-embedded zoning field is visible from this org metadata.
- Not immediately Class D: public metadata strongly suggests real per-muni FeatureServices exist.
- Best classification: **Class B per-muni FeatureServer, tokened/private**.

If Vessel grants tokened access, Lane A should treat each title like the proven per-muni Class B pattern:

1. Add per-title directory entry.
2. Read FeatureServer metadata with token.
3. Identify code field and geometry layer.
4. Run bbox and 1,000-parcel ST_Within dry-run gates.
5. Ingest zoning districts.
6. Backfill per-muni parcels.
7. Apply matrix rows against official municipal ordinance citations.

## Expected ops-count lift

| Scenario | Ops-count lift | Reason |
|---|---:|---|
| No Vessel token/access | 0 | All 47 true zoning FeatureServers return `499 Token Required` anonymously. |
| Pilot access for top 3 | +3 | Mount Laurel, Westport, New Canaan are the strongest visible 58-list / deferred-wave overlaps. |
| Pilot + Fairfield breadth add-ons | +3-5 | Fairfield and Norwalk/Trumbull/Shelton may add count if Master accepts county-breadth ops beyond named centers. |
| Full 47-service access | Unknown, likely far below 47 immediate flips | Each muni still needs parcel substrate, jurisdiction registration, source QA, and matrix citations. Metadata alone does not prove field quality. |

## Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Token-gated REST | Blocks anonymous sampling and adapter dispatch | Master must secure token/shared group/export first. |
| Commercial-use rights unclear | Could block use even if technical token works | Ask explicitly for permitted commercial use and redistribution limits. |
| Field schema unknown | No code-field or geometry QA possible now | Require 5-row samples or tokened read access before Lane A sprint. |
| Derived/private data | Vessel layers may not be authoritative municipal records | Validate code fields and geometry against official ordinance/map before flip. |
| Search index drift | Simple `zoning` search missed `LindenZoning` and included `Belleville Avoid Zone` | Use full-org paged inventory for future scans. |
| 58-list overlap limited | Visible metadata does not include Greenwich, Darien, Stamford, Moorestown, Medford, Marlboro, Holmdel, Saddle River, or Millburn | Use Vessel as targeted pilot, not as a guaranteed campaign-wide unlock. |

## Recommendation

**PURSUE B2B contact, but do not dispatch Lane A until access is secured.**

Master's ask should be concrete:

1. Tokened ArcGIS access or export for `Mount Laurel NJ Zoning`, `Westport CT Zoning`, and `New Canaan CT Zoning`.
2. Commercial-use terms and redistribution/derivative restrictions.
3. A 5-row attribute sample for each pilot layer if token access cannot be granted immediately.
4. Confirmation whether Vessel has non-public layers for the visible misses: Greenwich, Darien, Stamford, Moorestown, Medford, Marlboro, Holmdel, Saddle River, and Millburn.

This scan confirms that the opportunity is real enough for a business conversation, but not technically accessible enough for anonymous ingest work.

