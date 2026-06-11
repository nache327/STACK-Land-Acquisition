# Op-5 MassGIS / MA zoning-district ingest sprint — HALTED at source gate

**Owner:** Lane D  
**Date:** 2026-06-11  
**Sprint type:** Phase 2B MassGIS zoning acquisition + Class A spatial backfill  
**Verdict:** **HALT — no canonical MassGIS statewide municipal zoning FeatureServer found; MAPC fallback coverage is incomplete. No prod writes performed.**

---

## Headline

The sprint did **not** ingest zoning districts or run
`backfill_parcel_zoning_from_districts`.

The expected source family in the dispatch,
`services.massgis.digital.mass.gov/.../FeatureServer`, did not resolve
from this workspace. MassGIS ArcGIS Online search for `owner:MassGIS`
and `zoning` returned environmental / coastal / flood / evacuation
zoning services and a National Zoning Atlas app, but **no authoritative
statewide municipal base-zoning FeatureServer** suitable for county-wide
parcel binding.

The only broad district-polygon service found was MAPC's regional
Zoning Atlas:

- App: `https://zoningatlas.mapc.org/`
- Report: `https://zoningatlas.mapc.org/reports/1/`
- ArcGIS service: `https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer`
- Base zoning layer: `https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/2`

That layer is **regional and per-town**, not county-wide or statewide.
It contains 1,775 base-zoning polygons across 101 MAPC-region
municipalities, with `zo_code`, `muni`, and `zo_name` fields that would
map cleanly into `ingest_zoning_districts`. Its service metadata says it
is a test service based on the 2020 MAPC Zoning Atlas release:

> "A test service with feature access for the Zoning Atlas, with the
> full attribute table included with the base zoning polygons. Based on
> the 8/3/20 version of the data."

The hard rule for this dispatch was: if MassGIS coverage is incomplete
for any MA county, document and stop; do not bind partials via
`nearest_within_meters`. The MAPC layer fails that gate for all three
target counties:

| County | MAPC town coverage | Missing examples | Gate |
|---|---:|---|---|
| Norfolk MA | 26 / 28 towns | Avon, Plainville | **FAIL — incomplete county source** |
| Plymouth MA | 9 / 27 towns | Plymouth, Brockton, Wareham, Kingston, Carver, etc. | **FAIL — incomplete county source** |
| Middlesex MA | 40 / 54 towns | Lowell, Chelmsford, Billerica, Westford, Tewksbury, etc. | **FAIL — incomplete county source** |

Because the source gate failed, the strengthened Class A write path did
not proceed to district ingest, spatial backfill, or audit refresh.

---

## Source discovery

### Expected MassGIS service

Command probe:

```text
curl https://services.massgis.digital.mass.gov/arcgis/rest/services?f=pjson
```

Result:

```text
curl: (6) Could not resolve host: services.massgis.digital.mass.gov
```

MassGIS ArcGIS Online search:

```text
https://www.arcgis.com/sharing/rest/search?q=owner:MassGIS%20%22zoning%22&f=json&num=20
```

Returned zoning-tagged MassGIS services such as:

- `MassDEP Approved Zone I`
- `Surface Water Supply Protection Areas (ZONE A, B, C)`
- `MassDEP Wellhead Protection Areas Zone II IWPA`
- `Massachusetts Coastal Zone`
- `FEMA Q3 Flood Zones`
- `Massachusetts Hurricane Evacuation Zones 2017`
- `National Zoning Atlas` web mapping application

None are county/municipal base-zoning district polygons suitable for
parcel `zoning_code` backfill.

### Candidate fallback: MAPC Zoning Atlas

Layer:

```text
https://geo.mapc.org/server/rest/services/gisdata/Zoning_Atlas_v01/MapServer/2
```

Useful metadata:

| Field | Value |
|---|---|
| Layer name | `zoning_full` |
| Geometry | `esriGeometryPolygon` |
| Feature count | 1,775 |
| Max record count | 2,000 |
| Code field | `zo_code` |
| Municipality field | `muni` |
| Name field | `zo_name` |
| Source shape | Regional per-town mosaic, not statewide |

Existing mapper compatibility:

- `backend/app/services/zoning_ingestion.py` lowercases candidate fields
  in `_first`, so `zo_code` matches the existing `ZONE_CODE` candidate.
- `zo_name` matches the existing `ZONE_NAME` candidate.
- The service could be ingested technically, but only after Master
  approves a municipality-scoped partial-source strategy. It is not
  safe as a county-wide replace source.

---

## Before-state audit snapshot

Captured 2026-06-11 from prod:

```text
GET https://capable-serenity-production-0d1a.up.railway.app/api/jurisdictions
GET https://capable-serenity-production-0d1a.up.railway.app/api/admin/coverage
```

| County | Registered? | Jurisdiction ID | Parcels | zoning_code pct | zoning_district_count | matrix_zone_count | readiness | blocking_gaps |
|---|---|---|---:|---:|---:|---:|---|---|
| Norfolk County, MA | yes | `6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5` | 206,365 | 74.9% | 0 | 312 | partial | `no_zoning_polygons` |
| Plymouth County, MA | no | n/a | n/a | n/a | n/a | n/a | n/a | no jurisdiction / no coverage row |
| Middlesex County, MA | yes | `18a11c2a-4d7d-4725-a643-e40ea2a4e171` | 423,634 | 92.3% | 0 | 633 | partial | `high_unclear_self_storage_share` |

---

## County-by-county gate result

### Norfolk County, MA

**Verdict:** **HALT — source coverage incomplete; no ingest.**

Norfolk is the target this sprint was meant to unlock: it already has
74.9% parcel `zoning_code` coverage and needs the polygon gate resolved.
The MAPC layer includes the major Norfolk target towns that matter for
the 57-list wealth pockets, including Brookline, Wellesley, Needham,
Milton, Dedham, Dover, Westwood, and Weston-adjacent suburbs.

However, it is not a complete Norfolk County source. Avon and Plainville
are missing from the MAPC municipality set. A county-level
`replace=True` ingest would therefore load a known-partial source under
the Norfolk jurisdiction and create the same false-positive risk as the
Montgomery PA partial-source halt.

**No pre-flight backfill was fired.** The formal strengthened Class A
pre-flight (`district bbox >= 50% of parcel bbox` and 1,000-parcel
`ST_Within >= 50%`) is only meaningful after a candidate district source
passes the participation/provenance gate. This one did not.

### Plymouth County, MA

**Verdict:** **HALT — jurisdiction not registered; source coverage
incomplete.**

Plymouth County is not present in `/api/jurisdictions` and has no
`/api/admin/coverage` row. Even if it were registered, the MAPC layer
covers only 9 of 27 Plymouth County municipalities:

```text
Duxbury, Hanover, Hingham, Hull, Marshfield, Norwell, Pembroke,
Rockland, Scituate
```

Missing towns include Plymouth, Brockton, Wareham, Kingston, Carver,
Bridgewater, East Bridgewater, West Bridgewater, Hanson, Halifax,
Lakeville, Middleborough, and Whitman. That is far below a safe
county-wide source.

The correct path remains parcel-source ingestion first from MassGIS
Property Tax Parcels, then municipality-scoped zoning source discovery
for the 57-list towns.

### Middlesex County, MA

**Verdict:** **HALT — source coverage incomplete; no top-up ingest.**

Middlesex is already at 92.3% parcel `zoning_code` coverage and does not
need a county-wide zoning polygon backfill to clear the 70% parcel-source
gate. It has zero `zoning_districts`, but the current blocker is
`high_unclear_self_storage_share`, not low parcel zoning coverage.

The MAPC layer covers many inner/core Middlesex municipalities
(Cambridge, Newton, Lexington, Concord, Waltham, Arlington, etc.) but is
missing 14 of 54 county municipalities, including Lowell, Chelmsford,
Billerica, Westford, Tewksbury, Dracut, Groton, and Ayer. A county-level
district replace/top-up would be incomplete and would not directly
address the live blocker.

---

## Quality-gate verdicts

| Gate | Threshold / rule | Verdict | Reason |
|---|---|---|---|
| Source participation / completeness | Complete target-county district source or stop | **FAIL / HALT** | Candidate MAPC source is regional; Norfolk 26/28, Plymouth 9/27, Middlesex 40/54 towns covered. |
| Strengthened Class A bbox coverage | District bbox covers >= 50% of parcel bbox before write | **NOT RUN** | Participation/provenance gate failed before district ingest. |
| Strengthened Class A 1,000-parcel dry-run | `ST_Within` match >= 50% before backfill | **NOT RUN** | No district rows were loaded; no backfill attempted. |
| `nearest_*` cap | <= 30% of bound parcels | **PASS BY NON-ACTION** | No `nearest_within_meters` fallback used; zero rows written. |
| Per-muni coverage | Do not hide weak muni coverage inside a county headline | **FAIL / HALT** | Candidate source has known missing towns; no county-wide operational claim is safe. |
| Provenance | Newly ingested rows carry auditable source URL / timestamp | **NOT WRITTEN** | No `zoning_districts` rows inserted. Candidate service provenance is public but not MassGIS-authoritative. |

---

## After-state

No ingest, no backfill, and no audit refresh were fired.

| County | Before | After |
|---|---|---|
| Norfolk County, MA | 206,365 parcels, 74.9% `zoning_code`, 0 districts, partial / `no_zoning_polygons` | **unchanged** |
| Plymouth County, MA | not registered / no coverage row | **unchanged** |
| Middlesex County, MA | 423,634 parcels, 92.3% `zoning_code`, 0 districts, partial / `high_unclear_self_storage_share` | **unchanged** |

The "one audit refresh after all MA counties land" rule did not apply
because no MA county landed.

Preview Supabase branch was not used: the only technically-ingestable
candidate was 1,775 polygons and the sprint halted before any write
path. A preview run would be appropriate if Master authorizes a
municipality-scoped MAPC partial-source ingest later.

---

## Recommended next move

Do **not** treat MAPC Zoning Atlas as a county-wide MassGIS substitute.

Recommended dispatch options:

1. **Norfolk quick-win variant, if Master relaxes the complete-county
   source rule:** ingest MAPC zoning for only MAPC-covered Norfolk towns
   as municipality-scoped sources, with `replace=False` or a protected
   town-scoped replacement path. Then run per-muni backfill and audit
   only those towns. This is a new scoped sprint, not this one.
2. **Plymouth source path:** register/load Plymouth parcels from MassGIS
   Property Tax Parcels first; then discover municipal zoning sources for
   Hingham/Duxbury/Marshfield/Plymouth-town target areas. MAPC alone is
   not enough.
3. **Middlesex path:** prioritize unclear-matrix cleanup rather than
   polygon top-up. The live blocker is matrix classification quality, and
   the county is already above the parcel zoning coverage gate.
4. **Authoritative statewide path:** if Master has a separate MassGIS
   base-zoning download/source not exposed through the current Data Hub
   or ArcGIS search results, provide that exact URL and rerun this sprint
   from the source gate.

---

## STOP for Master sign-off

This branch documents a halt event only. It did not perform matrix
authoring, district ingest, spatial backfill, nearest fallback, or audit
refresh.

Master decision needed:

1. Accept the halt and keep the complete-county source rule.
2. Dispatch a municipality-scoped MAPC/Norfolk experiment.
3. Provide a different authoritative MassGIS statewide municipal zoning
   source and rerun the ingest sprint.
