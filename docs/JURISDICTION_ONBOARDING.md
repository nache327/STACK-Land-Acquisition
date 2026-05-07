# Jurisdiction Onboarding Playbook

How to add a new city / county to the ParcelLogic pipeline end-to-end.
Each onboarding takes 30–60 minutes once you know the patterns. This doc
captures everything learned from Marlboro (NJ) on 2026-05-07.

## What you need before starting

For every jurisdiction, you need exactly **three URLs**:

1. **Parcel source** — an ArcGIS FeatureServer / MapServer that publishes
   parcel polygons + APN + address (owner name optional, often redacted).
2. **Zoning source** — an ArcGIS FeatureServer / MapServer that publishes
   zoning-district polygons with at least a zone code field.
3. **Ordinance URL** — a Municode / eCode360 / AmericanLegal page that
   contains the city's permitted-use schedule per zone.

If any of the three is missing, the jurisdiction is not onboardable on the
free path — escalate to a paid data source (Regrid for parcels+owners,
ATTOM for zoning, manual transcription for ordinances).

---

## Step 1 — Find the parcel source

### Statewide vs. county vs. city

Most NJ + PA + NY work uses **statewide MOD-IV-style services**, where every
city draws from one giant table filtered by `COUNTY=` or `MUN_CODE=`.
Utah uses per-municipality UGRC layers. CA / TX / FL vary by county.

| State | Primary parcel pattern |
|---|---|
| **NJ** | `services2.arcgis.com/XVOqAjTOJ5P6ngMu/.../Parcels_Composite_NJ_WM/FeatureServer/0` — filter with `COUNTY='MONMOUTH'` |
| **PA** | County-level. Allentown uses City_Landuse layer; Philadelphia uses PWD_PARCELS. PASDA at `pasda.psu.edu` aggregates state-level |
| **UT** | UGRC publishes per-county at `mapserv.utah.gov/arcgis/rest/services/SGID/CADASTRE/Parcels_*/FeatureServer/0` |
| **NY** | NYC: MapPLUTO. Upstate: per-county tax-parcel viewer |

### Validating a candidate parcel endpoint

Probe the layer in your browser with `?f=pjson` to confirm it returns a
real schema:

```
https://<service>/FeatureServer/0?f=pjson
```

Look for:
- `geometryType: "esriGeometryPolygon"`
- A field that looks like an APN (`PARCEL`, `PIN`, `PAMS_PIN`, `BBL`, etc.)
- A field that looks like an address (`PROP_LOC`, `SITUS`, `ADDRESS`, `Address`)
- Total feature count via `?where=1=1&returnCountOnly=true&f=json` (sanity-check is ≥ 1,000 for any real city, ≥ 100,000 for a county)

### Add it to `pipeline.py`

For NJ counties, use the existing `_nj()` helper:

```python
monmouth = _nj("Monmouth", "Monmouth County, NJ", _NJ_MONMOUTH_ZONING)
```

…and register both county-keyed and city-keyed aliases in
`_build_nj_jurisdictions()`:

```python
"monmouth county":    monmouth,
"monmouth county, nj": monmouth,
"marlboro":           monmouth,
"marlboro, nj":       monmouth,
```

For other states, add a `JurisdictionConfig` directly to the registry.

---

## Step 2 — Find the zoning source

This is the hardest step. Most townships only publish PDF zoning maps;
those don't help us. You need a **polygon FeatureServer**.

### Where to look (in order)

1. **ArcGIS Hub:** search `hub.arcgis.com` for `<county> zoning` or
   `<state> municipal zoning`. NJTPA aggregates all 13 NJ counties they
   cover. PASDA aggregates much of PA.
2. **County GIS portal:** `gis.<county>.<state>.us` or `<county>nj.gov/gis`.
   Many counties expose a "Zoning" layer in their Open Data Hub.
3. **State GIS open-data portal:** `njogis-newjersey.opendata.arcgis.com`,
   `pasda.psu.edu`, `gis.utah.gov`.
4. **Search ArcGIS Online directly** for the muni name +
   `zoning FeatureServer`.
5. **Municipal IT departments** publish via Esri ArcGIS Online accounts.
   Search `services7.arcgis.com` / `services2.arcgis.com` etc. for the
   city name.

### Gotchas

- **NJTPA datasets are "public" but the REST endpoint returns 403** to
  unauthenticated clients (license-gated). The Hub UI proxies via an
  authenticated path. **Workaround:** download GeoJSON via
  `curl.exe -A '<browser UA>' -H 'Referer: https://hub.arcgis.com/'` and
  paginate manually with `resultOffset` (max 1000–2000 rows per request).
  See `Desktop/import_marlboro_zoning.py` for the working pattern.
- The Monmouth County tax board (`taxboardportal.co.monmouth.nj.us`)
  intermittently returns 503 "Could not access any server machines" —
  check on a different day if it's down.
- **NJDCA Statewide Municipal Zoning** is *not* polygons of zone districts
  — it's a directory of muni boundaries with links to ordinance URLs.
  Useful as a fallback for ordinance discovery, useless as zoning data.

### Validating a candidate zoning endpoint

Same `?f=pjson` probe. Look for fields like `ZON_ID`, `ZONING`, `ZONE`,
`ZoneCode`, `Code`, `District` and a description field. Sample a few
features with `?where=1=1&resultRecordCount=5&f=geojson` and confirm
zone codes look real.

### Add it to `pipeline.py`

Set the `zoning_polygon_endpoint` in the JurisdictionConfig. The pipeline
auto-discovers zone codes on parcel ingest via the spatial backfill in
`spatial_backfill.py`.

---

## Step 3 — Find the ordinance URL

The pipeline uses Claude to parse the ordinance text into the
`zone_use_matrix` table (self_storage, mini_warehouse, light_industrial,
luxury_garage_condo permission per zone with citations + confidence).

### Where to look

1. **eCode360** — `ecode360.com/<city slug>` — many NJ + NY townships.
   Marlboro lives at `ecode360.com/12875623`.
2. **Municode** — `library.municode.com/<state>/<city>` — common for
   PA + FL + TX + Western states.
3. **AmericanLegal** — `codelibrary.amlegal.com/codes/<state>/<city>`.
4. **City's own zoning ordinance PDF** as a last resort. The LLM parser
   handles text input; PDFs need OCR first.

### Add the ordinance URL

Set `ordinance_url` in the JurisdictionConfig.

---

## Step 4 — Run the pipeline

From the home page, type the jurisdiction name (e.g. `marlboro, nj`) and
hit Analyze. The pipeline:

1. Discovers the JurisdictionConfig from the registry
2. Downloads parcels (resume-aware: skips if `count > 1000` exists already)
3. COPY-ingests parcels into PostGIS
4. Refreshes the bbox + commits immediately (so dashboard auto-fits)
5. Downloads zoning polygons (if endpoint configured)
6. Spatial-backfills `zone_code` + `zone_class` onto parcels
7. Runs flood / wetland / AADT overlays
8. Parses ordinance with Claude → populates `zone_use_matrix`
9. Marks job ready

Watch logs for:
- `Total features to download: N` (parcel count plausibility check)
- `COPY staged X/N parcels` (ingest progress, ~25K rows per chunk)
- `Merge result: 'INSERT 0 N'` (final upsert)
- `Ingested N parcels for jurisdiction <id>`

Total runtime for a 250K-parcel county: ~5 minutes if zoning is small,
10–15 with zoning + overlays + ordinance parse.

---

## Step 5 — Quality gates (after each ingest)

Before declaring a jurisdiction "production-ready":

| Check | Pass criterion | How |
|---|---|---|
| Parcel count plausible | Within ±15% of public total | Compare to muni assessor's published parcel count |
| Bbox lands on the city | Map auto-fits to right area | Open the dashboard, confirm the map shows the jurisdiction |
| Zoning coverage | ≥ 70% of parcels have `zoning_code` set | `SELECT COUNT(*) FILTER (WHERE zoning_code IS NOT NULL) / COUNT(*) FROM parcels WHERE jurisdiction_id = X` |
| Matrix coverage | ≥ 80% of distinct `zoning_code` values are in `zone_use_matrix` | `audit_zone_matrix.py` |
| LLM confidence | ≥ 0.70 average across `zone_use_matrix` rows | The parser logs this; cross-check via `SELECT AVG(confidence) FROM zone_use_matrix WHERE jurisdiction_id = X` |
| Sample 5 random parcels | Drawer shows correct address + zone + use permissions | Click 5 parcels in the dashboard, sanity-check |

If anything fails, see the troubleshooting section.

---

## Troubleshooting

### Parcels download but ingest count is wildly low

Source likely has duplicate APNs that we're collapsing. Check the worker
log for `Collapsed N duplicate APN rows before parcel upsert`. If N is
huge, the upstream source is using a non-unique APN field — pick a better
one from the candidate list in [ingestion.py:36-50](backend/app/services/ingestion.py#L36).

### Map shows world view (no auto-fit)

`jurisdiction.bbox` didn't get committed before you opened the dashboard.
Hard refresh (Ctrl+Shift+R). If it still doesn't fit, check that
`refresh_jurisdiction_bbox` actually ran — `SELECT bbox FROM jurisdictions
WHERE id = X` should be a 4-element array.

### Zoning download returns 403 (NJTPA, etc.)

The REST endpoint is license-gated. Use the manual GeoJSON download
pattern with `curl.exe -A '<browser UA>'` — see
`Desktop/import_marlboro_zoning.py` for a working template.

### `zone_use_matrix` is mostly `unclear`

Two possible causes:

1. The LLM ordinance parse failed (check job_steps for the `parse_ordinance`
   step). Re-run with the LLM in record mode and inspect the snapshot.
2. The zone codes in `zoning_districts` don't match the codes in the
   ordinance text. Compare: `SELECT DISTINCT zone_code FROM
   zoning_districts WHERE jurisdiction_id = X` vs. the ordinance's
   district list. If they differ in formatting (e.g. `R-40` vs. `R40`),
   normalize.

### Owner names are NULL on every parcel

This is the norm, not a bug. NJ (Daniel's Law), Philadelphia OPA, and
most Utah cities redact owner names from public ArcGIS endpoints. Use
PropStream or Regrid for owner enrichment — see the `Owner Data` section
of the main project README.

---

## Three-URL examples (working configs)

### Marlboro Township, NJ (→ Monmouth County)

| Resource | URL |
|---|---|
| Parcel source | `https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0` (with `where=COUNTY='MONMOUTH'`) |
| Zoning source | `https://gis.njtpa.org/server/rest/services/LandUse/NJTPA_Zoning/FeatureServer/3` (NJTPA-licensed; manual GeoJSON download required) |
| Ordinance URL | `https://ecode360.com/12875623` |

### Allentown, PA

| Resource | URL |
|---|---|
| Parcel source | `https://gis.allentownpa.gov/.../City_Landuse/FeatureServer/0` |
| Zoning source | `https://gis.allentownpa.gov/.../CityZoning/FeatureServer/0` |
| Ordinance URL | `https://ecode360.com/<allentown-id>` |

### Draper, UT

| Resource | URL |
|---|---|
| Parcel source | UGRC SGID `Parcels_SaltLake/FeatureServer/0` (filtered to Draper boundary) |
| Zoning source | Draper City GIS open-data portal |
| Ordinance URL | `https://library.municode.com/ut/draper/codes/code_of_ordinances` |

---

## Adam's quick checklist

For each new jurisdiction Adam onboards:

- [ ] Got parcel source URL (probed with `?f=pjson`, has APN + address fields)
- [ ] Got zoning source URL OR confirmed PDF-only (escalate to manual)
- [ ] Got ordinance URL (eCode360 / Municode / AmericanLegal)
- [ ] Added `JurisdictionConfig` to [pipeline.py](backend/app/services/pipeline.py)
- [ ] Added city-keyed aliases (so users can type the city name, not just the county)
- [ ] Pushed to a feature branch (NOT main while production data is loading)
- [ ] Ran the analyze flow once locally / in a dev env
- [ ] Verified all 6 quality gates above
- [ ] Merged to main
