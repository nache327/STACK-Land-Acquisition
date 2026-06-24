# Hingham MA Per-Muni Probe v2 — DIAGNOSTIC

Date: 2026-06-23
Branch: `adarench/hingham-ma-per-muni-probe-v2`
Author: Discovery + Coverage Expansion lane
Status: **READ-ONLY DIAGNOSTIC. DO NOT MERGE.**

## Verdict

**VIABLE — re-confirms PR #335 spec.** Hingham, MA is a single-polygon Plymouth-MA-58 +1 path. The MAPC Zoning Atlas v0.2 regional aggregator and MassGIS Standardized Assessors L3 parcel layer both re-validated live today against the same endpoints PR #335 documented. No new viable source surfaced; no previously-rejected source has become usable.

Recommended action: hand off to Lane A as a per-muni jurisdiction Op-5 (2-4 day proof) following the King WA path-1 pattern. No further structural probing required for Hingham/Plymouth MA.

## Why this v2 probe was requested

User question: with the Westchester Class B proof primitive + per-muni jurisdiction pattern now battle-tested, is there anything on the Hingham/Plymouth MA list that was rejected in PR #335 (2026-06-23, same day) that deserves a second look — and is any new aggregator now live? This is a re-validation pass against the same five candidate buckets the user enumerated.

PR #335 (`docs/PLYMOUTH_MA_ACQUISITION_SPEC.md`) already supersedes the original PR #222 HALT. This v2 probe confirms PR #335 endpoints are still live and that none of the rejected sources has flipped to viable.

## Live re-validation of PR #335 endpoints (2026-06-23 today)

| Endpoint | HTTP | Result |
|---|---:|---|
| `geo.mapc.org/.../Zoning_Atlas_v01/MapServer/2` (zoning_full) | 200 | Service live |
| `geo.mapc.org/.../Zoning_Atlas_v01/MapServer/0` (overlay_districts) | 200 | Service live |
| `services1.arcgis.com/hGdibHYSPO59RG1h/.../Massachusetts_Property_Tax_Parcels/FeatureServer/0` | 200 | Service live |
| `where=muni='Hingham'` on `zoning_full` | — | **15 features** (matches PR #335 bylaw 1:1) |
| `where=ZONECODE LIKE '131%'` on overlay layer | — | **7 features** (matches PR #335) |
| `where=TOWN_ID=131` on MassGIS parcels | — | **8,894 parcels** (matches PR #335) |
| `where=TOWN_ID=131 AND ZONING IS NOT NULL` | — | **7,475 parcels = 84.0%** (matches PR #335) |
| Hingham bylaw PDF `/376/Zoning-By-laws-PDF` | 200 (5.3 MB) | Live, 2025-04-29 revision (PR #335 cite is current) |

All endpoint counts and field shapes match PR #335 within day-of-day drift. The MAPC service has Wayback snapshots in 2024-05 and 2025-05, indicating multi-year longevity — no signs of imminent deprecation despite the "v0.2 test service" label.

## Probe targets the user enumerated

### 1. Town of Hingham GIS portal — RE-CONFIRMED REJECTED

- Landing: `https://www.hingham-ma.gov/183/GIS-Map` (200 OK).
- Backend viewer: `https://www.mapsonline.net/hinghamma/index.html` (vendor: PeopleGIS / MapsOnline).
- ArcGIS Online item id `7b8a2d7676d343cdb86062801a4018cc` is titled "Town of Hingham, MA GIS Viewer" and owned by `MassGIS`, but the `url` field on that item points right back to the mapsonline.net PeopleGIS viewer — it is a wrapper item, not an alternate FeatureServer/MapServer.
- No public ArcGIS REST endpoint discovered for the town's own zoning layer.
- Adapter path would still require either a screen-scrape of PeopleGIS or a vendor data-access request — out of scope per PR #335.

### 2. Plymouth County GIS — RE-CONFIRMED ABSENT

- Plymouth County (`www.plymouthcounty-ma.gov`) returns connection failure today (HTTP 000). Even when up, the county does not publish a county-wide zoning aggregator; each town hosts independently. Old Colony Planning Council (`www.ocpcrpa.org`, the would-be regional planning analog for southern Plymouth County) is also down today (HTTP 000) and historically does not publish a queryable zoning service.
- The MAPC regional aggregator is the closest analog for Hingham (which is on the northern Plymouth County / South Shore boundary inside MAPC's footprint).
- Plymouth Registry of Deeds is online (`https://www.plymouthdeeds.com/` 302 redirects to portal) but is a deeds search interface, not a zoning publisher.

### 3. MassGIS via Mass.gov direct — RE-CONFIRMED NO STATEWIDE ZONING

- `https://www.mass.gov/info-details/massgis-data-zoning` returns 403 to scripted UA today (Cloudflare bot-protection). PR #335 already documents the substantive blocker: the MassGIS statewide zoning layer is 1999 vintage with no current refresh. That is the same blocker PR #222 hit.
- The separate **MassGIS Standardized Assessors / Property Tax Parcels** layer remains the canonical parcel source (re-validated live above, 8,894 Hingham parcels, 84% Class C `ZONING` field coverage).
- No new MassGIS statewide zoning layer has shipped between PR #335 (this morning) and now.

### 4. Town of Hingham bylaw PDF + ordinance — LIVE, ALREADY CITED IN PR #335

- `https://www.hingham-ma.gov/376/Zoning-By-laws-PDF` redirects (302) to `DocumentCenter/View/2145/Hingham-Zoning-By-law-PDF` and serves 5,341,384 bytes of `application/pdf` (HTTP 200 final).
- Title page revision date: April 29, 2025 (cited correctly in PR #335).
- This is the human-readable bylaw used to corroborate the 15 MAPC `zo_code` values. It is *not* a queryable adapter target.
- The published ordinance does not introduce any new machine-readable zoning source beyond what MAPC publishes.

### 5. Wayback Machine for stale ArcGIS layers — NEGATIVE

- `web.archive.org/web/*/hingham-ma.gov/gis` — no snapshots indexed.
- `services.arcgisonline.com/.../hingham` namespace — no snapshots.
- The MAPC zoning service has captures in 2024-05-20 and 2025-05-30, both 200 OK, indicating the service has been stable for at least 2 years. This *strengthens* the PR #335 confidence in MAPC as a primitive.
- No discoverable stale-but-recently-deprecated town-of-Hingham ArcGIS layer that could be revived from cache.

## Re-confirmed rejected candidates

These were rejected in PR #335 and remain rejected after live re-probe today:

| Candidate | Status | Reason |
|---|---|---|
| `services6.arcgis.com/.../Hingham_UDF_Zones/FeatureServer/0` | RE-REJECTED | Live (HTTP 200). Re-confirmed schema = `OBJECTID, AreaNumber, Zone (1-4), Shape__Area, Shape__Length`. This is the VHB utility/CAD UDF layer, not bylaw zoning. PR #335 already flagged this as the Fountain-Hills-style look-alike. **Hard-code MAPC URL, do not search-and-resolve.** |
| PeopleGIS / MapsOnline town viewer | RE-REJECTED | Wrapper viewer; no underlying queryable REST service. |
| MassGIS statewide Zoning | RE-REJECTED | 1999 vintage, never refreshed. Original PR #222 blocker. |
| Plymouth County county-wide zoning | RE-REJECTED | County does not publish one. OCPC down today. |
| Mercatus / Suffolk Law NZA static zip | RE-NOTED | Behind Cloudflare; useful only as corroboration, not as a live adapter target. |

## Single-polygon +1 path

This is the single-polygon proof shape PR #335 already specified. Re-stating here so the v2 probe is a complete deliverable:

- **Jurisdiction registration:** `Hingham, MA (Plymouth County)`, per-muni jurisdiction (King WA path-1 pattern).
- **Parcel source:** MassGIS Property Tax Parcels FeatureServer layer 0, filter `TOWN_ID=131` (8,894 parcels, SRS EPSG:26986).
- **Zoning source (Class B, source-of-record):** MAPC Zoning Atlas v0.2 `zoning_full` (MapServer layer 2), filter `muni='Hingham'` (15 base districts + 7 overlays, SRS EPSG:3857, vintage hard-coded 2020-08-03).
- **Class C diagnostic only:** MassGIS parcel `ZONING` field (84% non-null; flag legacy `R1`/`R3`/`XX`/`00`/`IA`/`IB` rows as low-confidence; use only for agreement-rate QA).
- **Bylaw directory:** `backend/data/plymouth_ma_zoning_directory.json` mapping 15 `zo_code` -> Hingham Zoning By-Law section URLs (bylaw PDF: `https://www.hingham-ma.gov/376/Zoning-By-laws-PDF`).
- **Effort:** 2-4 days for Hingham proof; same MAPC adapter unlocks Hull, Cohasset, Marshfield, Hanover, Duxbury, Norwell at ~1-2 days each.

## v2 vs PR #335 — net new findings

| Topic | v2 finding |
|---|---|
| MAPC service longevity | NEW: Wayback shows MAPC service stable at HTTP 200 in 2024-05 and 2025-05. Strengthens primitive confidence vs PR #335 "v0.2 test service" caveat. |
| Town of Hingham ArcGIS item under MassGIS owner | NEW: ArcGIS Online surfaces an item titled "Town of Hingham, MA GIS Viewer" with `owner=MassGIS`, but the `url` field redirects back to PeopleGIS MapsOnline. Not a new endpoint. |
| Old Colony Planning Council | NEW NEGATIVE: OCPC (the southern Plymouth County regional planner analog to MAPC) is down today and historically does not publish queryable zoning. Not a substitute path. |
| Plymouth Registry of Deeds | NEW NEGATIVE: Online, but deeds-only, not a zoning source. |
| Wayback for stale town ArcGIS | NEW NEGATIVE: No prior town-of-Hingham ArcGIS layer captured. No revival path. |

## Stand-down

Per user budget: **HALT-AND-REPORT**. No further structural probes for Hingham or Plymouth MA absent new signal. Lane A may proceed with PR #335's per-muni Op-5 plan whenever scheduled.

Re-engagement criteria for this geography:
- MAPC service starts returning non-200 in routine checks (then fall back to Mercatus NZA static zip).
- MassGIS publishes a new statewide zoning layer (would unlock western Mass and Cape Cod simultaneously).
- A new South Shore regional planner publishes a queryable zoning service (would extend coverage past MAPC's 101-muni footprint).

## Endpoints inventory (for Lane A handoff)

```
ZONING (Class B, source of record):
  https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/2
    filter: muni='Hingham'
    fields: zo_code, zo_name, zo_usety, zo_usede, mulfam2,
            mnls_eff, lapdu, mxht_eff, mxdu_eff, dupac_eff, far_eff
    SRS: EPSG:3857
    vintage: 2020-08-03 (service-level; per-row spatialrec is NULL)

OVERLAYS:
  https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/0
    filter: ZONECODE LIKE '131%'
    fields: ZONECODE, Overlay_Ty
    SRS: EPSG:3857

PARCELS (canonical):
  https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0
    filter: TOWN_ID=131
    fields: MAP_PAR_ID, LOC_ID, PROP_ID, SITE_ADDR, CITY, ZIP,
            OWNER1, OWN_ADDR, USE_CODE, LOT_SIZE, TOTAL_VAL,
            BLDG_VAL, LAND_VAL, ZONING (Class C diagnostic), FY,
            LAST_EDIT, YEAR_BUILT
    SRS: EPSG:26986

BYLAW (human-readable, citation only):
  https://www.hingham-ma.gov/376/Zoning-By-laws-PDF
  -> https://www.hingham-ma.gov/DocumentCenter/View/2145/Hingham-Zoning-By-law-PDF
  revision: 2025-04-29
```

## Scope guards honored

- Read-only HTTP probes only. No writes to any external system.
- No new jurisdictions registered, no DB rows touched, no scripts created beyond this draft markdown.
- No follow-on Hull/Cohasset/Marshfield/Hanover/Duxbury/Norwell probes (deferred to Lane A per PR #335).
- All cited endpoints already documented in PR #335; v2 adds only longevity / re-rejection signal.
