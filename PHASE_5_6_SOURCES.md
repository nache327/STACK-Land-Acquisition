# Phase 5/6 Jurisdiction Source Plan

**Status as of 2026-05-12.** This is a decision artifact — no jurisdiction rows
get created from this doc. It catalogues, for each of the 15 untouched Phase 5/6
jurisdictions, the most plausible public parcel + zoning sources discoverable
today, along with confidence and blocking-issue notes so future ingestion work
can be sequenced by ROI.

**Methodology.** Each section was probed via ArcGIS Hub keyword search (`hub_search`
for `parcels {county} {state}` and `zoning {county} {state}`), supplemented with
direct knowledge of well-known county GIS portals where Hub results were
dominated by adjacent-county noise. URLs marked _verified-shape_ were probed by
inspecting the FeatureServer metadata; _unverified_ means the URL pattern is
plausible but the layer hasn't been opened.

**Confidence rubric.**
- **High** — county-published, polygon zoning at a recognizable URL, large enough
  to plausibly cover the whole county.
- **Medium** — county has a recognized GIS portal but the discovered candidate is
  generic/incomplete and may need manual verification.
- **Low** — Hub search produced only adjacent-county or unrelated layers; the
  jurisdiction likely needs a manual portal hunt or per-municipality work.
- **None** — no public county-wide zoning found; per-municipality work required.

**Blocking-issue taxonomy.**
- `none` — discoverable, ready for ingest.
- `municipal-only` — county has no county-wide zoning; data lives at each
  municipality (NJ-style per-town work needed).
- `token-gated` — service requires API key or portal auth.
- `partner-only` — county data is contracted out and not in public Hub.
- `no-public-data` — confirmed via manual portal probe that county doesn't
  publish a zoning layer.

---

## 1. Williamson County, TN

- **Parcel candidate**: `https://services1.arcgis.com/L0MLvN0Ay0iEjnCT/arcgis/rest/services/Parcels/FeatureServer` (Hub: top hit, plausible — TN STS-coded org)
- **Zoning candidate**: none found via Hub (top zoning hit was Knox County, wrong jurisdiction).
- **Confidence**: parcels Medium, zoning Low.
- **Blocking issue**: `municipal-only` likely — Williamson County's incorporated cities (Franklin, Brentwood, Spring Hill, Nolensville, Thompson's Station) handle their own zoning; unincorporated areas may be county-zoned but the layer isn't in Hub.
- **Recommended action**: probe parcel URL first; if it returns >250k features, ingest as Phase 1 (parcels-only T2). Then build NJ-style per-municipality discovery for Franklin/Brentwood as the high-value subset.
- **Prior-session note**: marked "auto-discovered URLs returned 0 features (schema-only / token-gated)" — re-probe before re-attempting.

---

## 2. Fulton County, GA

- **Parcel candidate**: county runs ArcGIS at `gisweb.fultoncountyga.gov`; Hub doesn't surface it cleanly. Manual probe needed at
  `https://gisweb.fultoncountyga.gov/arcgis/rest/services/Sandbox/FultonCountyParcels/FeatureServer`.
- **Zoning candidate**: same portal — `https://gisweb.fultoncountyga.gov/arcgis/rest/services/Sandbox/FultonCountyZoning/FeatureServer`. Unverified URL pattern; Atlanta itself zones independently.
- **Confidence**: Medium for unincorporated; Low for Atlanta city limits.
- **Blocking issue**: Atlanta zoning is municipal (City of Atlanta portal). Unincorporated Fulton + the smaller cities (Roswell, Alpharetta, Sandy Springs, Johns Creek, Milton, Chattahoochee Hills, Union City, College Park, East Point, Hapeville, Palmetto, Fairburn, Mountain Park) may each have their own.
- **Recommended action**: ingest county parcels first (covers all 15 cities + unincorporated). Then run zoning_discovery with `municipality_name` set per city — Fulton is a strong NJ-loop candidate.
- **Prior-session note**: also flagged "0 features returned" — county's public layer may require Atlanta Regional Commission as proxy.

---

## 3. Mecklenburg County, NC

- **Parcel candidate**: Mecklenburg/Charlotte runs one of the best public GIS portals in the US (`maps.mecklenburgcountync.gov`). Likely service:
  `https://maps.mecklenburgcountync.gov/arcgis/rest/services/Parcels/MapServer`. Hub returns noise ("Potential New Park Parcels Mecklenburg", "Educational Institutions").
- **Zoning candidate**: City of Charlotte's UDO (Unified Development Ordinance) published Aug 2023 — service likely at
  `https://services.arcgis.com/ZBVHrl4yIWqWRq45/arcgis/rest/services/Zoning/FeatureServer` (Charlotte's org). Unincorporated Mecklenburg is sparse.
- **Confidence**: parcels High, zoning High for Charlotte UDO, Low for unincorporated.
- **Blocking issue**: `none` — both should ingest cleanly. Just need direct URLs; Hub search is too noisy.
- **Recommended action**: ingest Charlotte UDO as a county-level zoning source. Confirm UDO covers the county fully (it covers Charlotte + 6 surrounding towns: Cornelius, Davidson, Huntersville, Matthews, Mint Hill, Pineville). Use municipality_name for the towns.

---

## 4. Wake County, NC

- **Parcel candidate**: `https://services.wakegov.com/arcgis/rest/services/Parcels/Parcels/MapServer` (Wake County's known endpoint, not in Hub). Raleigh runs a separate portal.
- **Zoning candidate**: Raleigh's UDO at
  `https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer` (Raleigh's portal, not Hub).
- **Confidence**: parcels High, zoning High for Raleigh.
- **Blocking issue**: `municipal-only` for non-Raleigh portions. Cary, Apex, Holly Springs, Fuquay-Varina, Wake Forest, Garner, Knightdale each zone separately. Unincorporated Wake has a county zoning ordinance — county-level layer likely exists.
- **Recommended action**: ingest Wake parcels first. Then layer Raleigh + Cary + Apex as separate per-municipality sources. Phase D-style aggregation.
- **Prior-session note**: also "0 features returned" — likely path/layer issue, not unavailability.

---

## 5. Douglas County, CO

- **Parcel candidate**: `https://services.arcgis.com/seTexOicoRXDvRsJ/arcgis/rest/services/Parcels_Account_Property_Improvements/FeatureServer` (Hub: high-confidence match, Douglas County GA pattern but verify state).
- **Zoning candidate**: `https://services.arcgis.com/8O9UlSTnqjKptoda/arcgis/rest/services/Zoning_Districts/FeatureServer` — _strong direct match in Hub_ (score 20, "Zoning Districts" title, polygon FeatureServer).
- **Confidence**: parcels Medium (verify state owner is Douglas CO not Douglas GA/NE), zoning High.
- **Blocking issue**: `none` if state-of-owner matches. Castle Rock, Parker, Lone Tree zone separately; the county-published layer should still cover unincorporated.
- **Recommended action**: probe zoning URL service metadata for state/county fields; if Colorado, ingest immediately. This is the highest-confidence Phase 5/6 jurisdiction.

---

## 6. Arapahoe County, CO

- **Parcel candidate**: Arapahoe shares the Denver-region GIS pattern. Likely:
  `https://gis.arapahoegov.com/arcgis/rest/services/Public/Parcels/MapServer`.
- **Zoning candidate**: Hub returns generic Zoning Map 2a and unrelated services. County-published layer would be at the gov portal.
- **Confidence**: Medium.
- **Blocking issue**: `municipal-only` for Aurora (large portion of Aurora is in Arapahoe). Aurora's GIS is at `arcgis.auroragov.org`. Centennial, Englewood, Sheridan, Cherry Hills Village, Greenwood Village, Littleton each zone separately.
- **Recommended action**: probe Arapahoe gov portal directly. Ingest unincorporated + use NJ-loop for Aurora + Centennial as the high-value subset.

---

## 7. Maricopa County, AZ

- **Parcel candidate**: `https://services1.arcgis.com/41tKDgFmDOmw48Ax/arcgis/rest/services/Maricopa_Tax_Parcels/FeatureServer` (Maricopa Assessor's published service — known endpoint).
- **Zoning candidate**: Maricopa County only zones unincorporated areas; each of the 25+ cities (Phoenix, Mesa, Chandler, Scottsdale, Glendale, Gilbert, Tempe, Peoria, Surprise, Goodyear, Avondale, Buckeye, etc.) zones independently. County unincorporated zoning at
  `https://services1.arcgis.com/41tKDgFmDOmw48Ax/arcgis/rest/services/PlanningandDevelopment/Zoning/FeatureServer`.
- **Confidence**: parcels High, zoning Medium for unincorporated, Low for cities.
- **Blocking issue**: `municipal-only` — Phoenix's 1.6M residents are 100% city-zoned, not county.
- **Recommended action**: ingest county parcels (covers all ~1.7M parcels). Layer county unincorporated zoning. Then NJ-loop on the top 5 cities by population (Phoenix, Mesa, Chandler, Scottsdale, Glendale) — covers ~85% of zoned land.
- **Prior-session note**: this is the highest-leverage Phase 5/6 jurisdiction by parcel count.

---

## 8. King County, WA

- **Parcel candidate**: `https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer`. Hub returns Renton-only and noise.
- **Zoning candidate**: King County only zones unincorporated areas; Seattle zones independently. County layer at
  `https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Zoning/MapServer`.
- **Confidence**: parcels High, zoning Medium (unincorporated only).
- **Blocking issue**: `municipal-only` — Seattle, Bellevue, Kirkland, Redmond, Renton, Kent, Federal Way, Auburn, Sammamish, Issaquah all zone separately. ~40 cities total.
- **Recommended action**: ingest county parcels + county unincorporated zoning. NJ-loop on Seattle + Bellevue + Redmond.

---

## 9. Multnomah County, OR

- **Parcel candidate**: RLIS (Regional Land Information System) via Metro publishes the canonical Portland-area data:
  `https://gis.oregonmetro.gov/arcgis/rest/services/RLIS/Taxlots/MapServer`. Hub doesn't surface it.
- **Zoning candidate**: Portland (BPS) publishes:
  `https://www.portland.gov/sites/default/files/zoning.geojson` (also available as ArcGIS service).
- **Confidence**: parcels High (Metro RLIS is best-in-class regional GIS), zoning High for Portland.
- **Blocking issue**: `municipal-only` for Gresham, Troutdale, Fairview, Wood Village. County-level zoning for unincorporated exists but small.
- **Recommended action**: ingest Metro RLIS parcels (covers Multnomah + Washington + Clackamas — three Phase 5/6 jurisdictions worth in one source!). Layer Portland zoning. RLIS is the single highest-leverage source in the entire Phase 5/6 set.

---

## 10. Hennepin County, MN

- **Parcel candidate**: `https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcel_Points/FeatureServer` — Metropolitan Council 7-county service (Hub: confirmed). Hennepin-specific is at `gis.hennepin.us`.
- **Zoning candidate**: Minneapolis (Hennepin's largest city) publishes its zoning at
  `https://opendata.minneapolismn.gov/datasets/zoning-districts/`. Suburbs zone separately.
- **Confidence**: parcels High (Met Council service is well-known), zoning High for Minneapolis only.
- **Blocking issue**: `municipal-only` — Hennepin has 45 municipalities. Minneapolis + Bloomington + Plymouth + Brooklyn Park + Eden Prairie + Minnetonka cover ~50% of parcels.
- **Recommended action**: ingest Met Council parcels. Layer Minneapolis zoning. NJ-loop the 6 largest suburbs.

---

## 11. Oakland County, MI

- **Parcel candidate**: Oakland publishes a tax-parcels series via `services1.arcgis.com/jwbgoAzqzCbiJmg4`:
  `https://services1.arcgis.com/jwbgoAzqzCbiJmg4/arcgis/rest/services/Tax_Parcels_2020_to_2029/FeatureServer` (Hub: confirmed, score 20).
- **Zoning candidate**: Hub surfaces `Oakland_Proposed_Zoning_WFL1` (`https://services1.arcgis.com/YZCmUqbcsUpOKfj7/arcgis/rest/services/Oakland_Proposed_Zoning_WFL1/FeatureServer`) — uncertain whether this is _proposed_ or _current_. Also `Zoning_Group_Layers_Eff20241217__Ord13823` (`https://services.arcgis.com/9tC74aDHuml0x5Yz/arcgis/rest/services/Zoning_Group_Layers_Eff20241217__Ord13823/FeatureServer`) — promising but likely Oakland CA, not MI.
- **Confidence**: parcels High, zoning Low (URL ambiguity — needs probe to confirm Michigan ownership).
- **Blocking issue**: `municipal-only` likely — Michigan counties typically don't have countywide zoning; townships and cities each zone.
- **Recommended action**: ingest parcels. Probe Oakland_Proposed_Zoning_WFL1 layer metadata for state/county. If MI, ingest as countywide reference layer. Otherwise NJ-loop on Troy, Rochester Hills, Farmington Hills, Southfield, Novi.

---

## 12. Allegheny County, PA

- **Parcel candidate**: Pittsburgh/Allegheny GIS at `https://gis.alleghenycounty.us/arcgis/rest/services/property/Allegheny_County_Parcel_Polygons/MapServer` — known endpoint, not in Hub.
- **Zoning candidate**: Pittsburgh publishes its zoning at
  `https://services1.arcgis.com/YZCmUqbcsUpOKfj7/arcgis/rest/services/Zoning_Districts/FeatureServer` (City of Pittsburgh org).
- **Confidence**: parcels High, zoning High for Pittsburgh, Low for the 130 other municipalities.
- **Blocking issue**: `municipal-only` — Allegheny has 130 municipalities, more than Bergen NJ (70). Pittsburgh covers ~25% of population; the remaining ~75% is split across the 130 munis.
- **Recommended action**: ingest county parcels + Pittsburgh zoning first. NJ-loop on the 10 largest non-Pittsburgh munis: Penn Hills, Bethel Park, Monroeville, Plum, McCandless, West Mifflin, Mt. Lebanon, Moon, North Allegheny, Robinson.

---

## 13. Salt Lake County, UT

- **Parcel candidate**: Salt Lake County Assessor at
  `https://slcogis.slco.org/arcgis/rest/services/AssessorParcels/MapServer`. Hub returns only "Salt Lake Utah County Estimates" and noise — useless.
- **Zoning candidate**: same pattern. UT statewide AGRC (Utah Automated Geographic Reference Center) publishes a statewide zoning aggregation at
  `https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/UtahZoning/FeatureServer` (statewide; filter to Salt Lake County).
- **Confidence**: parcels Medium (need to verify portal), zoning Medium (statewide AGRC quality varies).
- **Blocking issue**: `municipal-only` for SLC, West Valley City, West Jordan, Sandy, Murray, Taylorsville. County zones unincorporated.
- **Recommended action**: try AGRC statewide first (it's the largest single source for UT). If it's incomplete, fall back to per-city.

---

## 14. Contra Costa County, CA

- **Parcel candidate**: county publishes at
  `https://gis.cccounty.us/arcgis/rest/services/CCMAP/ParcelsWS/MapServer`. Hub: `Contra_Costa_2025_Roll_Year` (`https://services7.arcgis.com/iwxhJVOFEKDxO7gk/arcgis/rest/services/Contra_Costa_2025_Roll_Year/FeatureServer`) — Assessor's roll-year service, useful for owner/value but may not have geometry.
- **Zoning candidate**: `Contra_Costa_County_Planning_Layers` (`https://services.arcgis.com/jDGuO8tYggdCCnUJ/arcgis/rest/services/ContraCostaCountyPlanningLayers/FeatureServer`) — likely contains zoning as one of multiple layers.
- **Confidence**: parcels High, zoning Medium (need to inspect layer list).
- **Blocking issue**: `municipal-only` for the 19 incorporated cities (Concord, Richmond, Antioch, Walnut Creek, San Ramon, Pittsburg, etc.). Unincorporated is ~12% of population.
- **Recommended action**: probe Planning Layers FeatureServer for zoning sublayer. Ingest parcels first. NJ-loop on Concord + Walnut Creek + San Ramon as the high-leverage cities.

---

## 15. Miami-Dade County, FL

- **Parcel candidate**: county publishes at
  `https://gisweb.miamidade.gov/arcgis/rest/services/Property/PropertyAppraiserMaps/MapServer` (Property Appraiser).
- **Zoning candidate**: `Miami_Dade_County_Zoning_WFL1` (`https://services.arcgis.com/LBbVDC0hKPAnLRpO/arcgis/rest/services/Miami_Dade_County_Zoning_WFL1/FeatureServer`) — _direct match in Hub, polygon FeatureServer_. There's also `Miami-Dade_County_Active_Zoning_Hearing_Subscription` which is hearing-tracking, NOT zoning polygons — _do not pick this one_.
- **Confidence**: parcels High, zoning High (direct candidate exists).
- **Blocking issue**: `municipal-only` for Miami, Miami Beach, Coral Gables, Hialeah, Doral, Aventura, Homestead, Kendall, etc. County zones unincorporated (largest portion of land area but smaller % of population).
- **Recommended action**: ingest county parcels + Miami_Dade_County_Zoning_WFL1. NJ-loop on Miami + Miami Beach + Coral Gables + Hialeah as the top-4 cities.

---

## Roll-up: ingestion order

Ranked by **expected-overlay yield per ingest day**:

| Rank | Jurisdiction | Why first | Effort |
|---|---|---|---|
| 1 | Multnomah OR | Metro RLIS gives 3 counties' parcels in one source | Low |
| 2 | Mecklenburg NC | Charlotte UDO is well-published, covers most of county | Low |
| 3 | Douglas CO | direct Hub match, single-source county zoning | Low |
| 4 | Miami-Dade FL | direct Hub match for county zoning | Medium |
| 5 | Maricopa AZ | largest parcel count in Phase 5/6 (~1.7M) | Medium |
| 6 | King WA | high-quality county portal, just needs direct URL | Medium |
| 7 | Hennepin MN | Met Council parcels = best-in-class regional source | Medium |
| 8 | Wake NC | needs Raleigh + per-city NJ-loop | Medium |
| 9 | Allegheny PA | needs Pittsburgh + 10-muni NJ-loop | Medium |
| 10 | Salt Lake UT | AGRC statewide zoning is unknown quality | High |
| 11 | Williamson TN | likely needs full per-muni discovery | High |
| 12 | Fulton GA | Atlanta-municipal; needs NJ-loop on 14 cities | High |
| 13 | Arapahoe CO | needs Aurora + Centennial + Englewood | High |
| 14 | Contra Costa CA | 19 cities, large NJ-loop scope | High |
| 15 | Oakland MI | URL ambiguity + township-zoning model | High |

**Recommended sprint scope**: ranks 1–4 (4 jurisdictions, ~5 days of work,
expected delta ~2M parcels across 6 metro areas including Portland, Charlotte,
Denver suburbs, and Miami). Saves the long-tail municipal work (ranks 11–15) for
after the platform has the NJ-loop verified at production scale.

---

## Cross-cutting findings

1. **Hub search is too noisy for counties with no direct match.** Top hits routinely
   surfaced adjacent-state or unrelated layers ("Yuba County Parcels" topping
   most queries, "Duplin County NC Parcels" for any TN/NC query, "Black Hawk
   County Zoning" topping any zoning query). The discovery service's confidence
   scoring + name-match bonus is doing real work here — Hub raw scores alone
   would mis-pick almost every time.
2. **All 15 jurisdictions need per-municipality work for full coverage**, but 8 of
   15 have a usable county-level zoning layer that's worth ingesting first for a
   partial-coverage win (Mont PA-style: gets unincorporated, doesn't get cities).
3. **The "county portal not in Hub" pattern is common** for the largest counties
   (Wake, Mecklenburg, Maricopa, Salt Lake, Allegheny, Miami-Dade). Their GIS
   teams publish to their own ArcGIS Server, not Hub. The discovery service
   should be extended to probe `gis.{county}.gov` and `gis.{county}county.us`
   conventional URLs directly.
4. **Regional GIS consortiums are leverage multipliers.** Portland's Metro RLIS
   covers 3 counties; Met Council in Minneapolis covers 7; Atlanta Regional
   Commission covers 11. One source-ingest = many counties' worth of parcels.
5. **County-level zoning is partial.** Even with a clean countywide zoning layer,
   the per-city zoning that overrides county is the dominant coverage in
   suburbanized metros. NJ-loop pattern (per-town discovery + verified-only
   ingest) is the right primitive for ranks 5–15.

## What this doc is NOT

- It is not a final source registry. Each candidate URL needs verification via
  `_discover-zoning` against the actual jurisdiction record once that
  jurisdiction is added to the DB.
- It is not a commitment to ingest order. The ROI ranking above is a strong
  recommendation; product/business may prioritize differently (e.g. specific
  metros for sales targets).
- It is not a substitute for operator review. Every "High" confidence candidate
  here is still a candidate, not a verified source. The `zoning_sources`
  registry with `confidence_label='verified'` is the source of truth at runtime.
