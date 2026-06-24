# Op-5 Oakland MI Phase 7E.1 — county parcel ingest + jurisdiction registration

**Owner:** Lane A
**Date:** 2026-06-19
**Sprint type:** Wave 4 dispatch per Master's 2026-06-19 parallel-wave directive. Second massive-county wave after Maricopa Phase 7B.1 (PR #305 MERGED).
**Verdict:** **DB-LEVEL IN FLIGHT.** Oakland County, MI jurisdiction `1f8dbc98-098a-42d1-a2b8-6dd80b6a658f` registered. Parcel ingest fetching 490,590 features from Tax Parcel Plus FeatureServer at PR commit time. Spatial bbox + wealth-band counts pending fire completion.
**Predecessors:** Diagnostic PR #260 (Oakland acquisition spec) · Phase 7A.1 Hennepin pattern (PR #293).

---

## TL;DR

Oakland County publishes a single-county-portal parcel layer at `gisservices.oakgov.com/.../EnterpriseOpenParcelDataMapService/MapServer/1`. **490,590 features** (about Hennepin-scale). CVTTAXDESCRIPTION case-discipline: UPPERCASE + political-entity prefix (CITY OF BIRMINGHAM, VILLAGE OF FRANKLIN, CHARTER TOWNSHIP OF BLOOMFIELD) — different from MN/WA/CT/AZ patterns. 5 wealth-band targets in orchestrator's 8fe33e5 pre-stage.

## What's in this PR

- `backend/scripts/ingest_oakland_mi_parcels.py` (new) — county parcel ingest + jurisdiction registration (Hennepin template adapted)
- `docs/OP5_OAKLAND_MI_PHASE7E1.md` (this file)

## Source — Oakland County Access Oakland

```
https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/
EnterpriseOpenParcelDataMapService/MapServer/1
```

- Publisher: **Oakland County GIS / Access Oakland open-data**
- Layer: `Tax Parcel Plus`
- SR: Web Mercator (wkid=102100); server-side reprojected via `outSR=4326`
- maxRecordCount: 2,000 (paginated)
- Total: **490,590 parcels**
- 24 fields per parcel (KEYPIN, CVTTAXDESCRIPTION, PIN, CLASSCODE, NAME1, SITEADDRESS, SITECITY, ASSESSEDVALUE, etc.)

## Case discipline — UPPERCASE + political-entity prefix

**Critical pattern flag**: Oakland publishes CVTTAXDESCRIPTION as UPPERCASE with full political-entity prefix:
- `CITY OF BIRMINGHAM`
- `CITY OF BLOOMFIELD HILLS`
- `CHARTER TOWNSHIP OF BLOOMFIELD`
- `VILLAGE OF FRANKLIN`
- `VILLAGE OF BEVERLY HILLS`

Per Master's Wave 4 dispatch: **PRESERVE THIS VERBATIM** — do NOT strip the prefix. This is the MI convention. Phase 7E.2 per-muni registration will use exact-equality `city='CITY OF BIRMINGHAM'` joins.

**Per Diagnostic PR #260**: use CVTTAXDESCRIPTION, not SITECITY. SITECITY uses postal city which over-selects Bloomfield-area parcels (postal city 'BLOOMFIELD HILLS' includes parcels in Bloomfield Township that don't belong to City of Bloomfield Hills).

## Pattern from Hennepin Phase 7A.1 carried forward

- COPY-upsert to `_stage_parcels` temp table + ON CONFLICT MERGE
- 50k BATCH_SIZE, 2k PAGE_SIZE
- Exponential backoff on timeout (5 retries)
- `--start-offset` resume flag (silent-hang recovery — Hennepin + Maricopa precedent)
- Inline `jurisdictions.bbox` UPDATE at fire-end (PR #261 codified)
- Skip prod ROLLBACK preflight at Class A scale (PR #253)
- Bounded raw_attributes (19 keys — assessor + tax + structure subset)

## is_residential heuristic — MI CLASSCODE

```
401-499 = residential                   → True
201-299 = commercial                    → False
301-399 = industrial                    → False
101-199 = agricultural                  → None
others                                  → None
```

## Pre-flight check ✓

```
features fetched : 1,000
geom_skipped     : 0
apn_skipped      : 0
mappable rows    : 1,000
distinct CVTTAXDESCRIPTION in sample: 1 (CITY OF HAZEL PARK 1000)
```

Early offsets alphabetically — CITY OF HAZEL PARK is at front. Wealth munis come later (BIRMINGHAM / BLOOMFIELD / FRANKLIN / BEVERLY HILLS at full-county scan).

## Fire process

Started 2026-06-19T12:43:48Z. Process PID 61172, `nohup ... & disown`. Log `/tmp/oakland_parcels_fire.log`. Estimated wall-clock: 2-4h based on Hennepin's 448k throughput (Hennepin ran clean ~1h end-to-end; Oakland is comparable scale).

If silent hang or rate-limit 502 surfaces (Maricopa precedent): `--start-offset` resume path codified.

## Next dispatch — sequence within Oakland wave

1. **Parcel ingest completes** (~2-4h from PR open time)
2. **Inline bbox UPDATE** fires automatically
3. **Phase 7E.2** per-muni registration via UPDATE jurisdiction_id pattern (Bellevue/Hennepin/Maricopa precedent):
   - City of Birmingham → own jid
   - City of Bloomfield Hills → own jid
   - Charter Township of Bloomfield → own jid
   - Village of Franklin → own jid
   - Village of Beverly Hills → own jid
4. **Phase 7E.3** per-muni zoning ingest:
   - Birmingham + Beverly Hills HIGH Path A (orchestrator's 65-row pre-stage 8fe33e5 — 21 + 12 codes)
   - Bloomfield Hills + Bloomfield Township + Franklin LOW Path B ordinance (orchestrator authors at apply-time)

## Birmingham numeric-zero caveat (per Diagnostic PR #260)

Birmingham city zoning layer uses `0-1` / `0-2` (numeric ZERO) for office codes, NOT the letter `O`. Phase 7E.3 adapter must handle:
- Preserve verbatim in raw_attributes
- Display correctly (don't normalize 0-1 → O-1)

This is a documented quirk for Phase 7E.3 — flagged here for Lane A awareness.

## Hard rules honored

- raw_attributes preserved verbatim (Norfolk gate)
- CVTTAXDESCRIPTION UPPERCASE + political-entity prefix preserved (MI discipline)
- No zoning data written (Phase 7E.3 separate)
- Inline jurisdictions.bbox UPDATE (PR #261 codified)
- Skip ROLLBACK preflight at scale (PR #253)
- `--start-offset` resume flag for silent-hang recovery
- One refresh per phase

## Sibling waves status

- **Maricopa**: PV (PR #310) + 4-muni (PR #313) → 5/5 registered, Scottsdale 7B.3 firing
- **Fairfield**: Stamford (#308 applied) + Greenwich (#311) → 2/5 ops, 3 deferred
- **Oakland MI Wave 4 (this PR)**: parcel ingest in flight (~2-4h)
