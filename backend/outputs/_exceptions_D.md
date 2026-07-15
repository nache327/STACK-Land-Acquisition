# Session D — Union County NJ — exceptions / escalations

jid `16dc5ad9-8211-47c6-bfad-93bf588b15e4`

## STAGE-1 GAP DISCOVERED + RESOLVED: Union parcels were NOT zone-bound

The batch brief assumed Union was "NJ name-bound → no rebind" (like Morris). **It was not.**
- Union parcels: `zoning_code` 100% NULL (0 / 147,627), `zone_class` NULL, no `zoning_districts` geometry.
- Morris (comparison): 177,464 / 177,532 bound + 3,904 zoning_districts rows.
- **NJTPA_Zoning FeatureServer has NO Union layer** — it exposes only Bergen, Hunterdon, Middlesex,
  Monmouth, Morris, Somerset, Sussex, Jersey City, Warren. Union was never in the "5 NJ Tier-1 bound" set.

**#38 trap avoided:** the discovery table's top ArcGIS hit `Union_County_Zoning_Map_WFL1` is **Union County,
NORTH CAROLINA** (ADMIN = Monroe/Waxhaw/Weddington/Mint Hill/Indian Trail — Charlotte-area). Discarded.

**Resolution — official Union County NJ GIS binding source:**
`https://oms.ucnj.org/server/rest/services/Public_Map/Public_Map_Service/MapServer/18` ("County Zoning",
1,432 polygons, all 21 munis, fields Municipal / ZoneID / ZONENAME). Spatial centroid-join
(`scripts/_bind_union_nj_zoning.py`) matched **100%** of parcels. Batch-1 scoped to 4 towns (23,889).
**Batch-2 (2026-07-14): county-wide bind AUTHORIZED + DONE** — `--only-unbound` (replace=false) bound the
remaining 123,713 parcels; county now 99.98% coded (147,602/147,627). **Winfield township IS covered by
UCNJ** (706 parcels bound — the NJTPA-Atlas gap; 0 wealth-pass so a no-op regardless).

## BATCH-2 grounded (4 newly-bound wealthy-industrial towns, +66 needles → county 90)
- **Clark** CI + LCI — self-storage EXPLICITLY named permitted (§195-136.1B(21)/§195-136.2B(19)) → 14 needles.
- **Mountainside** L-I + LI/AH — self-storage EXPLICITLY named conditional (§1004) → 33 needles (biggest).
- **Springfield** I-20 + I-40 — "warehousing" named by-right (App.A #8) → warehouse convention → 8 needles.
- **Cranford** C-1/C-2 ("Warehouses"=PPU) + ORD-1 (=ord C-3 "Office distribution centers"=PPU) → 11 needles.
Berkeley-Heights-vs-New-Providence rule applied cleanly (Springfield H-C "Wholesale business" ≠ warehouse → prohibited).

## Per-town notes
- **New Providence** — GIS code "LI" was RENAMED to "TBI-2" (Technology & Business Innovation Zone II) in the
  current Ch. 310 (adopted Nov 2022). Parcels carry "LI"; verdict grounded on current TBI-2 use regs, code
  reconciled (old GIS code → current ordinance zone). [Hudson/MAPC stale-code pattern.]
- **Westfield** — NO industrial district (all residential / General Business / Office / Commercial). 160
  wealth+1.5ac parcels are large residential lots → correct **no-op**, not a gap. Not grounded this batch.

## RECONCILIATION FLAG for coordinator — binding source choice (UCNJ GIS vs NJTPA Atlas)
The Essex session found a region-wide **NJTPA Atlas 082025** layer that reportedly covers all 13 counties
INCLUDING Union (`_bind_essex_njtpa_atlas.py`, Essex bound 99.81%). I bound Union via the **official UCNJ
county GIS** instead (`_bind_union_nj_zoning.py`, ZoneID = the ordinance's own codes, which is what my matrix
rows key on). **DO NOT re-bind these 4 towns via a different source with different code strings** without
re-reconciling the matrix — the needle join is `zone_use_matrix.zone_code = parcels.zoning_code` (exact), so
an Atlas rebind that normalizes "LI"/"M-1"/"TBI-2" differently would silently un-bind my 24 needles. For the
county-wide bind of the remaining 17 towns, either (a) extend the UCNJ bind (`--cities` empty) — consistent
with these 4 — or (b) Atlas-bind and re-run `_apply_union_nj_batch1.py` reconciled to the Atlas codes.

## Remaining un-grounded Union towns (low priority)
Elizabeth/Linden/Rahway/Hillside/Roselle/Roselle Park/Kenilworth = 0 wealth-pass (heavy-industrial OUTSIDE
the wealth ring = correct #38 no-op). Marginal: Union township (24 wealth+acre, avg HV 454k — mostly below
gate; has BB/I codes), Fanwood (18, LI:2), Garwood (15, LI:2), Watchung (2). Westfield (160 wealth+acre) =
no industrial district → no-op. These are small tails; grounded on request.

## Genuine ambiguities (batch-2)
- **Cranford ORD-1** (conf 0.72): GIS "Office Research, Distribution" has no current Ch.255 code letter;
  mapped to ordinance C-3 ("Office distribution centers"=PPU). All C-1/C-2/C-3 permit warehouse/distribution
  by-right so ss/mw=conditional holds regardless, but confirm ORD-1→C-3 vs the adopted zoning-map legend.
- **Mountainside I-40** (2 lots, conf 0.60): not in Mountainside's 7-district schedule (§1001) — GIS artifact;
  grounded prohibited. 0 wealth+acre so no needle impact.
- **Springfield PUD** (conf 0.70) & **Clark (COR) overlay** (conf 0.65): conservative-prohibited pending
  plan/overlay text; no wealth+acre needle impact.

## Genuine ambiguities (batch-1)
- **New Providence RL** (13 parcels) and **SCOTCH PLAINS SCRPD** (57 parcels) grounded conservative-prohibited
  (conf 0.70): stale/redevelopment codes without a parsed current use list. Revisit if a deal lands there.
- **Berkeley Heights OR-A** (1 parcel, conf 0.65): repealed → MU; grounded prohibited pending MU use table.

---
# PHASE 5 SOUTH (2026-07-15) — Williamson TN + Fulton GA (per-city SLCo jids)

Ring-precompute run per-city (worker path). **407 wealth-gated needles across 4 cities, all verify_batch CLEAN / gate PASS:**
- **Brentwood TN** [e0df78b2-de04-4e43-bf3b-c5244eb4613c] — **59** (C-3 Commercial Service-Warehouse; self-service storage named by-right §78-242(1)(b)).
- **Franklin TN** [307285f8-9426-4f17-9e66-999c8e01218f] — **277** (LI 169 + RC12 92 + HI 16; self-storage named §5.1.4.V).
- **Sandy Springs GA** [b49ac34f-6394-47ba-87e3-149b6ae0d706] — **29** (CX-3 cond 25 + CC-3 perm 4; self-service storage named Div. 7.2).
- **Atlanta-Buckhead GA** [a5d68bcd-ce4b-446a-aefb-23613e6f9013] — **42** (O-I/O-I-C/C-3/C-3-C/I-1 perm + SPI-15 SA1 cond; Atlanta secured-/self-storage terms).

## #38 catches (mislabeled family)
- **Brentwood SI-1..SI-4 = "Service Institution"** (Religious/Educational/Cultural-Gov/Retirement) — institutional, NOT industrial despite large acreage → all prohibited (only C-3 is the warehouse district). "-IP" suffix = GIS annotation (base AR/OSRD residential). Big trap avoided.
- **Franklin ER = Estate Residential** (NOT "Employment") and **CI = Civic Institutional** (NOT Commercial/Industrial).

## ESCALATE — Franklin CI + RC12 (graphic-matrix reads, need human verification)
Franklin's §5.1.3 use matrix is GRAPHIC DOTS (no text layer); the research agent read it via dot-detection.
- **CI (Civic Institutional, 124 large parcels): HELD → grounded PROHIBITED.** The matrix *appears* to show self-storage/general-warehousing = half-circle (permitted-w/-standards) in CI, but that is semantically surprising for a civic-institutional district and rests on a dot read. NOT claimed as ~124 needles pending human spot-check of an actual CI-mapped parcel. **If verified permitted, re-ground CI → +N needles.**
- **RC12 (Regional Commerce): grounded conditional (conf 0.72) = 92 of Franklin's 277 needles.** Self-storage half-circle read from the same graphic matrix; commercially plausible (regional-commerce), but confirm against the official matrix substrate. RC4/RC6 (self-storage not listed) grounded prohibited.
- Franklin LI/HI self-storage (§5.1.4.V) is text-confirmed (the named use + definition are in the text layer) — high confidence.

## INFRASTRUCTURE — ring-precompute worker stalls in bursts (coordinator: ring traffic control)
Firing 4 per-city `_precompute-ring-metrics-worker` jobs in parallel: Brentwood + Sandy Springs completed first pass; **Franklin + Buckhead stalled partway** (frozen ~20 min after an initial burst) and required 2 re-enqueues each to reach 100% (each enqueue advances one chunk then stops — likely Mapbox rate/tract-cache bursting). All 4 now 100%. Recommend staggering per-city ring jobs (2 at a time) rather than 4-way parallel.

## Notes
- Buckhead 500-ft BeltLine-corridor exclusion (I-1/C-3/O-I self-storage) is a parcel-level caveat noted in verdicts; Buckhead is north of the BeltLine and existing facilities are grandfathered → not applied per-parcel.
- Did NOT run CoStar close-out or re-score (per coordinator).

---
# PHASE 5 DENVER + FRANKLIN CORRECTION (2026-07-15)

## Franklin TN accuracy close-out — 277 → 185 needles
Text-verified the graphic §5.1.3 dot-matrix reads (see commit): **CI REFUTED** (Flex Building industrial
type is LI/HI-only §6.13; CI building types civic-only) → stays prohibited. **RC12 DEMOTED** to prohibited
(#58) — self-storage is NOT a named use in text (§5.1.4.V lists no districts); dot-read corroborated-plausible
but unconfirmable; removes 92 needles (restorable if the authoritative graphic matrix is human-verified).
**LI/HI kept conditional** (text-corroborated: named §5.1.4.V + Flex Building §6.13). Franklin = **185** (LI 169 + HI 16).

## Denver per-city pockets (ring-precompute per-city; RING RULE ≤2 jobs at once honored)
- **Greenwood Village CO** [9fd6996b-a4c3-4433-a737-9c705bff92ed] — **3 needles**, verify CLEAN / gate PASS.
  Self-storage EXPLICITLY named in ONE district only: **B-3 Community Business** (Special Use §16-16-30(2))
  → ss/mw conditional. **Named-confinement (Boonton rule) applied**: T.C. has warehousing by-right
  (§16-19-20(1)) but self-storage is confined to B-3 by the closed list (§16-1-10(b)(2)) → T.C./L-I grounded
  li-permitted-only (NOT self-storage). A naive warehouse-convention read of T.C. would have falsely armed
  ~113 parcels. **#38**: O-1/O-2 = Open Space (not Office); M-C = Mixed Commercial (not Metro Center).
- **Highlands Ranch CO** [524b1948-f806-4007-b7e3-6ef7219c2b2c] — **1 needle** (GI). **GATE FAIL = benign
  false-positive**: the domination check flags "PD covers 99.9%", but HR is a genuinely master-planned PD
  community (Highlands Ranch Planned Development Guide) — NOT a mis-bound field. PD grounded **prohibited**
  (conservative) so it creates no false needles. GI (§1402.01→LI §1302.16/§1302.30) + C (§1202.03) =
  mini-warehouse/warehouse by-right. Ring at 96.8% (last PD chunk stalled; immaterial — PD is prohibited).
  **ESCALATE**: self-storage IS permitted by-right in the HR **Industrial Park Planning Areas
  (PA 75-78/80/81/84-88)** ("Service Industry" def #101 folds in warehousing+self-storage), but the bare
  "PD" code cannot identify a parcel's PA → needs PA-level parcel mapping to isolate that real opportunity.

## Handed back to coordinator (not grounded this session)
- **Cherry Hills Village** [cea334ed-34b1-4211-a372-6182815733c8] — 0.1% zoned (essentially UNBOUND);
  pure-residential horse-property enclave → expected no-op (like Paradise Valley/Rumson). Needs a CO zoning
  source to formally confirm; low value (expected 0 needles). Deferred.
- **Douglas County** [ec296fd0-...] (121,742 parcels, 0% zoned) + **Arapahoe County** [5c4b612c-...]
  (211,557 parcels, 0% zoned) — large unbound county jids. The wealth pockets (Greenwood Village, Highlands
  Ranch) are already covered by per-city jids, so the county binds are lower priority. Need a sourced CO
  zoning layer + #38 CRS/coverage/sample-city dry-run BEFORE apply (Nassau/Indiana trap). Not attempted this
  session (no clean source validated). Recommend DRCOG regional or per-county GIS, dry-run-first.

## RING infra (reconfirmed)
Per-city worker ring jobs still stall in bursts (GV finished clean; HR needed 2 re-enqueues, stuck at 96.8%).
Kept to ≤2 concurrent per the rule. Stagger; expect 1-2 re-enqueues per job.

---
# CONTRA COSTA COUNTY CA — Batch-1 (2026-07-15) — jid 7ad622d4-0d36-4fe5-ad8b-53352bdac162

County-scale ring-precompute COMPLETE (387,492/387,492, coordinator-authorized single job, finished in one pass). **304 wealth-gated needles, casing CLEAN** (grounded cities):
- **Concord: 223** (OBP 95, IMX 44, SC 25, IBP 22, L-I 20, H-I 16) — self-storage named UP/conditional in all business-park/industrial + SC.
- **Walnut Creek: 36** (SC permitted 7 + B-P-100/200 CUP 29). Self-storage = "Mini-Storage" named, confined to S-C/B-P.
- **Pacheco: 19** (C-M 11, L-I 5, C 3) · **Pleasant Hill: 11** (LI 6, C 5) · **Byron 5, Bay Point 4, Crocket 3, Knightsen/Danville/Bethel Island 1**.

## #38 disambiguations (all confirmed from ordinance TEXT — big traps avoided)
- **CA "M-##" = MULTIPLE-FAMILY RESIDENTIAL** (density du/acre), NOT Manufacturing: Walnut Creek M1/M3/M15/M25, Danville M-8/13/20/30, County M-6/9/12/17/29 → all prohibited. (Would have falsely armed ~hundreds.)
- **County T-1 = Mobile Home Park, F-1 = Water Recreational, S = R-40, W-3 = Controlled HEAVY Industrial** (not water). T-1/F-1/S residential/rec → prohibited (killed the huge T-1/F-1 counts in Bay Point/Pacheco/San Pablo/Bethel Island/Discovery Bay).
- Named-confinement respected: Concord WMX self-storage explicit "–" (prohibited) despite warehouse by-right.

## GATE FAIL — pre-existing data, NOT this batch
The post-ingest gate HARD-FAILs on "over-length zoning_code(s)" (23 distinct, e.g. "CG General Commercial",
"IB Industrial Business", "CM-1 Commercial Mixed-Use Residential", "IW Industrial Water-Related"). These are
**verbose descriptive strings the source GIS stored as zoning_code** for **Richmond (13,537 parcels), San Pablo
(82), El Cerrito (33), El Sobrante (248)** — cities I did NOT ground (El Sobrante grounded prohibited-only,
residential). **None affect the 304 needles** (all in Concord/WC/Pacheco/PH/Byron/etc. with clean short codes).
It is a jurisdiction-wide pre-existing data characteristic, not a poison/mis-bind from this grounding.
**Fix (follow-up): normalize those codes** (strip descriptive suffix, e.g. "IB Industrial Business" → "IB")
**then re-run the gate.**

## HANDED BACK — incorporated cities needing per-city research (in-ring industrial counts)
Not grounded this batch (own code systems, need ordinance research):
- **Richmond** — IB Industrial Business (13), IL Industrial Light (4), CM-5 Activity Center (21), CR Regional
  Commercial (28), IW Industrial Water-Related. Real industrial + needs code normalization. Priority follow-up.
- **Martinez** — H-I (81), L-I (22), M-PA/C-I (9). Own code; refinery-town heavy industrial.
- **Oakley** — M-H (56), LI (23), SP-1..SP-4 (specific plans), C (66). (M-12/M-17/M-9 = county multifamily → prohibited.)
- **Antioch** (P-D/S-P/C-2/C-3/WSCD), **Pittsburg** (IG/GQ; mostly T-1 mobile-home), **Hercules**, **Pinole**
  (CMU/OIMU/OPMU/H-I), **San Pablo** (mostly T-1 + descriptive codes), **El Cerrito** (TOHIMU/TOMIMU form-based),
  **Moraga** (CC/MCSP-*), **Lafayette** (C-1/C tiny), **Orinda** (DC tiny), **San Ramon** (ZM-GC/ZM-MU/ZM-MUCC),
  **Brentwood-CA** (BBSP/PA-1/C-2/L-I), **Clayton** (L-C tiny). Most named-wealthy towns (Lafayette/Orinda/
  Danville/San Ramon) are residential-wealth with thin/no industrial → likely small or no-op.

## Accuracy notes
- Concord Ch.18.50 (OBP/IBP/IMX/HI) use cells are from a 2016 codepublishing snapshot (Cloudflare-blocked live);
  self-storage=UP + purpose statements match current — grounded conditional at conf 0.78 (SC current = 0.85).
- County H-I / W-3: heavy-industrial manufacturing named by-right; warehouse/self-storage NOT clearly by-right
  → conservatively ss/mw prohibited, li permitted (a-fortiori warehousing argument NOT applied; revisit if a deal lands).
- 'None'-city parcels (865, NULL city) not grounded (buybox join needs city).
- No re-score / no CoStar (per coordinator).

---
# CONTRA COSTA batch-2 + TRACK-2 (2026-07-15)

## Contra Costa CA — code normalization + Richmond/Martinez grounding
- **Normalized 21,458 parcels' verbose zoning_code strings → leading token** (`_normalize_contra_costa_codes.py`,
  coordinator-authorized): "IB Industrial Business"→IB, "RL2 Single Family Low Density Residential"→RL2, etc.
  0 codes >20 chars remain → **clears the batch-1 gate FAIL** (combining codes "A-2 -BS"/"C -CE"/"H-I -X" kept).
- **Richmond** (`_apply_richmond_ca.py`): self-storage = named "Mini-Storage", CONDITIONAL (CUP) in **IB, IL,
  IG, CG** (§15.04.204/.203; def §15.04.104.020); x in IW/ILL/CR/CC; not-listed (prohibited) in CM-1..CM-5.
  Needles ≈ IB 13 + IL 4 + CG 3. **Named-confinement decisive: CM-5 (21 in-ring) + CR (28 in-ring) are NOT
  needles** (self-storage not listed / =x). #38-adjacent: rejected "richmond.ca IL" = Richmond BC Canada.
- **Martinez** (`_apply_martinez_ca.py`): self-storage named ONLY in **CC Central Commercial** (conditional,
  §22.16.080.K.10) + M-combining districts that include CC. **H-I (81 in-ring) + L-I (22 in-ring) are
  li-armed NO-OPs, NOT self-storage needles** — warehouse is CUP-only (§22.18.060.K, conditional-warehouse →
  no convention) and self-storage is confined to CC. SC warehouse-by-right but self-storage confined to CC →
  prohibited. Honest correction to the expected "H-I/L-I 81/22 needles".

## HANDED BACK — East County / West County cities are NOT sub-$475k no-ops (need per-city research)
Ring-HV check REFUTES the sub-$475k hypothesis — all clear the gate (median ring-HV):
  Oakley $610k (812 wealth+1.5ac), Antioch $564k (495), Pittsburg $520k (145), Pinole $660k (194),
  Hercules $652k (214). These have in-ring industrial and need per-city ordinance research (own code systems:
  Oakley M-H/LI/SP-#, Antioch P-D/S-P/C-2/C-3/WSCD, Pittsburg IG/GQ, Pinole CMU/OIMU/OPMU/H-I, Hercules
  P/QP/PC-R/CC/CG). **NOT no-ops — follow-up batch.** Residential-wealth no-ops (thin/no industrial):
  Lafayette/Orinda/Danville/San Ramon (per batch-1). San Pablo/El Cerrito small + descriptive-code cities.

## TRACK 2 — Nassau NY [c72002c7-1f3e-48e4-be98-04e420776fdb]: NO spatial zoning layer — PASTE-SPEC
Municipality bind + ring are done, but **no verified NY zoning POLYGON layer exists** for Oyster Bay / North
Hempstead / Hempstead (all publish only PDF Building Zone Maps + parcels-without-zoning).
**#38 CONFIRMED:** the "City of Hempstead Zoning App" (services9.arcgis.com/CpGrZZm3P1y5qJHh/.../Zoning_view)
is **Hempstead, TEXAS** (SR wkid 2278 Texas State Plane; geom lon -96.08/lat 30.08; "ETJ" Texas-only field). REJECTED.
Real NY sources found: Town of Hempstead `ToH_Zoning_Maps` FeatureServer (services6.arcgis.com/bqUwpAFaDo5lm9eK)
= a PDF map-sheet INDEX grid (fields IndexNo/FileName/Location, NO zone code) — unusable. North Hempstead /
Oyster Bay / Nassau County ArcGIS = parcels + boundaries only, no zoning attribute.
**PASTE-SPEC to bind Nassau (pick one per town):**
  (1) **Ordinance use-tables** (already text-fetchable, no paste needed): Oyster Bay eCode360 (Ch.246 §246-5.2;
      client guid 26884554), Hempstead eCode360 14495788, North Hempstead ordinance. These give the per-district
      self-storage/warehouse verdicts.
  (2) **Parcel→zone binding** (the missing piece) — one of:
      (a) a **town-provided parcel-zoning export** (CSV/shapefile with parcel ID [Section-Block-Lot] + zone code), OR
      (b) **georeference/digitize the town PDF Building Zone Maps** (oysterbaytown.com/wp-content/uploads/Zone-Maps-all.pdf;
          hempsteadny.gov/548/Town-Map; northhempsteadny.gov zoning_maps) into zone polygons, then centroid spatial-join.
  Export format needed for bind: `{apn/SBL, zone_code}` keyed to Nassau parcels' NCID/Section-Block-Lot. PARK until a
  town furnishes parcel-zoning or the maps are digitized (like Hinsdale).

## TRACK 2 — Bloomfield Twp MI [15ecf7aa]: NOT a no-op, but blocked on source
Expected all-residential no-op is WRONG — Bloomfield Twp has an **ML Light Manufacturing** district (§42-3.1.12,
"warehousing and wholesale establishments" by-right → self-storage conditional convention; self-storage
acknowledged in §42-5 parking). BUT **no zoning spatial layer exists** (Oakland County GIS + township portal
publish only Current Land Use + a PDF zoning map; MI-verified, #38 mapxpress look-alike rejected). ML footprint
small (~5-6 labels near Telegraph/Wagner). **Blocked on Stage-1 binding** — needs PDF-digitize or assessor-code
rebind. Small potential needle; park with Nassau pattern.
