# Session B exceptions — Hudson County NJ (jid e7a3304a-9684-4fb6-9e25-8ba54542fe1c)

## BLOCKER (2026-07-14): Hudson is a Stage-1 binding gap, not a verdict batch

The batch premise ("14 towns, NJ name-bound → no rebind, ground top 3-4") does **not**
hold for Hudson. Findings:

1. **Zero zoning binding countywide.** `parcels.zoning_code` is NULL for **all 143,305**
   Hudson parcels (only NJ MOD-IV `land_use_code` is populated — 15F/15C/4B/1…). The
   needle join in `verify_batch.py` requires `m.zone_code = p.zoning_code`, so **no
   grounding can produce a single needle until parcels are zone-bound**. This differs
   from Morris/Monmouth (99.9% bound via NJTPA), which the batch premise assumed.

2. **NJTPA covers only Jersey City.** The NJTPA_Zoning FeatureServer has 11 layers;
   Hudson's only layer is **7 = Zoning_JerseyCity** (254 polygons). The other 13 towns
   (Hoboken, Secaucus, Kearny, Bayonne, North Bergen, Union City, West New York,
   Weehawken, Harrison, Guttenberg, East Newark, Fairview, Cliffside Park) have **no
   free regional zoning source** here. Each would need a per-town GIS layer to bind.
   (Layer 7 reachable via browser-UA curl — the `_NJ_JC_LANDUSE = None` note in
   pipeline.py:266 is stale; the "403" was the no-UA issue.)

3. **The wealth ring already zeroes the industrial towns.** wealth&≥1.5ac counts (dt=10,
   HV≥475k & HHI≥100k):
   - Jersey City **3,712**  |  Weehawken 283  |  Hoboken 61  |  Harrison 32  |  Union City 17  |  Secaucus **14**
   - North Bergen / West New York / Bayonne / Kearny / Guttenberg / East Newark = **0**
   The Secaucus/Kearny/Bayonne warehouse corridor sits **outside** the wealth ring →
   even if bound, ≈0 needles (correct no-op, per [[needle_vs_coverage_metric]]).
   Weehawken/Hoboken clear the gate but are ultra-dense high-rise residential (few/no
   industrial districts). **Jersey City is the only town with both real industrial land
   and a bindable source.**

4. **Jersey City is redevelopment-plan-dominated.** Of 108 distinct ZONE values in layer
   7, ~84 are individually-named redevelopment plans (Replan=Yes: Marine Industrial,
   Claremont Industrial, Greenville Industrial, Republic Container, Bayfront I, Canal
   Crossing, etc.) — each a separate use document. Base districts: R-1/1A/1F/2/3/4,
   NC, C, HC, OR, H, **I**, **M**, CBD, WPD, P/O, PI, G, U.

5. **JC self-storage regime NOT yet confirmed.** A promising "Mini-Warehouse/Self-Storage"
   PDF surfaced in search was **Lubbock TX** (catch #38 — `lubbodocs`; codes
   T/IDP/IHC/CB-1..6 are not JC codes). Discarded. JC Chapter 345 (Municode) still needs
   a verbatim read of the base I/M/HC/C use standards before any verdict.

## RESOLVED — Jersey City bind executed (2026-07-14, coordinator+Nache authorized: BIND ONLY, HOLD GROUNDING)

`_backfill-zoning-async` vs NJTPA layer 7 (job 10343743), `replace=false`, `spatial_join=true`.
Result: downloaded 254 → ingested 246 → **spatial_updated 58,106**. Final JC coverage
**58,040 / 58,797 = 98.7%** bound (7 wealth&≥1.5ac JC parcels left unbound = no polygon match).
- **#38 bleed cleaned:** 66 non-JC parcels (Hoboken 42, Bayonne 24 — boundary slivers whose
  centroid fell in a JC polygon) were coded, then NULLed back out. Bind is now JC-only (0 bleed).
- **Provenance note:** the endpoint set `zoning_code` but not `zoning_code_source` (still NULL on
  JC rows); `assessor_zoning_code` was already NULL (MOD-IV has no zoning) so nothing was
  overwritten. pre_zoning_count=0 → clean first bind. Flag for coordinator: NJTPA-source tag not
  recorded on these rows.

### DISTRIBUTION (the deliverable) — where the 3,705 wealth&≥1.5ac JC parcels sit
Concentrated almost entirely in **luxury Gold-Coast / downtown redevelopment areas**, NOT industrial:
Colgate 1,221 · Liberty Harbor North 736 · Hudson Exchange 570 · Exchange Place North 472 ·
St. John's 307 · Grove Street II 70 · Liberty Harbor 65 · (base R-3 154, R-1 12) · rest single digits.
These are high-rise residential/office towers — the "dense clears wealth but isn't a needle" caveat.

**Self-storage-plausible universe (I/M/HC + industrial RDPs) is OUTSIDE the wealth ring:**
`I` 310 bound / **0** wealth&1.5ac · `M` 133 / **2** · `HC` 229 / **8** · Republic Container 118 / 0 ·
Claremont Industrial 21 / 0 · Marine Industrial 4 / 0 · Bayfront I 16 / 0 · Canal Crossing 109 / 0.
→ **Realistic JC needle ceiling ≈ HC(8) + M(2) ≈ 10 parcels**, and only IF those districts permit
self-storage (unconfirmed — Chapter 345 read is held for the grounding batch). Grounding the ~84
RDPs blind would be low-yield: the wealth concentrates in residential/mixed-use RDPs that zone
storage out. **Recommendation to coordinator: Hudson is confirmed near-total no-op** — bind is done
and preserved for future re-scope, but the needle math does not justify a heavy RDP grounding pass.

## (original decision context, now resolved)

Producing needles requires a **county-scale production spatial-join** writing
`zoning_code` to Jersey City parcels from NJTPA layer 7:
`POST /_backfill-zoning-async?zoning_url=.../NJTPA_Zoning/FeatureServer/7&replace=false&spatial_join=true`
(additive/COALESCE, re-runnable). The auto-mode classifier **denied** this as an
unauthorized broad shared-DB mutation on a source the user never named. Awaiting
coordinator authorization to (a) bind Jersey City, then (b) read Chapter 345 + the named
industrial RDPs and ground JC's storage-permitting districts within the wealth ring.

Everything else in Hudson is an honest no-op / no-free-source pending.
