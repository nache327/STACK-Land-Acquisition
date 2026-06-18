# Op-5 Maricopa AZ Phase 7B.1 — county parcel ingest + jurisdiction registration

**Owner:** Lane A
**Date:** 2026-06-18
**Sprint type:** Wave 2 dispatch after Hennepin MN wave (Edina ✓, Plymouth ✓, Eden Prairie ✓, Minnetonka in flight, Wayzata deferred). Maricopa Phase 7B.1 fired in parallel per Master's "Maricopa is independent — fire NOW" directive.
**Verdict:** **DB-LEVEL IN FLIGHT.** Maricopa County, AZ jurisdiction `eb8a2fc8-c0a6-4155-a4d3-d49bf46d44a6` registered. Parcel ingest fetching 1,742,671 features from Parcel_Data_View FeatureServer at PR commit time. Spatial bbox + wealth-band counts pending fire completion.
**Predecessors:** PR #232 Diagnostic (Maricopa acquisition spec) · PR #262 Diagnostic (Maricopa citation directory pre-stage) · Phase 7A.1 Hennepin pattern (PR #293, 448k parcels).

---

## TL;DR

Maricopa County publishes a single-county-portal parcel layer at `services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/Parcel_Data_View/FeatureServer/0`. 1,742,671 features (~4× Hennepin's 448k). UPPERCASE PropertyCity preserved per Master's AZ case discipline (different from MN/WA/CT title-case). 5 wealth-band targets in pre-stage: Scottsdale 150,207 + Paradise Valley 10,071 + Cave Creek + Fountain Hills + Carefree.

## What's in this PR

- `backend/scripts/ingest_maricopa_az_parcels.py` (new) — county parcel ingest + jurisdiction registration, models on Hennepin Phase 7A.1
- `backend/scripts/ingest_maricopa_az_city_limits.py` (new) — Scottsdale prefilter via Maricopa County Reference/ParcelCityCounty/MapServer/1 (Pierce Task E pattern from PR #285)
- `backend/data/maricopa_az_zoning_directory.json` (new) — 5-muni directory for Phase 7B.3 (Scottsdale Path A + Paradise Valley Path A + Cave Creek/Fountain Hills/Carefree ordinance-only Path B)
- `docs/OP5_MARICOPA_AZ_PHASE7B1.md` (this file)

## Source — Maricopa County Assessor / GIS

```
https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/
Parcel_Data_View/FeatureServer/0
```

- Publisher: **Maricopa County GIS / Assessor**
- Layer: `ASR_Parcels` (per Diagnostic PR #232)
- SR: Arizona Central State Plane (wkid=2868); server-side reprojected via `outSR=4326`
- Geom: esriGeometryPolygon
- maxRecordCount: 2,000 (paginated)
- Total: 1,742,671 parcels (re-validated 2026-06-18 vs PR #232's 2026-06-11 probe)
- Field schema: 95+ fields per parcel (APN, PropertyCity, PropertyFullStreetAddress, OwnerName, LandLegalClassCode, FullCashValue, ImprovementFullCashValue, LotSize_Acre, …)

## Case discipline — UPPERCASE preserved

**Critical pattern flag**: Maricopa publishes PropertyCity in UPPERCASE (`SCOTTSDALE`, `PARADISE VALLEY`, `CAVE CREEK`, `FOUNTAIN HILLS`, `CAREFREE`).

Per Master's Wave 2 dispatch: **PRESERVE UPPERCASE** — do NOT title-case. This is the AZ convention (different from MN's space-padded ALL-CAPS that gets `.title()`'d, different from WA's mixed-case SITUS_CITY_NM, different from CT's full title-case). Codified in `_map_row` — `city = _trim(props.get("PropertyCity"))` without any case transform.

Phase 7B.2 per-muni registration will use exact-equality `city = 'SCOTTSDALE'` joins. Same UPPERCASE pattern expected to extend to all AZ counties (Pima/Pinal future waves).

## Scottsdale prefilter gate (PR #232 risk register)

Diagnostic PR #232 flagged that `PropertyCity='SCOTTSDALE'` parcel bbox FAILS the 50% Class A primitive against Scottsdale's city zoning layer:
- Scottsdale zoning bbox: `[-111.961, 33.448, -111.756, 33.900]`
- Raw PropertyCity='SCOTTSDALE' parcel bbox: `[-111.995, 33.376, -111.467, 33.965]`
- Rectangular overlap ~30% (postal-city noise extends well beyond actual limits)

`ingest_maricopa_az_city_limits.py` resolves this with the Pierce Task E (PR #285) pattern:
- Source: Maricopa County GIS `Reference/ParcelCityCounty/MapServer/1`
- 646 dissolved-by-CityName polygons (authoritative annexation ordinance source)
- All 5 target munis present as distinct polygons
- Spatial join: `UPDATE parcels SET city = city_polygon.CityName WHERE ST_Within(ST_Centroid(parcel), city_polygon.geom)`

This rewrites `parcels.city` from postal-city values to actual-city-limit values, restoring the 50% Class A primitive for Scottsdale. Paradise Valley, Cave Creek, Fountain Hills, Carefree expected to pass without prefilter, but uniformly rewritten for consistency.

## Pattern from Hennepin Phase 7A.1 carried forward

- COPY-upsert to `_stage_parcels` temp table + ON CONFLICT MERGE (matches `app/services/ingestion.py:_STAGE_COLUMNS` exactly)
- 50k-feature BATCH_SIZE; 2k PAGE_SIZE
- Exponential backoff on `httpx.ReadTimeout` / `ConnectTimeout` / `RemoteProtocolError` (5 retries, 1s→16s)
- `--start-offset` flag for resume after silent hang
- Inline `jurisdictions.bbox` UPDATE at fire-end (PR #261 codified)
- Skip prod ROLLBACK preflight at Class A scale (PR #253)
- Bounded raw_attributes passthrough (24 keys — assessor + tax + use code subset, vs 95+ field firehose)

## is_residential heuristic — AZ Legal Class Code

```
3 = Owner-occupied residential          → True
4 = Non-owner-occupied rental res       → True
1 = Commercial / Industrial             → False
5 = Railroad / Mines / Utilities        → False
2 = Vacant / Agricultural               → None  (uncertain)
6 = Historic / Religious                → None
```

Reference: https://azdor.gov/property/property-tax

Maricopa publishes legal class codes with decimal subclasses (`1.1`, `1.3`, `3.5`, `4.2`, …). Heuristic uses first character — correctly classifies all subclasses.

## Pre-flight check ✓

```
features fetched : 1,000 (early offsets — sorted by OBJECTID, alphabetical-ish)
geom_skipped     : 0
apn_skipped      : 0
mappable rows    : 1,000
raw_attributes avg/min/max: 22.4 / 8 / 23 keys
distinct PropertyCity in sample: 6 (AVONDALE 918, TOLLESON 53, SURPRISE 24, …)
```

Wealth-band cities not in first 1k (alphabetical sort puts them later — SCOTTSDALE/PARADISE VALLEY/CAVE CREEK/FOUNTAIN HILLS/CAREFREE come after AVONDALE/TOLLESON/SURPRISE). Full-county scan will surface them.

Sample row: `apn='10101001C', city='AVONDALE', owner_name='EL PASO NATURAL GAS COMPANY', land_use_code='1.3', acres=0.174, has_structure=False, assessed_value=89,900, is_residential=False, raw=<17 keys>`

## Fire process

Started 2026-06-18T17:43:39Z. Process PID 22209, foreground exit deferred via `nohup ... & disown`. Log at `/tmp/maricopa_parcels_fire.log`. Estimated wall-clock: 4-8h based on Hennepin's 448k throughput (3.9× scaling on Maricopa's 1.74M).

If silent hang surfaces (Hennepin precedent at offset 98k): use `--start-offset` to resume.

## Next dispatch — sequence within Maricopa wave

1. **Parcel ingest completes** (~4-8h from PR open time)
2. **Inline bbox UPDATE** fires automatically
3. **City limits prefilter** (`ingest_maricopa_az_city_limits.py fire --maricopa-jid eb8a2fc8…`)
4. **Phase 7B.2** per-muni registration via UPDATE jurisdiction_id pattern (Bellevue/Hennepin Phase 7A.2 precedent):
   - Scottsdale → own jid (gated on city-limits prefilter)
   - Paradise Valley → own jid
   - Cave Creek → own jid
   - Fountain Hills → own jid
   - Carefree → own jid
5. **Phase 7B.3** per-muni zoning ingest:
   - Scottsdale: ArcGIS direct (`maps.scottsdaleaz.gov/.../MapServer/24`, `full_zoning` field, 249-row orchestrator pre-stage)
   - Paradise Valley: ArcGIS direct (`gis.paradisevalleyaz.gov/.../MapServer/7`, `ZONECLASS` field)
   - Cave Creek + Fountain Hills + Carefree: ordinance-only Path B (no GIS publisher; rely on orchestrator's matrix-only flip)

PR description will be amended with parcel count + bbox once fire completes.

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate)
- PropertyCity UPPERCASE preserved (AZ discipline)
- No zoning data written (Phase 7B.3 separate)
- Inline jurisdictions.bbox UPDATE (PR #261 codified)
- Skip ROLLBACK preflight at scale (PR #253)
- Halt-and-report on silent hang (`--start-offset` resume path)
- One refresh per phase
