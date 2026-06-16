# Burlington Stage-1 zoning — source recon manifest (Prompt 1, 2026-06-16, NO WRITES)

Goal: authoritative MUNICIPAL zoning polygon layer carrying REAL zone codes for Moorestown,
Medford, Mount Laurel. Acceptance test: distinct zone-code values must include the real codes
(SRI/Moorestown BP-1/Medford PI), not generalized buckets. DVRPC region (NOT NJTPA).

## Parcels (the spatial-join target) — confirmed
- 174,852 Burlington parcels; **`zoning_code` NULL on all but 1 (0.0%)**; **0 `zoning_districts`** (no
  polygon layer to backfill from — confirms catch #27).
- Parcels carry **`apn`** (NJ PAMS block/lot, e.g. `0324_215_15.02`) + **`geom`** + **`centroid`**;
  all 18,518 Mount Laurel parcels have `geom`. **Join key = parcel centroid → zoning polygon (PIP).**
  No attribute join needed.

## Source per muni

### Medford — ✅ ACCEPTANCE TEST PASS (only automated source of the three)
- **ZoningHub ArcGIS Online FeatureServer:**
  `https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/ME0295_ZoningDistricts_04282023/FeatureServer/0`
- geom = **polygon**, **94 features**, zone-code field = **`Layer`**.
- Distinct `Layer` values: `APA, AR, CC, FD, GD, GMN, GMN-AR, GMS, HC-1, HC-2, HM, HVC, HVR, PD, PI,
  PPE, RC, RGD-1, RGD-2, RHC, RHO, RS-1, RS-2, SAPA, VRD` → **PI, HC-1, HC-2 all present** ✓ REAL CODES.
- Source: `MedfordZoning2023.dwg` (township CAD map → published as a feature service by ZoningHub; the
  `Layer` field = CAD layer = zone code). Verify CRS before PIP (reproject to match parcels). Caveat:
  PI is the only industrial district; Pinelands overlay south of Rte 70 still needs a separate flag.

### Mount Laurel — ⚠ NO automated source found (REJECT GovPilot/county)
- Public viewer = **GovPilot** (`map.govpilot.com/map/NJ/mountlaurel`) — SaaS, only `/api/js`, no open
  ArcGIS REST / FeatureServer. **NOT in the ZoningHub org** (no Mount Laurel service; `mountlaurel.zoninghub.com` 302s).
- → Needs out-of-band acquisition: **request the zoning shapefile from the township GIS engineer**, OR
  probe the GovPilot backend, OR digitize the official zoning map PDF.

### Moorestown — ⚠ NO automated source found (same as Mount Laurel)
- Public viewer = **GovPilot** (`map.govpilot.com/map/NJ/moorestown`). Not in ZoningHub. → same options.

### Burlington County GIS — REJECT as zoning source
- `co.burlington.nj.us/1209/GIS-Data-Downloads` = **parcels only** (per-muni tax-lot shapefiles +
  countywide 2018 geodatabase). **No zoning layer.** (Useful for parcels, not zoning.)
- NJGIN = statewide parcels; no municipal zoning published for these munis.

## Recommendation + plan-impact (the gate decision)
**The Prompt-2 anchor must shift from Mount Laurel → Medford.** Mount Laurel was the intended validation
anchor (cleanest verdicts, SRI), but it has **no ingestable zoning source** (GovPilot). Medford — the
*weakest-verdict* muni (all VERIFY) — is the **only one with a clean REST layer** that passes the
acceptance test. So:
- **Medford = ingest-ready** (ZoningHub FS) → make it the Prompt-2/3 validation anchor: ingest the 94
  polygons → centroid-PIP join → confirm coverage jumps 0%→high with PI/HC-1/HC-2 real counts. (Its
  *verdicts* still need the §412 use schedule, but the zoning-LAYER ingest+join can be validated now.)
- **Mount Laurel + Moorestown = acquisition-blocked** → Nache decision: request zoning shapefiles from
  each township (GovPilot towns usually have the source SHP from their engineer), then ingest the same
  way. The held verdicts (SRI/BP-1) remain ready for when their layers land.

**STOP — gate.** No ingest performed. Confirm: proceed with Medford as the ZoningHub-sourced anchor?
And how to acquire Mount Laurel + Moorestown (shapefile request vs digitize)?
