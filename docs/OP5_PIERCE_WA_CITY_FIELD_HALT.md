# Op-5 Pierce WA city-field HALT (Phase 6B.1 Pierce-specific)

**Owner:** Lane A
**Date:** 2026-06-16
**Sprint type:** HALT report — Pierce-specific gap surfaced during Phase 6B.1 verification.
**Verdict:** **Pierce parcels are LOADED in prod (328,832 rows with valid geom + raw_attributes + bbox), but `parcels.city` is uniformly null because the upstream Washington Current Parcels source publishes null `SITUS_CITY_NM` for every Pierce row.** Pierce Phase 6B.2 zoning backfill is blocked until `parcels.city` is populated by an alternate path. Forward fix recommended: spatial join to a WA city boundary layer.
**Predecessors:** PR #259 (King WA parcel ingest pattern) · PR #264 (multi-county bbox-primitive bonus probe). PR #267 (or wherever Master assigns this) is the Pierce-specific halt PR.

**Companion PR**: `docs/OP5_PUGET_SOUND_PHASE6B1.md` summarizes the Kitsap + Snohomish success path that lands alongside this HALT.

---

## Summary

Per Master's Phase 6B.1 dispatch, Lane A:
1. Ingested Pierce parcels from the Washington Current Parcels FeatureServer with filter `COUNTY_NM='53'` — **328,832 / 339,590 = 96.8 % retention** (8,866 collapsed APN duplicates collected in the final batch + minor null-APN tail).
2. Inline `jurisdictions.bbox` UPDATEd `[-122.842, 46.739, -121.447, 47.404]` per PR #261 codified pattern (sanity-checked Puget Sound range).
3. **Verification surfaced the gap**: 0 / 328,832 Pierce parcels have `city` populated. 0 Gig Harbor parcels (the wealth-band target). Compared to Kitsap (85.3 % city populated) and Snohomish (99.5 %), Pierce is anomalously empty.

## Root cause

The Washington State Current Parcels statewide source's `SITUS_CITY_NM` column is **uniformly null for every Pierce parcel** in the source layer itself (not a Lane A adapter bug). Confirmed via:

1. **REST `returnDistinctValues=true`** on `SITUS_CITY_NM where COUNTY_NM='53'`:
   ```
   Pierce distinct SITUS_CITY_NM: 1 unique values: [None]
   ```
2. **10-row random sample from prod** (post-ingest): all 10 had `raw->>'SITUS_CITY_NM' = NULL`.

This is the upstream WaTech feed pipeline — Pierce County either (a) doesn't push situs city to the statewide aggregation, or (b) the WaTech ingest drops Pierce's city column. **Not addressable in our adapter.**

## Alternate-field probe — all dead

The Washington Current Parcels layer has 17 source fields. Probed every reasonable city-locator alternative against the same Pierce 10-row sample:

| Alternate field | Pierce coverage | Verdict |
|------------------|-----------------|---------|
| `SITUS_CITY_NM` | 0 / 10 populated | DEAD — primary, confirmed null statewide for Pierce |
| `SITUS_ZIP_NR` | 0 / 10 populated | DEAD — Pierce ZIPs also null in source |
| `SUB_ADDRESS` | 2 / 10 populated, neither is a city | DEAD — condo/dev names only, no city |
| `SITUS_ADDRESS` | 10 / 10 populated, all street-only | DEAD — no city embedded in string |
| `DATA_LINK` | 10 / 10 populated | Indirect — links to `atip.piercecountywa.gov/app/v2/propertyDetail/<APN>/summary`, which would require 328,832 scrapes; rate-limit risk |
| `N_CTY_ST` / `TAXAREA` / `LEGAL` | not in this layer schema | DEAD — Master's brief mentioned these but Washington Current Parcels doesn't publish them; only Oakland MI's CVT* and Pierce direct have those |

No field-level path forward in this layer.

## Forward-fix recommendation

**Spatial join to a WA city boundaries layer.** Standard PostGIS pattern:

```sql
UPDATE parcels p
SET city = c.name
FROM wa_city_boundaries c
WHERE p.jurisdiction_id = '47ff33c8-…'::uuid
  AND p.geom IS NOT NULL
  AND ST_Within(ST_Centroid(p.geom), c.geom);
```

WA city boundary sources (any of these):
- **Washington Geospatial Open Data Portal** — `City Limits` layer (statewide)
- **WaTech State Geospatial Catalog** — `Cities` or `Incorporated_Places`
- **PSRC** — Puget Sound Regional Council often republishes city limits clean
- **Pierce County direct** — `https://gis.piercecountywa.gov/arcgis/rest/services/` likely has city limits

Spatial join on 328,832 parcels × ~30 Pierce cities (rough est) is a single SQL UPDATE. Probably 1-5 min wall-clock.

**Effort estimate**: ~30-60 min total — find the layer + verify schema + fire the spatial UPDATE + spot-check Gig Harbor count vs expected (~3,000 per US Census). Worth a follow-up dispatch.

**Alternative paths considered + rejected**:
- **DATA_LINK scrape** (328k requests) — rate-limit risk, slow, throwaway HTML parsing
- **Pierce County direct parcel layer** (`https://gis.piercecountywa.gov/.../Parcels/MapServer/0`) — likely has city field, but would re-do the entire ingest with a different source — wasteful given parcels already loaded
- **PSRC RegionalParcels** — per acquisition spec PR #245, "thinner" layer with just parcel number + geom; no city field there either

## What is NOT broken about Pierce

To be clear on the partial state:

| Asset | State | Usable for follow-up? |
|-------|-------|----------------------|
| Pierce jurisdiction row | ✓ registered | yes |
| `jurisdictions.bbox` | ✓ populated inline `[-122.842, 46.739, -121.447, 47.404]` | yes — `missing_bbox` won't fire post-refresh |
| 328,832 Pierce parcels | ✓ loaded with valid geom + 17-field `raw_attributes` | yes |
| `is_residential` | ✓ 273,241 (83.1 %) classified | yes |
| `assessed_value` | ✓ populated from VALUE_LAND + VALUE_BLDG | yes |
| `parcels.city` | **null on all 328,832** | NO — gated for Phase 6B.2 |

Pierce is at "**partial-with-no-city**" — staged behind the city gap. Nothing wasted; spatial join unblocks everything.

## What changed in the repo (Pierce-specific)

- `backend/data/pierce_wa_zoning_directory.json` (new) — Gig Harbor entry pre-staged, but blocked until Pierce city derivation lands
- This sprint doc (`docs/OP5_PIERCE_WA_CITY_FIELD_HALT.md`)

No backend code changes. No prod writes specific to Pierce beyond the parcel ingest itself.

## Halt-and-report discipline (running tally)

This is **Pierce HALT** — the 6th major halt of the campaign:

1. **PR #216** — Phase 2A Montgomery PA: 54 districts cover ~1.2% of county
2. **PR #221** — Phase 2B Fairfield CT: CAMA layer has zero zoning attributes
3. **PR #242** — Task 5 Phase 2 Contra Costa: jurisdiction + parcels not loaded
4. **PR #253** — Phase 5A.2 Pass 2: asyncpg 60-min ceiling (partial recovery)
5. **PR #259** — Phase 6A.1 Bellevue WAZA-vs-city mismatch (resolved via PR #264 authoritative-layer choice)
6. **This HALT** — Pierce city field uniformly null in upstream WA Current Parcels

Same discipline that saved each predecessor. Pierce parcels are NOT broken — they're staged behind a known forward-fix.

## Recommended next dispatch

**TASK E — Pierce city derivation via spatial join** (~30-60 min):

1. Identify a WA city boundary FeatureServer (Washington Geospatial Open Data Portal / WaTech / Pierce direct).
2. Fetch the layer scoped to Pierce County (or filter post-fetch).
3. Build the WA city boundaries into a temp table or query directly via PostGIS.
4. Fire `UPDATE parcels SET city = ... WHERE ST_Within(centroid, boundary)` for Pierce's jurisdiction_id.
5. Verify: Gig Harbor count ≈ 3,000 (per US Census). If reasonable, declare Phase 6B.2 Pierce unblocked.
6. Stop point: PR opened with the city UPDATE + verification — Master reviews.

After Task E: Pierce can join the Phase 6B.2 dispatch cohort.

## Operational state

Operational count unchanged: **20**. Pierce stays `not_loaded` per audit-readiness terms (no zoning_code populated, city blocked). DB-level: parcels are live, just gated from operational by the city gap.
