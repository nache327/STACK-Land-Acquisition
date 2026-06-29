# Montgomery County, PA — county_gis source manifest (Option A, Step 1 recon)

**Date:** 2026-06-29 · READ-ONLY recon · prerequisite for the JurisdictionConfig PR (Step 3).
**Outcome:** Montgomery PA zoning IS bindable via REST — the stale code comment
([pipeline.py:449-451](../../app/services/pipeline.py#L449), "zoning not on any public REST endpoint")
is **WRONG as of today**. A countywide municipal-zoning FeatureServer exists. But this is a **hybrid
pattern** (Bucks-style zoning + a city-NULL parcel layer) with **one real catch #34/#37 hazard** that
must be fixed before any ingest. Details below.

---

## Layers found on `gis.montcopa.org/arcgis/rest/services`

### 1. Spatial parcels (ALREADY INGESTED — 301,424 rows, the ring-armed layer)
`Parcels/Montgomery_County_Parcels/FeatureServer/10`
- Fields: `OBJECTID, TAXPIN, ALTERNATEID, PARCELTYPE, CALCACREAGE, TrueCalculatedAcres, …`
- **TAXPIN** = 12-digit string, e.g. `300034228005` (no padding) → this is `parcels.apn`.
- **NO municipality field, NO zoning, NO value** → confirms why `parcels.city` is NULL for all 301k
  Montgomery PA parcels and zoning is ~2%. The original `_pa_county("Montgomery", …)` registered this
  layer with no `muni_field`/`city_override`/`zoning_endpoint`.

### 2. Municipal zoning polygons (THE BIND TARGET — not previously wired)
`Zoning/Montgomery_County_Municipal_Zoning/FeatureServer/`**`11`** ← layer id is **11**, not 0 (/0 404s)
- geometryType polygon · WKID 2272 (PA State Plane) · **62 distinct municipalities** (matches expected 62).
- Fields: `OBJECTID, Name, Code, Type, Municipality, WebSite, Map_Date, Category, Last_Update, Shape__*`
  - **`Code`** = the real district abbreviation (e.g. `LI`, `HI`, `IP`, `BP`, `RS`, `TC1`, `VC`, `MDR2`).
  - **`Name`** = long label (e.g. "LI Limited Industrial").
  - **`Type`** = uniform constant **`"District"`** for every row — NOT a bucket. ⚠️ see catch below.
  - **`Category`** = broad bucket ("Industrial", "Residential", "Commercial", "Business Park/Office",
    "Mixed Use", "Institutional") → maps to `_ZONE_CLASS_FIELDS` ("CATEGORY").
  - **`Municipality`** = full NAME string ("Lower Merion Township", "Plymouth Township", …) — **Bucks
    pattern, name-native → NO `muni_name_map` crosswalk needed for zoning.**

### 3. Board-of-Assessment land table (enrichment, non-spatial)
`Parcels/GIS_BOA_LAND/FeatureServer/0` — a **table** (no geometry), 157 fields.
- Key: `PARCEL` = `300021576003` (12-digit, **same format as TAXPIN** → directly joinable to `parcels.apn`).
  Also `PARCEL_NUMBER`/`ALT_ID` (space-padded variants).
- Carries `MUNI_CODE` (numeric string "30"), `ZONING`, `TOTAL_ASSESSMENT`, `TOTAL_APPRAISAL`,
  `OWN1/2`, `ADDR1-3`, `LAND_ACRES`.
- ⚠️ **`ZONING` here is a COARSE county assessor class** (sample rows all `"V"`), **NOT** the municipal
  district code. Do **not** use BOA.ZONING for the zoning bind — it would collapse everything to ~5
  assessor letters. BOA is valuable only as a **value/owner/address/muni enrichment** join (future).

---

## Decision: how to bind zoning

**Use the spatial polygon layer (#2), exactly the Chester/Bucks playbook** — `zoning_polygon_endpoint`
= `Municipal_Zoning/11`, spatial PIP join to the 301k parcels. This is the only source of true municipal
districts. Expected lift: `parcels.zoning_code` 2% → ~95%.

**Rejected:** BOA attribute join for zoning (its ZONING is coarse assessor class, not districts). BOA
remains a strong *future* enrichment join for value/owner/city (PARCEL == TAXPIN), but that's out of
scope for the zoning-bind goal and not needed for Stage-1.

---

## ⚠️ CATCH #34 / #37 HAZARD — must fix before ingest (the one real blocker)

`_first(_ZONE_CODE_FIELDS)` ([zoning_ingestion.py:43](../../app/services/zoning_ingestion.py#L43)) checks
candidates in ORDER and stops at the first present field. Current order is:
`… "ZONING", "ZONINGCODE", "TYPE", "ZONE", "CODE", …`

The Municipal_Zoning/11 layer has BOTH a `Type` field (constant `"District"`) AND the real `Code` field.
Because **`"TYPE"` precedes `"CODE"`**, ingestion would bind **every Montgomery parcel to zone_code
`"District"`** — total zoning collapse. This is the same class of bug as the Bucks `ZoningAbbr`-first fix
(line 38-42).

**Audit done:**
- `"TYPE"` appears **only** at line 43 — no jurisdiction-specific comment claims it, and no other app
  code references `"TYPE"` as a code field. It looks defensive/speculative.
- `180420_zoning_districts` (field `Districts`, line 53-55) is referenced **only in a comment** — never
  wired (no endpoint URL, no registration). It was a prior recon note; superseded by Municipal_Zoning/11.

**Two fix options for the PR (need your call — infrastructure decision per the contract):**
- **(A) Reorder global list** — move `"CODE"`/`"ZONE"` (+ lowercase) ahead of `"TYPE"`. One-line, matches
  the existing "specific-field-first" convention. Low regression risk (no identifiable `TYPE`-as-code
  dependent), but it IS a shared-global change → needs a regression eyeball across already-ingested
  zoning layers + a note in the PR.
- **(B) Per-jurisdiction `zone_code_field` override** — add an optional field to `JurisdictionConfig`
  threaded into `_map_row` so Montgomery pins `Code` without touching the global order. Zero global-
  regression risk, but a larger diff (config + ingest signature + _map_row) and diverges from "same
  shape as Chester/Bucks."

**Recommendation: (A)** — smallest diff, fits the established pattern, and the audit shows no `TYPE`
dependent. Guard it with a one-query regression check (any ingested zoning layer whose real code sits in
a `TYPE` field) before merge.

---

## Muni crosswalk (Step 2) — NOT needed

Zoning layer is name-native (`Municipality` = full name). No `muni_name_map`. (BOA's numeric `MUNI_CODE`
would need a crosswalk, but BOA isn't used for the bind.) All 7 priority wealth munis present:
Lower Merion Twp, Narberth Boro, Whitpain Twp, Upper Dublin Twp, Abington Twp, Cheltenham Twp,
Plymouth Twp — plus Upper Merion Twp (King of Prussia — the real industrial belt). **62/62 munis confirmed.**

## Catch #38 disambiguation — clear
`gis.montcopa.org` = Montgomery County **PA** (montcopa). Distinct from Montgomery County **MD**
(`montgomery county, md` → `_md(… "MONT")`, MD iMAP) and Montgomery NJ. Zone codes (LI/HI/IP PA-style
borough/township districts) match PA, not MD's R/C/I overlay scheme. WKID 2272 = PA State Plane South. ✓

## Field-list additions (catch #34 proactive)
- `Code` / `Name` / `Category` → **already present** in `_ZONE_CODE_FIELDS` / `_ZONE_NAME_FIELDS` /
  `_ZONE_CLASS_FIELDS`. No additions needed — only the **reorder** (or override) above.
- Parcel `TAXPIN` → already ingested as apn (no change).

---

## Endpoints (verbatim, for the PR)
```
PARCELS (ingested):  https://gis.montcopa.org/arcgis/rest/services/Parcels/Montgomery_County_Parcels/FeatureServer/10
ZONING (to wire):    https://gis.montcopa.org/arcgis/rest/services/Zoning/Montgomery_County_Municipal_Zoning/FeatureServer/11
BOA (future enrich): https://gis.montcopa.org/arcgis/rest/services/Parcels/GIS_BOA_LAND/FeatureServer/0
```

## Residual Stage-4 note (not a Step-1 blocker)
`parcels.city` is NULL for all 301k (parcel layer has no muni). The zoning **bind** (zoning_code lift)
does NOT need city. But muni-specific Stage-4 verdicts will need a city-backfill — cleanly available
here from the zoning polygon `Municipality` (spatial) OR BOA `MUNI_CODE` (attribute). Tractable, unlike
Lake/Fairfield (which lack a usable muni source). Defer to a Stage-4 follow-up; flag in ledger.
