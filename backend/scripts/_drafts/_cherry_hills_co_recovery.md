# Cherry Hills Village CO Recovery — DIAGNOSTIC

Date: 2026-06-24
Branch: `adarench/cherry-hills-co-recovery`
Author: Discovery + Coverage Expansion lane
Status: **READ-ONLY DIAGNOSTIC. DO NOT MERGE.**

## Verdict

**HALT — recovery is not viable as a single re-fire.** Two-step path required:

1. **Substrate cleanup (REQUIRED, ~5 min):** Delete the 1,153 mis-ingested Arapahoe County zoning rows from the CHV jurisdiction. Reset `zoning_endpoint` from the county URL to NULL.
2. **Source-acquisition backlog item (~hours to weeks):** Cherry Hills Village has NO live machine-readable Class B zoning source. Town publishes only a PDF official zoning map. Path requires either manual PDF→GeoJSON digitization or direct outreach to the City GIS owner.

Re-fire alone will NOT flip Cherry Hills. The Arapahoe County zoning layer fundamentally does not cover incorporated CHV territory.

## Root cause

The jurisdiction `cea334ed-34b1-4211-a372-6182815733c8` (Cherry Hills Village, CO) was created with `zoning_endpoint = https://services2.arcgis.com/.../AC_WSS_Arapahoe_County_Zoning/FeatureServer/89` — but that layer is **Arapahoe County's zoning**, which covers only **unincorporated** Arapahoe County. Cherry Hills Village is an incorporated home-rule municipality with its own zoning ordinance, NOT included in the county layer.

Hard evidence from live probes:

| Probe | Result |
|---|---|
| County zoning layer total features | 1,236 |
| **County zoning features intersecting CHV bbox** | **0** (with 2 fringe parcels grazing an edge polygon — `R-2`) |
| CHV parcel envelope | `-104.978, 39.624` → `-104.913, 39.653` |
| County zoning envelope inside CHV | only one polygon (R-2) touches the northern boundary |

The ingest pulled 1,153 county zoning polygons and stamped them with the CHV `jurisdiction_id`. The spatial backfill then ran `st_within(st_centroid(parcel.geom), district.geom) AND district.jurisdiction_id = CHV` — which returned 2 hits out of 2,229 parcels (the 2 fringe overlap parcels).

## Live prod state (probed 2026-06-24)

| Field | Value |
|---|---:|
| `parcel_count` | 2,229 |
| `parcel_with_geom_count` | 2,229 |
| `parcel_with_zoning_code_count` | **2** |
| `parcel_with_zone_class_count` | 0 |
| `parcel_distinct_zone_count` | 1 (R-2) |
| `district_count` (muni-health) | **1** (the single fringe-overlap polygon) |
| `district_count` (raw zoning_districts table for this JID) | **1,153** (all upstream county polygons stamped with CHV jid) |
| `parcel_zoning_code_coverage_pct` | **0.09%** (2 / 2,229) |
| `_sources.count` | 0 (no zoning source rows registered against this JID — adapter wrote zoning_districts directly) |
| Band | `broken` |
| Bucket in `/api/admin/coverage` | NEITHER `jurisdictions` NOR `failures` |

Uncovered codes endpoint reports `R-2` as the only "uncovered" code with 2 parcels — which is misleading; the real picture is 2,227 parcels have NO zoning at all (not just an uncovered code mapping).

## Source check — Is the upstream alive?

| Source | Status | Verdict |
|---|---|---|
| Arapahoe County Zoning (current `zoning_endpoint`) | ALIVE (HTTP 200, 1,236 features, 50 distinct codes) | Wrong source — covers unincorporated only, 0 features inside CHV bbox |
| CHV City Official Zoning Map (PDF) | ALIVE — `/DocumentCenter/View/1873/Official-Zoning-Map-PDF` | Not machine-readable |
| `chvgis` (Jan Peciak) ArcGIS items | ALIVE — 5 items under `services3.arcgis.com/NeZAn2ca6Z9Y9II7` | **WIP/TEST — incomplete (only 2 zone polygons)** |
| ArcGIS Online search `"Cherry Hills Village" zoning` | 2 results, neither viable | No public live Class B exists |
| DRCOG (Denver Regional Council of Governments) | ALIVE | 127 items, none are a municipal zoning aggregator |
| Wayback for `cherryhillsvillage.com/gis` | NO snapshots | No historic ArcGIS layer to revive |

### Detail on the `chvgis` WIP item

`https://services3.arcgis.com/NeZAn2ca6Z9Y9II7/arcgis/rest/services/Zone_Test_3_WFL1/FeatureServer`

| Layer | Name | Feature count | Notes |
|---|---|---:|---|
| 0 | Cherry Parcels | 2,419 | Real city parcel layer, healthy |
| 5 | ZoningShapes | **2** | Only 2 polygons exist: `O-1` (Open Space) and `R-2` (1.25 Acre Residential) |
| 6 | CherryParcels_SpatialJoin | 2,419 | Parcels with Zone joined — Zone is mostly NULL because layer 5 is incomplete |

Owner is `chvgis` / Jan Peciak (real ArcGIS identity, CHV GIS staff). Item title literally says "Test." This is a development/staging artifact, NOT a complete municipal zoning layer.

## Recovery paths

### Path A — Substrate cleanup ONLY (REQUIRED before any re-fire)

```sql
-- Delete mis-ingested county zoning from CHV jurisdiction
DELETE FROM zoning_districts
WHERE jurisdiction_id = 'cea334ed-34b1-4211-a372-6182815733c8';
-- expected: 1153 rows deleted

-- Null out the wrong zoning_endpoint so re-fires don't re-pull county data
UPDATE jurisdictions
SET zoning_endpoint = NULL
WHERE id = 'cea334ed-34b1-4211-a372-6182815733c8';

-- Re-run coverage refresh
POST /api/admin/coverage/refresh?jurisdiction_id=cea334ed-34b1-4211-a372-6182815733c8
```

Outcome: CHV drops from `broken` to `no_zoning_districts` / honest `not_loaded` state. Parcels remain (2,229). No false +1 op claimed.

### Path B — Wait for chvgis to finish

`chvgis` (Jan Peciak) is actively building a city zoning layer (`Zone_Test_3_WFL1`). Today it only has 2 polygons. Re-probe in 30-90 days; if ZoningShapes grows to ~15-20 polygons (matching the PDF zoning map's district count), it becomes a real Class B candidate at:

`https://services3.arcgis.com/NeZAn2ca6Z9Y9II7/arcgis/rest/services/Zone_Test_3_WFL1/FeatureServer/5`

Renamed-from-Test version (when production-ready) will likely live in the same org with a non-"Test" name.

### Path C — Direct outreach (fastest if Master willing)

Contact: Jan Peciak (`chvgis` owner) via City of CHV Community Development — `303-783-2721` or general portal at `cherryhillsvillage.com/201/Community-Development`. Ask for either:
- An export of the canonical zoning shapefile/GeoJSON, or
- ETA for the public release of the in-progress `Zone Test 3` layer

This is a public-records request scope item; CHV would normally honor it under CORA.

### Path D — Manual PDF→GeoJSON digitization

`https://www.cherryhillsvillage.com/DocumentCenter/View/1873/Official-Zoning-Map-PDF` is the canonical zoning map. Manual digitization is ~4-8h of analyst work (CHV is small: ~6 sq mi, single-digit residential zone districts). Output would be a static GeoJSON committed to `backend/data/manual_zoning/cherry_hills_village_co.geojson` and ingested via the `_upload-zoning` path.

## Recommendation

**Immediate (Agent 6 or 8, ~5 min):** Execute Path A substrate cleanup. This stops the broken-state bleeding and gives an honest "not_loaded" reading. The +1 op cannot be claimed today regardless.

**Backlog (Lane A coordination, ~1-4 weeks):** Pursue Path C (outreach to Jan Peciak / City) in parallel with Path B (monthly re-probe of `Zone_Test_3_WFL1` for completeness). Reserve Path D as fallback if both Path B and Path C return no signal within 30 days.

**Do NOT re-fire** the current adapter without changing `zoning_endpoint` — it will simply re-pull the same county layer and reproduce the same broken state.

## Endpoints used (Lane A reproducibility)

```bash
PROD="https://capable-serenity-production-0d1a.up.railway.app"
JID="cea334ed-34b1-4211-a372-6182815733c8"

# Jurisdiction metadata (reveals zoning_endpoint pointing to county layer)
curl "$PROD/api/jurisdictions/$JID"

# Muni-health (confirms 2/2229 binds, 1 effective district)
curl "$PROD/api/jurisdictions/$JID/_municipalities-health"

# Explain-backfill (shows the spatial join + 1-row estimate)
curl "$PROD/api/debug/explain-backfill/$JID"

# Zone summary (only R-2, 2 parcels)
curl "$PROD/api/jurisdictions/$JID/parcels/zone-summary"

# Upstream county zoning — count features inside CHV bbox = 0
ZONING="https://services2.arcgis.com/OSbOBWdLkmvu5I9F/arcgis/rest/services/AC_WSS_Arapahoe_County_Zoning/FeatureServer/89"
BBOX="-11686098,4811452,-11678862,4815645"
curl "${ZONING}/query?where=1%3D1&geometry=${BBOX}&geometryType=esriGeometryEnvelope&inSR=102100&spatialRel=esriSpatialRelIntersects&returnCountOnly=true&f=json"

# chvgis WIP layer — confirm only 2 polygons
TEST="https://services3.arcgis.com/NeZAn2ca6Z9Y9II7/arcgis/rest/services/Zone_Test_3_WFL1/FeatureServer/5"
curl "${TEST}/query?where=1%3D1&returnCountOnly=true&f=json"
```

## Expected ops impact

| Action | Ops delta | Reasoning |
|---|---:|---|
| Do nothing | 0 (and broken-state stays in coverage report) | Lane A will keep seeing CHV at 0.09% cov, may waste re-fire cycles |
| Path A (cleanup only) | 0 | Honest accounting; no +1 op |
| Path A + Path C (City delivers export) | +1 (after ingest + refresh) | If outreach succeeds, single-polygon proof |
| Path A + Path B (wait for chvgis completion) | +1 (timeline: 30-90 days speculative) | Depends on Jan Peciak's release timeline |
| Path A + Path D (manual digitization) | +1 (4-8h analyst work) | Cleanest if Lane A wants this slot certain |

## Scope guards honored

- Read-only HTTP probes only. No prod writes, no `_upload-zoning`, no DELETE executed.
- SQL block in Path A is a recommendation for Agent 6/8 (or DB-direct), not executed from this lane.
- No outreach sent.

## Stand-down

Per user budget: HALT-AND-REPORT complete. Re-engagement criteria unchanged plus this new one:
- Lane A executes Path A; substrate cleanup confirmed; CHV re-classified to honest `not_loaded`
- Path B/C/D returns a viable machine-readable Class B source → activate ingest

Until then, CHV remains a +0/+1 polygon depending on outreach success.
