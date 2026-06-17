# Medford bind-test coverage (Burlington Prompt 2, re-anchored) — 2026-06-16

**Catch #27 bind-test: PASS.** Coverage jumped 0% → 100% on Medford-bounded parcels. The
ZoningHub-FS → zoning_districts → centroid-PIP → parcels.zoning_code pipeline is validated; the
pattern scales to Mount Laurel + Moorestown once their shapefiles arrive.

## Pipeline
- Ingested **94 polygons** from ZoningHub FS `ME0295_ZoningDistricts_04282023` (zone code in `Layer`,
  pulled GeoJSON outSR=4326 → SRID-4326 to match parcels) into `zoning_districts`
  (jurisdiction=Burlington, muni in raw_attributes — no `municipality` column; source='arcgis').
- Centroal-PIP join (correlated subquery, smallest-area containing district) → `parcels.zoning_code`
  for `city ILIKE 'Medford township%'`. Idempotent (skips re-ingest by source_url).

## Coverage
- Medford township parcels: **9,880** · now zoned: **9,877 (100.0%)** · unmatched: 3.
- **Verdict-relevant:** PI = 17 (10 ≥1.5ac) · HC-1 = 51 (26 ≥1.5ac) · HC-2 = 21 (9 ≥1.5ac).
- Top zones: GD 3,226 · RGD-1 1,640 · RGD-2 1,339 · GMN 1,151 · GMN-AR 504 · HM 305 · RS-2 234 ·
  GMS 227 · AR 201 · RHO 197 · CC 158 · HVC 121 · … · PI 17 · HC-1 51 · HC-2 21.
- **Split parcels (geom intersects >1 district): 861** — centroid-assigned the containing district;
  acceptable for the bind-test, revisit if a specific split parcel becomes a needle.

## Code reconciliation vs held verdict matrix (preview of Prompt 3)
The held Medford verdicts target **PI / HC-1 / HC-2** — all now present with real parcel counts, so the
verdicts will bind. The GIS layer also carries many codes the verdict matrix doesn't cover yet
(GD/RGD-1/RGD-2/GMN/GMN-AR/HM/GMS/RHO/CC/HVC/VRD/PPE/HVR/RHC/SAPA/APA/FD/PD/RS-1/RS-2/RC/AR) — those are
residential/conservation/village codes, expected PROHIBITED, but enumerate them in the full verdict pass.

## Gate (Prompt 2 Step 4) — STOP
NO verdicts applied (Medford verdicts need the §412 use schedule paste). Mount Laurel + Moorestown
untouched (no source yet — need shapefiles). Nache reviews → greenlight Prompt 3 (spot-check + reconcile)
→ then Prompt 4 (apply verdicts, only the schedule-confirmed ones). Pinelands check (parcels S of Rte 70)
is a Prompt-3 item before relying on PI.
