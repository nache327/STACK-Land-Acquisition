# Session A exceptions / discovery notes (cumulative)

# ================= ESSEX COUNTY NJ (jid 67541a18…) — STAGE-1 UNBLOCKED via NJTPA Atlas (2026-07-14) =================

## ✅ RESOLVED — the Stage-1 block below is FIXED. Essex parcels are now 99.81% zone-bound.
**Source = NJTPA Zoning Atlas 082025** (`https://gis.njtpa.org/server/rest/services/LandUse/NJTPA_Zoning_Atlas_082025/MapServer/0`)
— a NEW region-wide polygon layer (all 13 NJTPA counties in ONE layer + a `County` filter), superseding the
per-county `NJTPA_Zoning` FeatureServer layers in zoning_ingestion.py (which have NO Essex). Fields: `County`
| `Jurisdic_1` (town) | `Abbreviate` (=code) | `Full_District_Name`. Bound via
`scripts/_bind_essex_njtpa_atlas.py` (curl-fetch — Cloudflare 403s httpx but passes curl+UA; geopandas
centroid-`within` sjoin; replace=false so Newark's codes preserved; provenance `njtpa_atlas_082025`).

- **bound_pct: 175,603/175,932 = 99.81%** (was 23.8% / Newark-only). Wealthy towns: Millburn 99.9%,
  Livingston 99.4%, Fairfield 96.3%, Montclair/Verona/West Caldwell/Roseland/Essex Fells 100%, West
  Orange/North Caldwell 99.9%. Dry-run centroid-within match = 99.8% (CRS clean, EPSG:4326 both sides).
- #38 spot-check PASS: codes match ordinances (Livingston I=Limited Industrial, CI=Commercial Industrial;
  Fairfield L-1/L-2/L-3=Light Industrial, C-3=Commercial-Industrial, H-D=Rt-46 Highway Development).
- **Template for Union/Passaic/Hudson**: same Atlas covers Union (2,464 polygons/21 munis), Passaic
  (7,243/16), Hudson (2,495/12). Re-run the script with their jid + `where=County='<X>'`. Opens ~140k
  wealth-pass parcels.

## DISTRIBUTION (post-bind) — Essex is a Morris-PLUS profile → GROUNDING-WORTHY, not a Hudson no-op.
Wealth-ring (dt10 HV≥475k, HHI≥100k) AND acres≥1.5 lots that land in REAL industrial / commercial-industrial
districts (the grounding-worthy pool; residential/park/open-space excluded):
- **Fairfield township = the headline** (~HV 697k): **L-1=150, H-D=90, L-2=40, L-3=15, C-3=8, C-2=5, O-P=4,
  C-1=3 → ~315 wealth-ring industrial/CI lots**. 564 of its 660 wealth-ring lots are NON-residential. The
  county's industrial hub (Rt-46 corridor). Bigger industrial base than any single Morris wealth town.
- **West Caldwell township** (~HV 651k): **M-1=57, M-2=21** (+ OP office 14, B-3 11) → ~78. 112/143
  non-residential. ⚠️#38 at grounding: confirm M-1/M-2 = Manufacturing (likely) NOT Multifamily (Tarrytown trap).
- **Livingston township** (~HV 850k — very wealthy): **CI=27, I=11, R-L2=8, R-L=7, B-2=4, B-1=3 → ~60**.
  ⚠️#38: R-L/R-L2 = Research Laboratory (industrial-ish), NOT residential despite the R- prefix. Bulk (700)
  is residential (R-5A/R-5B adult/senior + R-1/2/3).
- **Millburn township** (Short Hills, ~HV 764k): **C=30, CMO=9 → ~39** commercial.
- **Roseland borough** (~HV 586k): C=13, CR=10, OB-3=9 → ~32 commercial/office (weaker).
- **Montclair** (~HV 530k): C-1=5, C-2=3 → ~8 (mostly residential 332/402 — dense downtown, modest industrial).
- **West Orange / Verona / North Caldwell / Essex Fells**: wealth-ring pools are predominantly
  residential + P(park)/OS-REC(open space)/AH(adult housing)/A-C(agricultural-conservation) — NOT
  self-storage-eligible. Likely correct no-ops (verify at grounding).

**Recommendation: GO on a grounding batch, led by Fairfield (L-1/L-2/L-3/H-D/C-3), then West Caldwell
(M-1/M-2), Livingston (CI/I/R-L), Millburn (C).** ~500+ wealth-ring industrial/CI lots concentrated across
4 towns. Data caveat: `acres` is genuine acres (verified vs geom-derived), but a few corrupted-geometry
parcels inflate acres (max 94,018 impossible; county median 0.13ac) — rare outliers, don't change the picture.
HELD per scope: no zone_use_matrix writes, no ordinance reads, no re-score — awaiting coordinator grounding scope.

---
### (historical) The original block, now fixed by the above:

**Essex was NOT groundable as a matrix batch — the parcels were not zone-bound.**
The session was scoped as "NJ name-bound → no rebind, ground top 3-4 towns." That assumption (true for
Morris, where 177,464/177,532 parcels arrived with a `zoning_code` from the source pull) is **FALSE for
Essex**. Diagnosis below is verify-before-declare (#42) — all counts are live queries, not inference.

## The block (verified)
- **Only Newark is zone-bound**: 41,957 / 175,932 Essex parcels have a non-NULL `zoning_code`, and ~all
  are Newark (R-3/C-2/RDV/MX-1/EWR-airport/PORT). Every wealthy target town has **zoning_code = NULL,
  assessor_zoning_code = NULL, zone_binding_method = NULL** for 100% of its parcels.
- **Newark's wealth ring fails** (urban) → its 873 bound ≥1.5ac lots yield **0 wealth-gated needles** =
  correct no-op. So the one bound town is a no-op and the towns with real needle potential are all unbound.
- **`zoning_districts` geometry is Newark-only**: 2,966 rows (source='arcgis', raw_attributes `"City":
  "Newark"`). A centroid spatial-bind test (`ST_Within(ST_Centroid(p.geom), zd.geom)`) returns **0
  bindable parcels** for every wealthy town — no district polygon covers them.
- **`zone_use_matrix`**: 0 human_reviewed rows for Essex. verify_batch → **needles=0**, gate PASS (nothing
  poisonous), warn "only 23.8% of parcels have a zoning_code".

## Wealth-eligible potential being left on the table (acres≥1.5 + dt10 HV≥475k + HHI≥100k)
Livingston 794 · Fairfield 716 · Montclair 402 · Millburn 168 · West Caldwell 143 · Verona 106 ·
West Orange 92 · North Caldwell 90 · Roseland 81 · Essex Fells 64 · Bloomfield 27 · Maplewood 25.
These are large — Fairfield + Livingston alone rival a whole grounded county — but **unreachable until the
parcel→zone link exists**. Grounding an ordinance matrix now produces 0 needles (nothing to join on).

## Why the fetch-first playbook doesn't unblock it here
`zoning_sources` for Essex (NJDCA directory, 20 rows) gives the wealthy towns only `pdf_map` +
`ordinance` (eCode360) — **no `shapefile_url`, no `zoning_endpoint` FeatureServer**. Bounded probe done:
Fairfield's public ArcGIS app is FEMA-flood only; the consultant org hosting it (services6/UcuMPLF9IlsigGHI)
carries Paramus/Westwood (Bergen) zoning but **not** Fairfield/Livingston/etc. The top targets publish
zoning as **PDF maps only**. So the ordinances give use tables but nothing binds a parcel to a district.

## Unblock path (Stage-1 infra — coordinator decision; this is the Braintree/Hudson-parked town-GIS pattern)
Per target town: (1) locate a zoning **polygon** source — town/county ArcGIS FeatureServer with a Zone
field, OR a georeferenced shapefile (NJGIN/Rutgers njmaps host NJ *parcels* but not municipal *zoning*
polygons); (2) ingest into `zoning_districts`; (3) spatial centroid-bind → populate `parcels.zoning_code`
(#38: verify layer codes+geometry vs the CURRENT ordinance); (4) THEN ground the eCode360 use table +
apply the NJ self-storage catch (global closed-list clause OR named-district confinement beats the
warehouse convention — the Boonton rule). Ordinance URLs already captured in `zoning_sources`
(Fairfield ecode360.com/35314662, Livingston attachment LI1238, etc.).

**Recommendation:** do NOT ground Essex ordinances into the matrix yet (would create human rows that
score 0 and give a false "grounded" signal). Either (a) fund the per-town zoning-polygon acquisition as a
Stage-1 task, or (b) pivot this session to a county whose parcels arrived pre-bound. No matrix writes were
made; no re-score run. Discovery scripts left uncommitted/removed.

# ================= MORRIS COUNTY NJ (jid 746b7604…) — batchA1 (2026-07-14, shared w/ D) =================
Partition: D = discovery ranks 1-4 (Kinnelon/Randolph/Boonton township/Long Hill); A = ranks 5-8
(Morristown/Chatham township/Boonton town/Mountain Lakes). NJ name-bound → NO rebind. SKIP re-score
(coordinator runs ONE reconciling Morris re-score after A+D merge).

## GROUNDED — Morris NJ batchA1
| Muni | Result |
|---|---|
| **Boonton town** | GROUNDED **NEEDLE = C-1** (eCode360 BO1912 Ch.300, print?guid=7162402). §300-110 A(18)(d) "Self-storage facilities" by-right in **C-1 (Hybrid Commercial/Industrial)** ONLY (added 9-16-2024 Ord.19-24). NJ CATCH: the same ordinance amended I-1 (§300-111) but did NOT add self-storage there; global closed-list §300-83 ("use not specifically permitted... is prohibited") ⇒ warehouse-by-right in I-1 does NOT ground ss. So I-1's 27 wealth-ring lots = **li-armed only** (manufacturing + warehouses by-right), NOT ss needles. C-2 (Gateway) = shared commercial uses only, no ss. Distinct from D's 'Boonton township' (#38). |
| **Mountain Lakes borough** | GROUNDED **NEEDLE = B (Business Zone B)** (eCode360 MO1514 Ch.245, print?guid=8632797). §245-78 C(4) self-storage **conditional** in Business Zone B (§245-112). #38 CATCH: parcel "C-1"/"C-2" = **CONSERVATION Zones** (§245-81, recreational only) NOT commercial → the 26+8 wealth-ring "C" lots are prohibited (false signal). "A"/"B" = Business Zone A/B; "OL-1"/"OL-2" = Office & Light Industrial (§245-79 A(2) light mfg/storing/fabrication by-right → **li-armed**, ss not named there so prohibited). "RC-*" = Residential Clustering. |

## DEFERRED — code-mismatch, 0 self-storage needle under current law
| Muni | Reason |
|---|---|
| **Morristown town** (rank 5) | Feb-2024 form-based LDO (eCode360 MO0747 Ch.30) renamed ALL districts to R/E/MF-1/MF-2/PWN/**CI**/MX — but parcels still carry PRE-2024 codes (RC/RDZ/OB-1/OB-2/CBD-1/CBD-2/B/M1/PPU/TVC/ORC...). **Self-storage/warehouse is NOT a named use anywhere in the current LDO** (searched Article 2E + Part 2 District Standards, 260k chars, use tables Key P/NP/C) → 0 self-storage needles town-wide regardless of code mapping. Low ceiling anyway (dense downtown; M1 only 2 wealth-ring lots; PPU=Public/Park). NOT force-grounded: per-district li verdicts would need an old→new (M1→CI etc.) crosswalk — declined to fabricate against a superseded code scheme. Unblock = re-code parcels to the 2024 LDO districts, then ground CI for li. |

# ================= DELAWARE COUNTY PA (jid de8945f7…) — batch1 (2026-07-14) =================

## Discovery
Only 3 un-grounded towns have ANY wealth-ring ≥1.5ac lots (rest have ring_big=0 — the industrial
river-boroughs Eddystone/Marcus Hook/Ridley etc. sit OUTSIDE the wealth ring = correct no-ops):
Radnor (546), Upper Providence (148), Chester Heights (132). PA spatially bound → NO rebind.

## GROUNDED — Delaware PA batch1
| Muni | Result |
|---|---|
| **Radnor Township** | GROUNDED **0-NEEDLE correct no-op** (eCode360 RA0484 Ch.280, full chapter via print?guid=11078356). Wealthy Main Line office/institutional township with NO industrial district and self-storage NOT named. Only standalone by-right warehouse = C-3 Service Commercial §280-55.E "Indoor storage building or warehouse" → ss/mw conditional (convention, self-storage UNNAMED, flagged) — but C-3 has **0 wealth-ring ≥1.5ac lots** → 0 needles. #38: PI=Planned **Institutional** (not Industrial), PLU=Public Land Use, AC=Agricultural-Conservation. CO "storage" = bank security-vault only; C-2 warehouse = accessory-to-retail only. |
| **Chester Heights Borough** | GROUNDED **NEEDLE = MHP only** (eCode360 CH2012 Ch.185, print?guid=12777187). KEY CATCH: self-storage IS named but §185-110.1.A confines it to **conditional use in the Mobile Home Park (MHP) district ONLY** → ss/mw conditional in MHP (2 wealth-ring lots). Named-and-confined ⇒ warehouse convention does NOT override the exclusion in B/LI. **LI §185-81** ("...and no other", closed) = light manufacturing by-right → li permitted (4 ring-big li-armed, NOT ss). **B §185-72** (current, amended 4-21-2025) = retail/office/service + accessory conjunctive storage only → prohibited (the 11 wealth-ring B lots are NOT self-storage needles). |

## CORRECT NO-OP — recorded, not force-grounded
| Muni | Reason |
|---|---|
| **Upper Providence Township (Delaware Co)** | **#38 catch**: TWO Upper Providence Townships in PA. The eCode360 UP1236 / Chapter 300 (node 42975244, uprov-montco.org) is the **Montgomery County** namesake — do NOT use it. The Delaware Co one = eCode360 **UP0461**, Title Six Zoning (node 28525006; confirmed Delaware/Media). It is 98% residential; "Miniwarehouse" (G7) is a defined use but lives in the industrial group, and the **LI Limited Industrial district — the only plausible host — has 0 wealth-ring ≥1.5ac parcels** (discovery). Wealth-ring lots are only B Business (1) + RO Residence-Office (3), which are not self-storage-eligible categories. **0 possible wealth-gated needles** → correct no-op. Not force-grounded (district use-tables live in §§1274-1280 not cleanly captured; declined to fabricate uncited verdicts). Revisit only if a specific blocked deal surfaces. |

# ================= MIDDLESEX COUNTY MA (jid 18a11c2a…) — COMPLETE =================

## OPEN — needs Nache
| Muni | Item | What's needed |
|---|---|---|
| **Newton** | **No auto-fetchable CURRENT source.** Chapter 30 Zoning is only at `newtonma.gov/home/showpublisheddocument/72882/...` — **Akamai-WAF-blocked** (curl → "Access Denied"; WebFetch → 403; no Wayback PDF snapshot; not on Municode/eCode360). Only freely fetchable copy is the **2014 DRAFT rezoning (never adopted)** — DO NOT ground from it (Hudson-class staleness trap). Wealthy, little industrial → likely modest yield. | **Paste** current Ch.30 §4.4.1 Use Table (M/Business/Mixed-Use rows: self-storage/warehouse/manufacturing/motor-vehicle-storage) + legend + closed-list clause. Then rebind (MAPC, muni='Newton') + ground. |
| **Hopkinton** | Identified in tail discovery (IA 27 + IB 7 large-lot wealth-ring parcels; Rt-495 biotech) but NOT yet grounded — deferred for time. Bylaw fetchable (town/eCode360). | Next pickup: fetch Hopkinton use table, check self-storage/warehouse in IA/IB, rebind if needed, ground. Likely a needle. |

## GROUNDED — tail3 batch (2026-07-14) — LAST Middlesex batch (tail drained)
| Muni | Result |
|---|---|
| Wakefield | GROUNDED (eCode360 Ch.190 WA1512, Appendix A Table of Use, curl+UA). **NEEDLE**: "Self-storage facility" (row 7) permitted **by-right** in LI + I; conditional (BA special permit) in B; li permitted LI/I. lgc prohibited (goods self-storage ≠ vehicle garage-condo; closed table). No rebind (parcels carry bylaw codes SSR/SR/GR/NB/LB/B/LI/I). |
| Boxborough | GROUNDED (town PDF View/1918, 2025, Table 4.1.3.d). **NEEDLE**: "Self-storage facility" permitted **by-right in IC** only. MAPC rebind confirmed assessor code **C→IC** spatially (C→IC:62, gates a/b/d PASS, layer vocab = AR/B/B1/IC/OP/R1/TC = bylaw Article 3). li permitted B/B1/OP/IC. lgc prohibited. |
| Pepperell | GROUNDED (town Zoning Bylaw View/2442, consolidated rev. 7/28/2014, Appendix A Table of Principal Uses; MRPC region). **NEEDLE**: "Self-storage facility" permitted **by-right in both C (Commercial) and I (Industrial)**; li permitted C/I. §3100 closed list. No rebind — parcel codes RUR/TNR/SUR/RCR/URR/COM/IND map by NAME to bylaw §2200 abbreviations RR/TR/RCR/SR/UR/C/I (verified against district-establishment list); verdicts keyed on parcel codes (COM→C, IND→I). lgc prohibited. |
| Natick | GROUNDED (CURRENT June-2025 Zoning Bylaws View/19928, Section III-A.1 Table of Use + §III-B..G). **MODEST NEEDLE**: self-storage is NOT a named use (only "self-service laundry" appears) → under §III-A.1.a closed list grounds to K6 "Warehouses for storage of personal property" = SP (conditional) in **INII + HMIa**; DM >1,000 sf SP. Prohibited elsewhere incl. INI (K6 INI=N — INI permits light-mfg by-right but excludes warehouses). li permitted INI/INII/HMIa; conditional CG/HM-II/HM-III/HPU (R&D). HM-II/III/HPU sections name office/R&D/retail but NO warehouse use. lgc prohibited. No rebind (verdicts keyed on parcel codes). |

## GROUNDED — tail2 batch (2026-07-13)
| Muni | Result |
|---|---|
| Hopkinton | GROUNDED (eCode360 Ch.210, §210-9/15 IA/IB permitted uses). NEEDLE: warehousing-for-distribution by-right IA/IB → ss/mw conditional (convention); li permitted IA/IB. |
| Acton | GROUNDED (town PDF §3.6.1 "Warehouse ... a personal self-storage facility or mini-warehouse"). NEEDLE: self-storage IS warehouse, by-right in OP-1/OP-2/PM/GI/LI/LI-1/SM/TD → ss/mw **permitted** there. |

## GROUNDED — tail batch (2026-07-09)
| Muni | Result |
|---|---|
| Lexington | GROUNDED (eCode360 Ch.135 Table 1 via curl+UA attachment). **0-NEEDLE correct no-op**: no self-storage use + closed-list; only mover-storage/distribution by-right (not generic warehouse). li permitted CM/CRO; lgc conditional CS/CSX (named auto-storage SP). NOTE: GC = "Government Civic" (not commercial) — discovery false signal. |
| Ayer | GROUNDED (eCode360 Ch.320 Table via curl+UA; §320-4 confirmed DB=DPSFBC, MT=MUT). Needle: ss/mw conditional (SP) in LI + MUT; li permitted LI/I; **self-storage = N in the heavier Industrial (I)** — confined to LI/MUT. lgc prohibited. No rebind (MRPC town, codes clean). |
| Bedford | GROUNDED (MAPC rebind split assessor IND→IP/I/IC). Needle: no named self-storage but Warehouse by-right in Commercial + Industrial A/B/C → ss/mw conditional (convention); li permitted there. Great Road GB/LB recorded prohibited (Table 4.3-2 not machine-parsed, conservative). Closed-list §2.3. Adopted March 2025 (not the Jan-2025 draft). |

## CORRECT NO-OPS — discovery-ranked but all-residential / no wealth-ring industrial (recorded, not forced)
Wealthy towns whose high large-lot-in-ring count is RESIDENTIAL (single-letter A/B/C/D codes = residence districts), with no real self-storage-eligible industrial in the ring:
- **Carlisle** ("B"=Residence-B, 2-acre residential), **Weston** (A/B/C/D=residence), **Lincoln**, **Sherborn**, **Sudbury**, **Wayland**, **Concord** (mostly AA/A residence; only I(16)+IPA(13) tiny industrial), **Reading** (S20/S15/S40 residential + tiny IND), **Belmont** (dense residential), **Groton/Stow/Dunstable** (rural residential).
These are correct no-ops per the thesis (wealth without self-storage-eligible industrial ≠ gap). Revisit only if a specific blocked deal surfaces.

## MIDDLESEX TAIL DRAINED (2026-07-14)
All industrial/commercial tail towns are now grounded. Remaining un-grounded parcels are either
correct no-ops (all-residential towns, see above) or the two held items:
- **Newton** = OPEN, awaiting Nache paste (Akamai-WAF-blocked current source; only stale 2014 draft freely fetchable).
- **Hudson** = PARKED (stale M-code consolidating recodification; coordinator-ruled — needs town shapefile → spatial rebind).
Middlesex is otherwise COMPLETE — next session pivots to a fresh county.
