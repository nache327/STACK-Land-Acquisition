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

## Open verification items (browser-UA reads before/at grounding)
- **Highland Park §150.490** self-storage cell (L-I / B-*) + reconcile GIS `ZONED` legacy codes ↔ Municode districts.
- **Waukegan** confirm Self-Storage(Indoor) is Conditional in `I` and absent from `R/LI` (Table 9.02-1).
- **Gurnee** Sec. 8.2.6 self-storage design standard + confirm the two self-storage rows' C-3/I-1/I-2/I-3 cells.
- **Mundelein** eyeball Table 20.32-1 to confirm the C-1..C-4 by-right mini-warehouse row.
- **Lake Forest §159.116**, **North Chicago** ordinance, **Libertyville** Ch.26 Art.5/7 — all fetcher-blocked.
