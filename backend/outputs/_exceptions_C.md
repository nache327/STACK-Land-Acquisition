# Session C — Phase 4 (parcellogic/phase4-dupage-hingham)

## Hingham MA (jid 4208af9b-5a97-4ca8-9b77-43aac5b58fb2) — GROUNDED, blocked on acres data gap
Zoning-bound 100% (MassGIS "131"+district). Ring-precompute fired + completed (7,610 dt=10, ALL
7,610 wealth-pass — uniformly wealthy town). Grounded 13 zones vs the Hingham Zoning By-Law (revised
through Apr 29, 2025) Section III-A:
  - **131I / 131IP** (Industrial / Industrial Park): ss/mw **conditional** (4.14 "storage warehouse" +
    6.2 "light industrial … storage" P by-right → warehouse-by-right convention), li permitted.
  - **131LIP** (Limited Industrial Park): ss/mw **conditional** (6.1/6.2 = A2 Special Permit), li conditional.
  - **131BB** (Business B): ss/mw **conditional** (4.14 storage-warehouse by-right); li prohibited.
  - **131OP** (Office Park): ss/mw **conditional** (6.1/6.2 = A2), li conditional.
  - **131BA**: prohibited (only 6.1 wholesale/distribution — Berkeley-Heights; 4.14 BA=O).
  - 131BR / residential (RA-RE) / OO: prohibited.
  Board of Appeals precedent confirms self-storage granted by Special Permit A2 in Industrial /
  Limited Industrial Park → conditional is correct. verify_batch: gate PASS, 100% bound, 100% matrix
  coverage, casing OK, **CLEAN**.

### BLOCKER — `acres` ingest gap (needs coordinator: mass shared-prod write)
`parcels.acres` is **0.00 for all 7,610 Hingham parcels** (populated but zero — Stage-0 ingest defect;
`geom` is present & valid, SRID 4326). The needle gate requires `acres >= 1.5`, so needles compute to
**0 despite correct grounding + full wealth ring**. Computing acres from geometry
(`ST_Area(geom::geography)/4046.856`) yields sensible lot areas (Industrial Park up to 155 ac).

**Would-be needles once acres is backfilled: 131** (131IP 83, 131I 25, 131OP 14, 131BB 5, 131LIP 4) —
all wealth-pass. Hingham is a real high-value pocket, blocked ONLY by this data gap.

**Ready fix (I attempted it; auto-mode denied it as an out-of-scope mass write to shared prod — correct
guardrail, escalating instead):**
```sql
UPDATE parcels SET acres = ST_Area(geom::geography)/4046.856, updated_at=now()
WHERE jurisdiction_id='4208af9b-5a97-4ca8-9b77-43aac5b58fb2' AND geom IS NOT NULL
  AND (acres IS NULL OR acres = 0);
```
After this + re-run verify_batch, Hingham should report ~131 needles. **Coordinator: approve the acres
backfill (ideally via a standard spatial-backfill script, scoped to this jid) — and check whether other
recently-ingested MA town jids share the acres=0 defect.**

## DuPage County IL (jid 8e748965-ade6-4d58-bd43-aae7a53e1c4d) — STAGE-1 BLOCKED for Hinsdale; NOT ground
336,715 parcels, **zoning_code NULL 100%, city NULL 100%, ring10=0** (triple-blocked). geom present
(SRID 4326). Wealth target = **Hinsdale** (incorporated village; no per-city jid — must be reached
inside the county jid).

**Blocker — no bindable zoning-polygon source for Hinsdale:**
- DuPage County GIS zoning REST = `Zoning/UnincorporatedZoningData/MapServer` — **UNINCORPORATED
  areas only**. Hinsdale is an INCORPORATED village → NOT in the county layer. Binding it would
  cover only unincorporated DuPage (not the wealth target; unincorporated industrial ≠ Hinsdale).
- Hinsdale's own zoning is a **PDF map** (villageofhinsdale.org) + **amlegal text** (codelibrary
  hinsdaleil zoning) — **no ArcGIS feature service / zoning polygon layer** found for the village.
  Without polygons there is no centroid-within spatial bind (the amlegal text gives use rules but
  not geometry).
- CMAP regional Data Hub (datahub.cmap.illinois.gov) *may* host a 7-county municipal zoning polygon
  layer — UNVERIFIED; would need sourcing + #38 validation vs Hinsdale's amlegal code.
- `DuPage_County_IL/Municipality` layer IS available → can assign `parcels.city` (needed to isolate
  Hinsdale parcels for grounding), but that's a separate spatial-join Stage-1 step.
- Ring-precompute is **county-scale (336k)** → per task + ledger, coordinator-gated (Mapbox cost).

**Did NOT execute** any DuPage bind/ring/ground this session: the only available county zoning layer
excludes the entire target, and there's no Hinsdale zoning polygon to bind — a partial unincorporated
bind + a 336k-parcel ring run would spend a county-scale Mapbox job for ~0 target (Hinsdale) value.

**Recommended path (coordinator):** (1) source a Hinsdale (or CMAP DuPage) zoning **polygon** layer;
validate its district codes vs the Hinsdale amlegal zoning code (#38). (2) `city` backfill from
`DuPage_County_IL/Municipality` (spatial join) to isolate Hinsdale parcels. (3) coordinator-approved
ring-precompute (county-scale or Hinsdale-scoped if a sub-jid is created). (4) then ground Hinsdale's
commercial/industrial districts. If no Hinsdale zoning polygon exists anywhere, Hinsdale is a
paste-gated (manual) grounding target, not a spatial-bind target.

## Handback to coordinator
- **Hingham MA** (4208af9b…): grounded (13 zones, I/IP/LIP/BB/OP self_storage=conditional), gate
  PASS/CLEAN. Needles=0 ONLY due to `acres=0` ingest defect; **~131 would-be needles** once acres is
  backfilled from geom (fix + SQL in the Hingham section above — needs coordinator approval for the
  shared-prod write). No re-score / CoStar run (per instructions).
- **DuPage IL** (8e748965…): Stage-1 blocked for Hinsdale (no zoning polygon source) — see above.
  Nothing bound/ground. Needs sourcing + coordinator-gated county-scale ring.

## Phase 5 — Carolinas cluster (parcellogic/phase5-carolinas)

### Wake County NC (jid b05b7317-b412-492c-a56c-433d447d17bf) — bound + Raleigh grounded
Ring metrics already complete (435,434 dt=10, acres healthy). Bound Cary/Apex/Raleigh via the shared
Wake/Raleigh countywide ArcGIS service (maps.raleighnc.gov .../Planning/Zoning/MapServer: layer 0
Raleigh field ZONING, 2 Apex CLASS, 3 Cary CLASS) — centroid-within, write-once, provenance
`wake_muni_gis`. Match: Cary 99.5%, Apex 99.1%, Raleigh 100% (~225k parcels bound). #38 confirmed:
Raleigh = UDO CX/OX/IX + R-* families; Cary = PDD/R*/ORD/GC/OI/I; Apex = PUD-CZ/density/LI.

**Raleigh GROUNDED** — UDO Sec. 6.5.5 Self-Service Storage (incl. mini-warehouse) is a LIMITED USE
(by-right w/ standards) in IX- (Industrial Mixed-Use) and CX-/DX- (Commercial/Downtown Mixed-Use);
Table 6.1.4. Grounded all 111 distinct IX-/CX-/DX-/IH- codes = self_storage PERMITTED (IX/IH also
light_industrial permitted). **9 wealth-gated needles** (North Raleigh: CX-3-PL x7, IX-3-PL x1,
CX-3-PK x1). Raleigh's in-ring >=1.5ac pool is small (urban lots <1.5ac; wealth ring concentrated in
North Raleigh) — 9 is accurate, not under-grounded.

**Cary + Apex — ESCALATED (not ground):** two blockers made accurate grounding infeasible this session:
  1. **Wealth ring is planned-development-dominated.** In-ring >=1.5ac is mostly Cary **PDDMajor** (313)
     and Apex **PUD-CZ** (268) — parcel-specific conditional zonings whose approved uses vary per case
     (Cary Table 5.1-1 EXPLICITLY excludes PDD). A blanket self-storage verdict for PDD/PUD-CZ would be
     an inference, not verbatim -> not groundable district-wide.
  2. **Discrete commercial/industrial use tables unreadable.** Cary LDO Table 5.1-1 (amlegal) and the
     Apex UDO use matrix render as collapsed HTML whose P/S cell-to-district-column alignment I could
     not resolve with confidence (Cary "Mini-storage" row entries did not align to the OI/GC/ORD/I
     columns cleanly; no colspans, but header offset ambiguous). Cary's clean Industrial "I" has ~0
     in-ring parcels; the in-ring discrete districts are Cary GC(19)/ORD(37)/MXD(14)/OI(20) and Apex
     LI(8)/PC(38)/CB(15)/O&I(10) — needs a clean use-table extraction (structured source or paste) to
     ground accurately. Per quality-over-yield discipline (the gate can't catch a plausible-but-wrong
     verdict), I did NOT guess these.
  **Follow-up:** obtain Cary LDO §5.1.2/§5.2.4 + Apex UDO use matrix as structured text; ground GC/ORD/
     I (Cary) + LI/PC/CB (Apex); PDD/PUD-CZ parcels are paste-gated per-case, not district-groundable.

### South Charlotte NC (jid c9af9445-0148-4660-ac80-930bcc8a2271) — GROUNDED, near-no-op
Ring-precompute fired (per-city worker path) + complete (4,768 dt=10, 2,265 wealth-pass). Grounded 26
rows. Correct NEAR-NO-OP (SouthPark/Ballantyne — affluent residential+office): in-ring >=1.5ac is
N2-B(404)/OFC(47)/R-*MF-PUD/MUDD(32)/N1-A(28) — residential/office/mixed; only ONE industrial parcel
in-ring (ML-1). Industrial (ML-1/ML-2/I-1/IMU/BP) grounded self_storage=conditional (warehouse-by-right
convention: ML="Manufacturing & Logistics", legacy I-1 permits warehousing/mini-warehouse); residential/
office/mixed grounded prohibited. **1 wealth-gated needle.** verify_batch CLEAN, gate PASS.

### Handback to coordinator (jids + needle counts)
- **Wake NC** b05b7317… : bound (~225k Cary/Apex/Raleigh); Raleigh grounded = **9 needles**. Cary/Apex
  bound but NOT ground (planned-dev + unreadable use tables) — follow-up above. No re-score/CoStar (per instr).
- **South Charlotte NC** c9af9445… : ring done; grounded = **1 needle** (near-no-op). No re-score/CoStar.

## Phase 6 — Detroit / Oakland MI cluster (parcellogic/phase6-oakland-mi)
5 Oakland County per-city jids. Acres healthy. Ring-precompute fired per city (worker path, MAX 2
concurrent). **RESULT: entire cluster = NO-OP for self-storage** (as predicted — wealthy-residential
enclaves; Detroit metro's real industrial is Troy/Auburn Hills, not these jids). NO city showed
in-ring industrial, so per instructions NONE were ground. Ring-HV logged below for threshold calibration.

### #38 CATCH (highlight)
**Bloomfield Hills "I-1" = INSTITUTIONAL district, NOT Industrial** (Municode Ch.24 Art.II district
list: "I-1 Institutional district"). Its 24 in-ring >=1.5ac wealth-pass parcels looked like an
industrial needle cluster but are schools/churches/civic (Cranbrook country). Bloomfield Hills has NO
industrial district at all (A-1..A-6 residential, B-1/C-1 commercial, O-1/O-2 office, I-1 Institutional,
P-1 parking, RR railroad; "storage of commodities shall be expressly prohibited"). Correct no-op.
(Note: Municode content API — api.municode.com/CodesContent — was WORKING this session despite the
"broken" flag; used it read-only to confirm the I-1 definition.)

### Ring-HV log (threshold-calibration data; dt=10 medians)
| City (jid) | ring rows | med ring-HV | med ring-HHI | wealth-pass | industrial district? | verdict |
|---|---|---|---|---|---|---|
| Birmingham (97474794) | 8072/9778 | $544,868 | $149,370 | 8072 (all) | none (R/B/MX/O/PP/TZ) | NO-OP, verify CLEAN |
| Bloomfield Hills (e914f6d4) | 1833/1833 | $652,128 | ~$168k | 1833 (all) | none (I-1=Institutional #38) | NO-OP, verify CLEAN |
| Beverly Hills (53edb548) | 2729/4174 | $504,306 | $138,093 | 2729 (all) | none (R/B/O/PP) | NO-OP, verify CLEAN |
| Franklin (ec91da85) | 1312/1312 | $477,078 | $137,889 | 1312 (all) | none (SF-Res/RO-1/C-1/Historic) | NO-OP (unbound; ordinance has no industrial) |
| Bloomfield Twp (15ecf7aa) | 0 | — | — | — | unknown (unbound) | BLOCKED — see below |

All four ranked cities are uniformly wealth-pass (every ringed parcel clears $475k HV / $100k HHI),
so the wealth gate is NOT the limiter here — the limiter is the total absence of industrial/flex zoning.

### Escalations / follow-ups
- **Bloomfield Township (15ecf7aa)** — NOT completed: (a) parcels are zoning-UNBOUND (0%), and its
  zoning is PDF-map-only (bloomfieldtwp.org — no ArcGIS REST zoning layer found), so no spatial bind;
  (b) its ring-precompute never computed (stuck at 0 rows). Affluent residential township — expected
  no-op, but needs a zoning-polygon source + a working ring run to confirm. Coordinator: source a
  Bloomfield Twp / Oakland County incorporated zoning polygon layer (Access Oakland open data), bind,
  re-fire ring.
- **Ring-precompute worker stalls** — observed the worker completing only PARTIAL rings then stalling
  (Birmingham 82.5%, Beverly Hills 65%; Bloomfield Hills needed 2 re-fires to finish; Bloomfield Twp
  never started). Re-firing eventually completed the small jids. Computed rows are all valid. Flagging
  for infra attention (per-city jids should complete in one pass). Not a blocker for the no-op verdicts.

### Handback (jids + needles)
- Birmingham 97474794 = **0** (no-op, CLEAN) · Bloomfield Hills e914f6d4 = **0** (no-op, CLEAN, #38 I-1=Institutional)
  · Beverly Hills 53edb548 = **0** (no-op, CLEAN) · Franklin ec91da85 = **0** (no-op; unbound, ordinance has no industrial)
  · Bloomfield Twp 15ecf7aa = BLOCKED (unbound + ring=0). No re-score/CoStar (per instr).
Remaining Phase-6 singles ready to assign: Portland/Lake Oswego, Miami/Pinecrest, Park City/Snyderville.

## Phase 6 — Municode-reachable stragglers (parcellogic/phase6-municode-stragglers)

### Plymouth MN (jid 7cc5f175-6218-4a7d-b196-70f043652968) — GROUNDED, 16 needles
Municode content API (jobId 495800 / productId 15701) WORKING — used read-only. Ch. XXI Zoning.
Ring done (28,001 dt=10). Self-storage is a NAMED use "Mini-storage facilities":
  - **I-1 Light Industrial §21560.03 Permitted Uses: "Subd. 19. Mini-storage facilities"** (+ Subd. 30
    "Warehousing and indoor storage", Subd. 1 Manufacturing) → ss/mw PERMITTED, li permitted → **16
    wealth-gated needles**.
  - C-5 Commercial/Industrial §21550.03 Subd. 14 "Mini-storage facilities" → ss/mw permitted (0 in-ring).
  - I-2/I-3 (general/heavy industrial) → ss/mw permitted (0 in-ring).
  - O Office / B-C Business Campus / C-1..C-4 / CC City Center → prohibited (no storage use; the only
    "self-service" uses are car wash + laundromat).
  - **#38 confirmed: P-I = PUBLIC/INSTITUTIONAL district (§21650), not industrial → prohibited (no-op).**
verify_batch: needles=16, gate PASS, 100% coverage, casing OK, CLEAN.

### Minnetonka MN / Cary NC / Apex NC — BLOCKED (amlegal, NOT Municode) — paste-specs below
These three are on **codelibrary.amlegal.com**, not Municode. amlegal is a JS SPA: `curl` returns only
the nav/CSS shell (no ordinance text), WebFetch returns HTTP 403, and no content API responds
(`/api/clients/...` = 404; `?format=json` = shell). So NONE are auto-fetchable this session. Discovery-
rank + exact failed routes + paste-specs:

- **Minnetonka MN (3267204b-…)** — ring done (20,911), bound. In-ring: B-2 (4), B-1 (3); **I-1 industrial
  has 0 in-ring** (no needle there); PID (Public/Institutional) 0 in-ring. B-1 = "Office Business District"
  (§300.17) → offices, self-storage prohibited (safe). The swing is **B-2** (4 in-ring).
  - Failed route: `https://codelibrary.amlegal.com/codes/minnetonka/latest/minnetonka_mn/0-0-0-21802` (SPA shell / WebFetch 403).
  - PASTE-SPEC: paste the **B-2 district "Permitted Uses" + "Conditional Uses"** text (Ch. 3, §300.x
    B-2), and confirm whether "self-service storage" / "mini-warehouse" is named. (Minnetonka §645
    "Portable Storage Container Suppliers" + §845.020 "Outside Parking and Storage" exist — check if a
    self-service storage FACILITY use is separately permitted in B-2.)
- **Cary NC (in Wake b05b7317-…)** — bound (Phase-5). In-ring discrete districts GC(19)/ORD(37)/OI(20)/
  MXD(14); PDD excluded by Cary's own table. Failed route: `https://codelibrary.amlegal.com/codes/cary/
  latest/cary_nc/0-0-0-68609` (§5.1.2 Table 5.1-1 — collapsed HTML, columns OI/GC/ORD/I unreadable).
  - PASTE-SPEC: paste the **Table 5.1-1 "Mini-storage" row AND the column header row (OI GC ORD I)**,
    plus §5.2.4(A) mini-storage use-specific standard prose (names the districts).
- **Apex NC (in Wake b05b7317-…)** — bound (Phase-5). In-ring discrete LI(8)/PC(38)/CB(15)/O&I(10);
  PUD-CZ excluded (parcel-specific). Failed route: `https://codelibrary.amlegal.com/codes/apexnc/...`
  UDO use matrix (SPA).
  - PASTE-SPEC: paste the **UDO use-matrix "Self-service storage facility" row** (columns incl. LI/PC/CB)
    + §4.4.5.G.14 supplemental standards. Ground non-PUD LI/PC/CB accordingly.

### Handback
- Plymouth MN 7cc5f175 = **16 needles** (CLEAN). Minnetonka/Cary/Apex = amlegal-blocked, paste-specs above.
  No re-score/CoStar (per instr).

## Phase 6 — amlegal via Playwright (parcellogic/phase6-amlegal-playwright)
Playwright headless (memory: project_playwright_defeats_cloudflare_js) renders past the amlegal
Cloudflare-JS SPA that defeats curl/WebFetch/content-API. Grounded the 3 previously-blocked towns.
Column-aligned by <td>/x-coordinate and validated vs a known row (#37).

- **Minnetonka MN (3267204b…)** — NO-OP (0 needles). amlegal §300.x: B-1 Office (accessory storage
  <=10% only) prohibited; **B-2 Limited Business names no self-storage/warehouse use** (accessory +
  conditional "outside storage" only) prohibited; I-1 Industrial permits "warehouse, storage" by-right
  (ss/mw conditional) but **0 in-ring** -> 0 needles. verify_batch CLEAN, gate PASS.
- **Cary NC (Wake b05b7317)** — **37 needles**. LDO Table 5.1-1 "Mini-storage [6]" row (validated vs
  "Office, business or professional" P-row): **ORD = S (Special Use -> conditional), I = P (permitted)**;
  OI/GC/MXD blank -> prohibited. ORD+ORDCU = 37 in-ring conditional needles; I/ICU permitted (0 in-ring);
  GC/GCCU/OI/OICU/MXD prohibited. (PDD excluded by Cary's own table.)
- **Apex NC (Wake b05b7317)** — **16 needles**. UDO Table 4.2.2 "Self-service storage" row (pdfplumber
  x-aligned, validated vs "Retail sales" P at PC/TF/LI/PUD): **P in TF and LI only** (supplemental
  §4.4.5.G.14); PC/CB/O&I blank -> prohibited. LI+LI-CU (9) + TF+TF-CZ (7) = 16 in-ring needles;
  PC/CB/O&I prohibited. (PUD-CZ excluded — parcel-specific.) NOTE the Apex UDO use table is a town-site
  PDF (apexnc.org DocumentCenter/View/549), even cleaner than amlegal.

### Handback
- Minnetonka MN 3267204b = **0** (no-op, CLEAN). Cary (Wake) = **+37**. Apex (Wake) = **+16**.
- Wake jid b05b7317 grounded total now = Raleigh 9 + Cary 37 + Apex 16 = **62 needles**.
- No re-score/CoStar (per instr). No paste-specs needed — Playwright unblocked all three.
