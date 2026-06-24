# Burlington NJ structural probe v2

Date: 2026-06-23  
Scope: read-only source probe for Burlington County, NJ wealth-tail munis: Moorestown, Medford, Mount Laurel. No ingest, matrix edits, or production writes.

## Bottom line

**Verdict: Burlington is not county-level operationally flippable today. It is a per-muni wave with mixed blockers.**

| Muni | Current parcel zoning state | Best source found | Source class | Matrix state | Recommended next action |
|---|---:|---|---|---|---|
| Medford Township | 9,877 / 9,880 parcels zoned (100.0%) | ZoningHub ArcGIS FeatureServer | Class B per-muni FeatureServer | 22 / 25 parcel-exposed zones covered | Finish 3 missing matrix rows, then per-muni registration/audit |
| Mount Laurel Township | 0 / 18,518 parcels zoned in prod | GovPilot public parcel-detail `ZONING` field + GovPilot zoning polygons | Class C-like embedded field, with Class B polygon cross-check | 1 row only (`I`) | Build/verify GovPilot adapter; then matrix pass |
| Moorestown Township | 0 / 7,575 parcels zoned in prod | GovPilot public zoning polygon layer | Class B per-muni GovPilot polygons | 4 rows only | Build/verify GovPilot polygon adapter; then matrix pass |

**Expected ops-count lift:** county umbrella remains blocked, but the three target munis are plausible per-muni operational flips. If Master tracks the Phase 1 Burlington wealth-tail polygon as one regional polygon, the realistic closure path is all three munis. If the operational unit is per-muni, expected lift is up to **+3 jurisdictions** after source + matrix completion.

**Ranked next-fire order:** Medford first, Mount Laurel second, Moorestown third.

## Current prod state

Jurisdiction checked: `Burlington County, NJ` / `d316fb43-d0e6-4359-aa47-6475fa99cc0f`.

Read-only DB probe:

| Metric | Value |
|---|---:|
| Total parcels | 174,852 |
| Parcels with non-empty `zoning_code` | 9,878 |
| County-wide `zoning_code` coverage | 5.65% |
| Distinct populated parcel zones | 26 |
| Distinct parcel `city` values | 41 |

Target muni split:

| City value | Parcels | Zoned | Coverage | Distinct populated zones |
|---|---:|---:|---:|---:|
| Mount Laurel township | 18,518 | 0 | 0.0% | 0 |
| Medford township | 9,880 | 9,877 | 100.0% | 25 |
| Moorestown township | 7,575 | 0 | 0.0% | 0 |
| Medford Lakes borough | 1,643 | 0 | 0.0% | 0 |

Current `zoning_districts` for the Burlington jurisdiction are Medford-only:

| Districts | Distinct codes | Medford-like | Moorestown-like | Laurel-like |
|---:|---:|---:|---:|---:|
| 94 | 25 | 94 | 0 | 0 |

This confirms the county-level gate cannot be reached from the current state. Even perfect Medford matrix coverage only covers about 5.6% of Burlington County parcels.

## Medford Township

### Source

Live FeatureServer:

`https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/ME0295_ZoningDistricts_04282023/FeatureServer/0`

Probe result:

| Check | Result |
|---|---|
| Layer type | Polygon Feature Layer |
| Total features | 94 |
| Zone field | `Layer` |
| 50-feature sample | 50 / 50 non-null `Layer` |
| Sample zone values | `APA`, `AR`, `CC`, `FD`, `GMS`, `HVC`, `HVR`, `PD`, `PPE`, `RC`, `RHO`, `SAPA` |

### Current parcel/matrix gap

Medford parcel zones in prod:

`GD`, `RGD-1`, `RGD-2`, `GMN`, `GMN-AR`, `HM`, `RS-2`, `GMS`, `AR`, `RHO`, `CC`, `HVC`, `VRD`, `RS-1`, `PPE`, `HVR`, `RC`, `HC-1`, `PD`, `FD`, `RHC`, `HC-2`, `PI`, `SAPA`, `APA`.

Current matrix rows for `Medford township`: 22 rows / 22 distinct codes, all human-reviewed. Missing parcel-exposed codes:

| Missing code | Parcel count |
|---|---:|
| `GD` | 3,226 |
| `CC` | 158 |
| `PD` | 30 |

Medford is therefore **matrix-near-ready**, not source-blocked. The missing codes are enough to keep matrix-zone-match below the 70% gate if evaluated as a per-muni jurisdiction.

Recommended action: nache/orchestrator completes `GD`, `CC`, `PD`, then Lane A/nache can carve/register Medford as a per-muni jurisdiction and refresh audit. No new source acquisition is needed for Medford.

## Mount Laurel Township

### Source

No anonymous ArcGIS FeatureServer was found for Mount Laurel through ArcGIS search. However, the public GovPilot map exposes both:

1. A parcel-detail `ZONING` field.
2. A queryable `Zoning Map` polygon layer.

Public map:

`https://map.govpilot.com/map/NJ/mountlaurel`

GovPilot metadata in the public page:

| Field | Value |
|---|---|
| `accountName` | `MOUNT LAUREL TOWNSHIP` |
| `uid` | `6968` |
| `GMID` | `136` |
| `GCID` | `14` |
| Public parcel panel | includes `ZONING` |
| Public layers | includes `Zoning Map` |

Layer enumeration endpoint:

`POST https://map.govpilot.com/api/v1/cmd/get/017` with body `[136]`

This returns layer code `ZM` / `Zoning Map`.

Polygon endpoint:

`POST https://map.govpilot.com/api/v1/cmd/get/015` with body `[136,"ZM","<bbox polygon>"]`

Small-bbox polygon sample result:

| Check | Result |
|---|---|
| Returned features | 65 |
| Features with zone text in `DESC` | 65 / 65 |
| Zone field pattern | `ZONE:<name>|ZONE2:<code>|` |
| Distinct sampled codes | `B`, `FR-MX`, `I`, `MCD`, `MH-MF`, `NC`, `O-2`, `O-3`, `ORC`, `R-1`, `R-2`, `R-3`, `R-4`, `R-8`, `R1D`, `SAAD`, `SRI` |

Parcel endpoint:

`POST https://map.govpilot.com/api/v1/cmd/get/GET-PARCELS` with body `[6968,"NJ",14,136,"<bbox polygon>"]`

Parcel detail endpoint:

`POST https://map.govpilot.com/api/v1/cmd/get/025S` with body `["MPNJ","<parcel id>"]`

50 parcel-detail sample:

| Check | Result |
|---|---|
| Parcel details sampled | 50 |
| Non-null `ZONING` | 50 / 50 |
| Sample distinct `ZONING` values | `CHRC`, `CSFA`, `I`, `R3`, `RAMW`, `SGVE`, `TARA` |
| Example | `3836 CHURCH RD`, `ZONING=CSFA` |

Vessel Tech also exposes a `Mount_Laurel_NJ_Zoning` FeatureServer title, but the REST endpoint returns `499 Token Required`, so it is not an anonymous immediate path:

`https://services1.arcgis.com/KX6JS016gWFWiY6Y/arcgis/rest/services/Mount_Laurel_NJ_Zoning/FeatureServer`

### Current gap

Prod has 18,518 Mount Laurel parcels and 0 populated `zoning_code`. Existing matrix has only one Mount Laurel row (`I`). Mount Laurel is **source + matrix blocked**, but the source blocker now looks solvable through GovPilot without Vessel Tech B2B access.

Recommended action: verify a GovPilot adapter path. Prefer parcel-detail `ZONING` as the fast path, with `ZM` polygons as a spatial QA/backfill cross-check. If the adapter is accepted, Mount Laurel becomes a normal per-muni matrix sprint.

## Moorestown Township

### Source

No anonymous ArcGIS FeatureServer was found for Moorestown through ArcGIS search. The public GovPilot map exposes a queryable `Zoning Map` polygon layer, but sampled parcel details have blank `ZONING`.

Public map:

`https://map.govpilot.com/map/NJ/moorestown`

GovPilot metadata in the public page:

| Field | Value |
|---|---|
| `accountName` | `MOORESTOWN TOWNSHIP` |
| `uid` | `7555` |
| `GMID` | `139` |
| `GCID` | `14` |
| Public parcel panel | includes `ZONING` |
| Public layers | includes `Zoning Map` |

Layer enumeration endpoint:

`POST https://map.govpilot.com/api/v1/cmd/get/017` with body `[139]`

This returns layer code `ZM` / `Zoning Map`.

Polygon endpoint:

`POST https://map.govpilot.com/api/v1/cmd/get/015` with body `[139,"ZM","<bbox polygon>"]`

Polygon sample result:

| Check | Result |
|---|---|
| Returned features | 54 |
| Zone field pattern | `M_ZoneCode:<code>|M_ZoneDesc:<description>|...` |
| Distinct sampled labels | `AR-1`, `L-MR`, `LTC`, `R-3-TH`, `R1`, `R1-Aa`, `R1A`, `R2`, `R3`, `RLC`, `RLC-2`, `SC-1`, `SRC`, `SRC-1`, `SRC-2`, `SRI` |
| Vintage signal | `Map_Source: Environmental Resolutions`, `Map_date: 08/27/2008`, `LastUpdate: 20140715` or `20090901` in sampled records |

Parcel-detail sample:

| Check | Result |
|---|---|
| Parcel details sampled | 50 |
| Non-null `ZONING` | 0 / 50 |
| Example | `701 BORTONS LANDING RD`, `ZONING=""` |

### Current gap

Prod has 7,575 Moorestown parcels and 0 populated `zoning_code`. Existing matrix has four Moorestown rows (`BP-1`, `BP-2`, `LTC`, `SRC`). Moorestown is **source + matrix blocked**, but the source blocker looks like a GovPilot polygon-backfill adapter rather than a manual PDF path.

Risk: sampled GovPilot polygon records have older source/vintage metadata and do not prove full modern code coverage by themselves. This should get a bbox/dry-run gate before any production write.

Recommended action: Lane A/nache verifies full GovPilot `ZM` layer extraction and performs the usual district-bbox/parcel-match preflight. If it passes, Moorestown becomes a per-muni matrix sprint.

## Statewide / countywide source check

### Burlington County parcel source

Existing parcel endpoint:

`https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0`

Sampled fields do **not** include a zoning field. Relevant fields include `PAMS_PIN`, `PCL_MUN`, `MUN_NAME`, `PROP_CLASS`, `PROP_USE`, `BLDG_CLASS`, and assessment/location fields. This confirms the current parcel source does not solve `zoning_code` on its own.

### NJDCA / NJGIN equivalent

No statewide or countywide Burlington municipal zone-district polygon source was found through NJGIN/ArcGIS search. Existing onboarding notes also distinguish NJDCA statewide municipal zoning from true zone-district polygons. Burlington remains a municipal-source problem, not a statewide NJDCA-style unlock.

### Vessel Tech

Vessel Tech is relevant only for Mount Laurel among the three target munis found here. It is token-gated and therefore a B2B path, not an immediate anonymous ingest source.

## Classification

| Unit | Classification | Reason |
|---|---|---|
| Burlington County umbrella | Source-blocked / wedge-affected | 5.65% parcel `zoning_code`; county-level flip unreachable from wealth-tail muni work |
| Medford Township | Matrix-blocked | Source and parcel zoning are already present; 3 parcel-exposed zone codes missing matrix rows |
| Mount Laurel Township | Source + matrix blocked, but source now viable | GovPilot parcel detail has 50/50 non-null `ZONING`; matrix has only `I` |
| Moorestown Township | Source + matrix blocked, but source now viable | GovPilot `ZM` polygons are queryable; parcel `ZONING` blank; matrix partial |

## Recommended hand-off

1. **Do not spend more effort trying to flip Burlington County as an umbrella.** The coverage math is structurally wrong for the wealth-tail polygon.
2. **Carve/register Medford / Mount Laurel / Moorestown as per-muni jurisdictions.**
3. **Medford:** nache/orchestrator completes matrix rows for `GD`, `CC`, `PD`; Lane A/nache applies per-muni registration and audit.
4. **Mount Laurel:** Lane A/nache verifies GovPilot `ZONING` parcel-detail extraction and/or `ZM` polygon extraction. If accepted, run matrix sprint for remaining codes.
5. **Moorestown:** Lane A/nache verifies GovPilot `ZM` polygon extraction with bbox and parcel-match preflight. If accepted, run matrix sprint for exposed codes.

This is a real infrastructure acceleration path. The prior state made Moorestown/Mount Laurel look acquisition-blocked or Vessel-Tech-dependent; the public GovPilot backend gives a plausible anonymous source path for both, with Mount Laurel especially strong because `ZONING` is embedded in sampled parcel details.
