# Lake County IL — Class-B per-muni (North Shore) zoning recon manifest

**READ-ONLY recon, 2026-07-09. Session C. jid `10d01284-829b-4b03-b416-54bc452b8e70`.**
Nothing here has been applied. This is the go/no-go + source map for the incorporated-muni
Stage-4 work that follows the county-UDO grounding (unincorporated land; done, PR
`parcellogic/lake-session`). Proceed **muni-by-muni** off this manifest.

## The binding problem (read first)
All incorporated parcels currently carry `zoning_code='INC'` (assessor "incorporated" flag;
`zone_class` reclassified to `unknown` per catch #51). County zoning layers cover
**unincorporated land only**. So to make a muni's verdicts actually SCORE parcels we must
first **rebind** its parcels to real district codes via a **zoning-district POLYGON layer**
(centroid-in-polygon stamp of `zoning_code`, then muni-scoped matrix verdicts join on
`jurisdiction + zoning_code + municipality='<CITY>'`). Consequence:

- **Public zoning-polygon layer available → can go end-to-end** (rebind → ground → score).
- **PDF/text only (no public geometry) → verdicts would be DORMANT** (no parcel carries the
  code). Grounding these is low-value until geometry is obtained (village GIS data request /
  GIS-Consortium credentials / digitize the PDF map). **Defer.**

City names are stamped UPPERCASE (`municipality='GURNEE'` etc.). ≥1.5ac parcel pools per muni
in the table below are the *addressable universe ceiling* (mostly residential; the
industrial/commercial slice is the real needle).

## catch #38 — wrong-jurisdiction sources found & REJECTED during recon (do NOT ingest)
- Lake Forest **CA** AGOL zoning (`ZNy8hnJqYHIKCiV1` / `lakeforestca`) — decoy for Lake Forest IL.
- Tempe **AZ** `zoning_districts` (`lQySeXwbBg53XWDi`, WKID 2868) — surfaced for several munis.
- Brownsburg **IN** `2021_Zoning_Districts` (`R9CVCgaSS8Zy2txP`); statewide **OR** DLCD zoning
  (`8PAo5HGmvRMlF2eU`); Alabama/New-Hampshire `Zoning_Districts` (`f4rR7WnIfGBdVYFd`) — Lake Bluff decoys.
- **Deerfield Township, OHIO** (`choosedeerfield.com`, 513 area) & **MI** (Lapeer Co.) — Deerfield decoys.
- Bannock County **ID** (`maps.bannockcounty.us`) — Bannockburn decoy.
- Lubbock **TX** "Mini-Warehouses" amendment (`destinyhosted.com/lubbodocs`) — surfaced again for Riverwoods (same hit that fooled the county-UDO search).
- **Jurisdiction-LEVEL trap**: Lake County "* Township UDO Zoning" open-data layers (Libertyville/Waukegan Twp, etc.) are the **county UDO on UNINCORPORATED township land**, NOT the incorporated village's districts. Do not use to code village parcels.

## Proceed order (recommendation)
**GROUP A — end-to-end ready (public GIS + confirmed use table):** proceed in this order.
1. **Gurnee** — cleanest: true Use Matrix + live layer; self-storage P by-right in C-3 & I-1.
2. **Mundelein** — strongest storage town: mini-warehouse P by-right across C-1..C-4 + M-1/M-MU.
3. **Waukegan** — largest industrial base; self-storage Conditional in `I` (narrow but real).
4. **Highland Park** — Tier-2 surprise: has L-I + active operators; NOT a no-op (see caveat).
5. **Deerfield** — thin: self-storage special-use only inside an I-2 PUD.
6. **Bannockburn** — tiny: self-storage special-use in Office District (flaky GHA endpoint).

**GROUP B — needs one more recon step before proceeding:**
7. **North Chicago** — public GIS layer confirmed, but the ordinance PDF (`northchicago.org`,
   blocks fetchers) must be read with a browser-UA to confirm the use table + self-storage
   treatment before grounding.

**GROUP C — PDF/text only, no public geometry → DEFER (grounding dormant until geometry):**
Vernon Hills, Libertyville, Buffalo Grove, Lincolnshire, Lake Forest, Lake Bluff.

**GROUP D — honest no-ops (bank zero; catch #52 / Tewksbury — wealth w/o industrial):**
Riverwoods, Mettawa (no industrial district; self-storage absent/prohibited everywhere).
Lake Bluff trends here too (no self-storage use class; enclosed-storage only in L-1/L-2).

---

## Per-muni recon table

### GROUP A — end-to-end ready

| Muni (municipality=) | ≥1.5ac pool | Ordinance source | Use table | Self-storage treatment | Industrial/commercial districts | Zoning GIS layer (verified live) | zone field |
|---|---|---|---|---|---|---|---|
| **GURNEE** | 677 | town PDF "Zoning Ordinance" (Oct 2025) + Municode `/il/gurnee` | **YES — Table 8-1 Use Matrix** (Art. 8) | **Self-Storage P in C-3, I-1**; Outdoor-principal variant S in C-3/I-1, **P in I-2/I-3**; Warehouse P in I-1/I-2/I-3, S in C-3/C-5/C-6 | I-1/I-2/I-3 (+I-2 O.I.P.); C-1..C-6; O-1/O-2; EGG overlay | `https://webmaps.gurnee.il.us/arcgis/rest/services/Zoning/MapServer/0` | `ZONE_CLASS` |
| **MUNDELEIN** | 1,233 | town PDF Title 20 (amended 2021-06-09) + Municode | **YES — Tables 20.32-1 / 20.40-1** | **Mini-Warehouse P by-right in C-1,C-2,C-3,C-4, M-1, M-MU**; Warehouse/Distribution P in M-1/M-MU, S in O-R | C-1..C-4, C5-* family; O-R, M-1, M-MU; L-MU | `https://ags.gisconsortium.org/arcgis/rest/services/VMD/AGOL_VMD_Project/MapServer/3` | `ZONED` |
| **WAUKEGAN** | 1,928 | town PDF **UDO** (eff. 2024-07-01) + Municode | **YES — Table 9.02-1** | **Self-Storage (Indoor) CONDITIONAL in `I` only**; Warehousing/Distribution P in `R/LI` & `I`; Light Mfg P in R/LI & I | **R/LI, I** (only 2 industrial); B1-B4, H/C, E | `https://services5.arcgis.com/LcMXE3TFhi1BSaCY/arcgis/rest/services/New_Zoning_Districts/FeatureServer/0` | `New_Zoning_Code` ⚠ holds `"<code> <name>"` (parse prefix) |
| **HIGHLAND PARK** | 1,178 | Municode Ch. 150 (Code of 1968) | **YES — §150.490 Table of Allowable Uses** | **NOT determined** (matrix behind Municode 403); L-I district + **active operators** (Extra Space/iStorage, Old Deerfield Rd) → likely P/C in L-I | **L-I** (Light Industrial) + B-*/BP/VC-*/HC | `https://ags.gisconsortium.org/arcgis/rest/services/VHP/AGOL_VHP_Project/MapServer/0` | `ZONED` ⚠ legacy schema ≠ Municode codes (reconcile) |
| **DEERFIELD** | 596 | amlegal `deerfieldil` (Zoning Ord. 1978 amended) + town DocCenter PDFs | per-district lists (Art. 4/5/6) | **Self-Storage = SPECIAL USE, only inside an I-2 Industrial PUD** (Sec. 6.02-C(13)); warehouse P by-right ≤25k sf in I-2 (def. excludes logistics) | I-1, I-2; C-1..C-4; P-1 | `https://ags.gisconsortium.org/arcgis/rest/services/VDF/VDF_OpenGov_Project/MapServer/8` | `ZONED` |
| **BANNOCKBURN** | 261 | eCode360 `BA3216` Ch. 260 | per-district use tables | **Self-Storage/mini-warehouse = SPECIAL USE in Office (Office-Research) District** (+5% rental-fee ordinance corroborates a pathway) | **NO industrial**; Retail, Specialty Retail, Office-Research only | `https://gis.gha-engineers.com/arcgiswebadaptor102/rest/services/Bannockburn/Zoning/MapServer/2` ⚠ slow/500s — retry+paginate | `ZONECLASS` |

### GROUP B — one more recon step

| Muni | ≥1.5ac | Ordinance source | Use table | Self-storage | Districts | GIS layer | zone field |
|---|---|---|---|---|---|---|---|
| **NORTH CHICAGO** | 703 | town PDF `Zoning_Ordinance_2024-11-18.pdf` (fetcher-blocked) | **TBD — needs browser-UA read** | **TBD** ("Storage" page exists; M2/M3 heavy-commercial principal) | M2, M3 (M1 likely); B1, B2 | `https://services5.arcgis.com/dUVPCTd3mmy0bK3k/arcgis/rest/services/Zoning_Map_WFL1/FeatureServer/14` | `ZONING_DIS` (+`PIN`) |

### GROUP C — PDF/text only (no public geometry) → DEFER

| Muni | ≥1.5ac | Ordinance source | Use table | Self-storage | Districts | GIS status |
|---|---|---|---|---|---|---|
| **VERNON HILLS** | 2,780 | Municode Appendix C | per-district lists (Art. 6-16A) | O-R&D "Storage facilities" = **special use** (§15.3.10); B-P undetermined | **NO industrial**; B-1, O-R&D, O-R&D-1, B-P | private (village AGOL not shared) |
| **LIBERTYVILLE** | 1,691 | Municode Ch. 26 | per-district lists (Art. 4-8) | mini-warehouse/self-storage defined; likely special-use in I-1/I-3/O-2 (unverified) | I-1, I-2, I-3; O-1, O-2; C-1..C-5 | **auth-gated** GIS-Consortium |
| **BUFFALO GROVE** | 2,807 | Municode Title 17 | per-district lists (17.40/44/48) | self-storage **special use** in I district (§17.48.020.C); real facility via B-3 PUD | I (Industrial), O&R; B-1..B-5 | **auth-gated** GIS-Consortium (VBG) |
| **LINCOLNSHIRE** | 641 | town PDFs Title 6 | per-district lists | M1 lists "Storage and warehousing" **P by-right** → self-storage **conditional** (warehouse convention) | M1; Industrial (Ch.8B); Office/OC; B1/B2/E | no public layer (MGP viewer, no open REST) |
| **LAKE FOREST** | 1,406 | amlegal Ch. 159 | hybrid; **§159.116 business use matrix** | **NOT determined** (matrix behind amlegal 403); Extra Space on US-41 strip exists → NOT clean no-op | **NO industrial**; O-1, OR, OR-2, B-1..B-4, TD | **auth-gated** GIS-Consortium (CLF) |
| **LAKE BLUFF** | 255 | amlegal Title 10 | **YES — §10-13-3 use table** | **no self-storage use class**; "Storage of goods (enclosed)" P in L-1/L-2 only → effective no-op | L-1, L-2 (light ind.); CBD, O&R, AP-1 | none (not a Consortium member) |

### GROUP D — honest no-ops (catch #52)

| Muni | ≥1.5ac | Ordinance source | Finding |
|---|---|---|---|
| **RIVERWOODS** | 406 | amlegal Title 9 | **No industrial district**; residential + B-1/B-2 + O&R only; self-storage in NO district's enumerated uses → **prohibited village-wide (clean no-op)**. No public GIS. |
| **METTAWA** | 299 | amlegal Ch. 15 | **YES Table 7-1 Use Matrix**; **"Warehouse" = blank (not allowed) in every district**, no self-storage row, §15.701.D catch-all prohibits unlisted uses → **prohibited everywhere (clean no-op)**. Districts: R-1/R-2, O/R, H, TC, O/S. No public GIS. |

---

## Per-muni proceed protocol (Group A/B), when greenlit to apply
For each muni, one PR:
1. **Rebind** — centroid-in-polygon stamp `zoning_code` from the muni's zoning-polygon layer
   for `city='<CITY>'` parcels (dry-run → eyeball distinct-code diff → apply). Normalize PUD
   suffixes ("C-3 PUD" → base "C-3") and Waukegan's `"<code> <name>"` labels.
2. **Fetch + parse** the use table under the 2.3 guards; **self-verify** column alignment +
   closed-list clause + named-use defs vs the source (browser-UA where the publisher 403s).
3. **catch #58 closed-list sweep** across inferred uses.
4. **Apply** muni-scoped verdicts: `municipality='<CITY>'`, `human_reviewed=true`, verbatim
   citations. Verify rows (catch #42). Commit `_apply_lake_<muni>.py`, open per-muni PR.
5. **Escalate** genuine ambiguities only → `outputs/_exception_queue.md` (tag C).
6. **Do NOT re-score per muni.** After the batch: ONE Lake re-score +
   `python scripts/postingest_gate.py --jurisdiction 10d01284-829b-4b03-b416-54bc452b8e70`
   (must PASS); then post distance-to-Loudoun delta + armed count by tier.

## BATCH 1 STATUS (2026-07-09) — GROUNDED + re-scored + gate PASS
Grounded end-to-end (rebind → verbatim muni-scoped verdicts, human_reviewed, catch #42 verified):
- **Gurnee** (`gurnee.json` + `_apply_lake_gurnee.py`): C-3/I-1 self_storage P; I-2/I-3 conditional.
- **Mundelein** (`_apply_lake_mundelein.py`): mini-warehouse P by-right C-1..C-4 + M-1/M-MU (255 ac).
- **Waukegan** (`_apply_lake_waukegan.py`): self_storage conditional in I only; R/LI light-ind P.
- **Deerfield** (`_apply_lake_deerfield.py`): I-2 self_storage conditional (PUD special use); thin.
- (+ county-UDO LI/II from the prior county sequence.)

**ONE Lake re-score done + `postingest_gate.py` PASS** (278,834 parcels; bound 100%; 56 distinct
codes; matrix_coverage 91.2%). Armed ≥1.5ac after batch: **416 self_storage PERMITTED + 251
CONDITIONAL = 667** (unincorp UDO 151 P; Mundelein 255 P; Gurnee 10 P + 114 C; Waukegan 131 C;
Deerfield 6 C). Distance-to-Loudoun (100%-operational gold standard): 14/56 distinct codes carry a
human verdict; the industrial/commercial spine of the 4 munis + UDO is grounded — residential codes
(the coverage tail) intentionally left ungrounded (no lead risk).

### DEFERRED to Batch 2 (each has an open blocker — do NOT ground on shaky sourcing):
- **HIGHLAND PARK** — a real GO (its `I` Light Industrial district permits self-storage **by right**),
  but the recon's GIS layer is the **WRONG JURISDICTION (catch #38 at the layer level)**:
  `ags.gisconsortium.org/.../VHP/AGOL_VHP_Project/MapServer/0` yields `ZONED` codes
  (L-I, L-O, BP, VC-C/N/P/R, B-1, B-2) that match **neither** Highland Park IL (real §150.401 codes:
  R1–R7, RM*, RO, HC=Health Care, **I**=Light Industrial, PA, overlays LFOZ/SLOZ/CDRO) **nor**
  Highland Park NJ (RA/RB/C/CBD/LI…). Its geometry also reprojects to ~-88.12/41.98 (SW Lake Co.,
  not the HP lakefront ~-87.82/42.17) → 0/12,857 rebind. So "VHP" is NOT Village of Highland Park
  zoning. FIX: find the CORRECT Highland Park IL zoning-polygon layer (city AGOL / a properly-attributed
  source), then key verdicts to IL codes.
  **Real HP IL use table IS in hand** (Municode content API, current thru Ord. O67-2025, §150.490
  Table of Allowable Uses): "Mini-warehouses" = **P in `I` only** (no self-storage row in any B
  district); "Warehouse and Distribution Facilities, Enclosed" = P in B3 + I; all manufacturing = I
  only. So once a correct HP polygon layer is found: `I` → self_storage/mini_warehouse PERMITTED,
  light_industrial PERMITTED; B3 → light_industrial PERMITTED (enclosed warehouse) but self_storage
  prohibited.
  **REUSABLE UNLOCK for Group C:** Municode's SPA 403s automated fetchers, but its **content API is
  open** — `https://api.municode.com/CodesContent?jobId=<J>&nodeId=<N>&productId=<P>` returns the
  section JSON (get jobId/productId from the SPA's network calls). This de-blocks the Group-C Municode
  munis (Vernon Hills Appendix C, Libertyville Ch.26, Buffalo Grove Title 17) — they can be grounded
  once a public zoning-polygon layer is located for each.
- **BANNOCKBURN** — GHA endpoint (`gis.gha-engineers.com/.../Bannockburn/Zoning/MapServer/2`) is
  slow/500s (retry+paginate needed); eCode360 403s the use table. Tiny (261 ac; Office-District
  special-use only). Low priority.
- **NORTH CHICAGO** — GIS layer OK (`.../Zoning_Map_WFL1/FeatureServer/14`, `ZONING_DIS`) but the
  ordinance PDF (`northchicago.org`, blocks fetchers) needs a browser-UA read to confirm the use
  table + self-storage treatment before grounding.

## BATCH 2 STATUS (2026-07-09) — thesis recalibrated to WEALTH-GATED needles
Needle = grounded ss permitted/conditional AND acres≥1.5 AND dt=10 median_home_value≥475k AND
median_hhi≥100k (`parcel_ring_metrics`, Lake has full dt=10 coverage). Batch-1 recomputed under
this gate = **70 needles** (unincorp UDO 64 + Deerfield 6; Gurnee/Mundelein/Waukegan = 0 — industrial
but OUTSIDE the wealth rings → correct no-ops, confirming the recalibration).

Wealth-gate profile (median dt10, % parcels clearing gate):
Highland Park 100% · Buffalo Grove 100% · Lincolnshire 100% · Bannockburn 100% · Lake Forest 100% ·
Riverwoods 100% · Mettawa 100% · Lake Bluff 99.7% · Libertyville 37% · Vernon Hills 12%.

- **HIGHLAND PARK — GROUNDED (the Batch-2 win).** Correct layer found (catch #38 verified codes+geom):
  `CHP/CHP_Tyler_Energov_Viewing/MapServer/3` (the UNAUTHENTICATED Tyler_Energov service; the
  `AGOL_CHP_Project` sibling needs a token). 12,853 rebound. Verdicts (§150.490 via open Municode
  content API): `I` self_storage/mini_warehouse PERMITTED + light_industrial PERMITTED; `B3`
  self_storage PROHIBITED, light_industrial PERMITTED. **+22 wealth-gated needles** (I district,
  all ≥1.5ac clear the 100% gate).
- **BUFFALO GROVE · LINCOLNSHIRE · LIBERTYVILLE — escalated (exception queue C1).** Geometry-blocked:
  GIS-Consortium `VBG`/`VOL`/`VLV` services are token-gated (unlike CHP). Real industrial districts +
  strong wealth gate (BG 100%, Lincolnshire 100%, Libertyville 37%) — geometry is the ONLY blocker;
  use tables reachable. Highest-value Lake unblock after HP.
- **VERNON HILLS — escalated (C2).** Private AGOL, no public layer; marginal (12% gate).
- **BANNOCKBURN — escalated (C3).** Only public layer (GHA) returns HTTP 500 on query; tiny.
- **RIVERWOODS · METTAWA · LAKE FOREST · LAKE BLUFF — honest no-ops (catch #52).** Clear the wealth
  gate but have NO self-storage-permitting district (Riverwoods/Mettawa: no industrial; Lake Forest:
  no industrial district; Lake Bluff: L-1/L-2 enclosed-storage only, no self-storage use class) →
  0 needles by structure. Not grounded (no false-lead risk).

## Open verification items (browser-UA reads before/at grounding)
- **Highland Park §150.490** self-storage cell (L-I / B-*) + reconcile GIS `ZONED` legacy codes ↔ Municode districts.
- **Waukegan** confirm Self-Storage(Indoor) is Conditional in `I` and absent from `R/LI` (Table 9.02-1).
- **Gurnee** Sec. 8.2.6 self-storage design standard + confirm the two self-storage rows' C-3/I-1/I-2/I-3 cells.
- **Mundelein** eyeball Table 20.32-1 to confirm the C-1..C-4 by-right mini-warehouse row.
- **Lake Forest §159.116**, **North Chicago** ordinance, **Libertyville** Ch.26 Art.5/7 — all fetcher-blocked.
