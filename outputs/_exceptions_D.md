# Session D exceptions — Morris NJ (746b7604) + Westchester NY (3e706886) + MontPA carryover

Per-session file (not the shared queue).

## Morris NJ — batch 1 (2026-07-09) — wealthy-industrial discovery

Discovery-ranked un-grounded towns by wealth-ring industrial/commercial parcels; grounded the top 4.
All eCode360 curl+UA; DOM-anchor for use placements. NJ casing (mixed-case + suffix) matched EXACTLY.
NJ parcels 100% zoning-coded (name-bound; no rebind).

| Town | Verdict | Basis |
|---|---|---|
| **Hanover township** | **I-B + I-B2 → permitted** (28 parcels); base I/I-P/I-5/I-P2 + all others → prohibited | §166-203.6K (I-B3) / §166-203.2B (I-B2) list "Self-service storage facilit(y/ies)" as a Permitted use. DECISIVE: §166-119.2 "self-service storage facilities are prohibited in all zone districts ... unless specifically permitted" — OVERRIDES the warehouse-by-right convention, so base I (126, warehouse-by-right) is PROHIBITED. catch #37/#57 — verbatim prohibition beats inference. |
| **East Hanover township** | **I-3 → permitted** (128 parcels); I-1 + all others → prohibited | §95-59A(1)(j) "Self-storage facilities" is a Permitted principal use in the Light Industry I-3 Zone. Named only in I-3 → affirmative-provision → prohibited elsewhere. Biggest Morris needle this batch. |
| **Montville township** | **I-1B + OB-2A + B-5 → conditional** (38 parcels); other industrial (I-1A/I-2/I-2A) → prohibited | §230-173 makes self-storage a CONDITIONAL use assigned ONLY to B-5/I-1B (§230-173A), OB-2A/OB-4 (§230-173B), OB-5 (§230-149). Named-use restricted to those zones → I-1A/I-2/I-2A prohibited (affirmative-provision). |
| Denville township | all industrial/commercial → **prohibited** (no-op) | Ch. 600 Part 4 names self-storage 0×; I-1/I-2 primary use = offices/labs/industrial-and-manufacturing (NO warehouse → no convention trigger). Honest no-op. |

Morris batch-1 needle contribution (pre-wealth/size gate): Hanover I-B/I-B2 (28 permitted), East Hanover
I-3 (128 permitted), Montville I-1B/OB-2A/B-5 (38 conditional) — wealth-gated totals in verify_batch below.
KEY NJ catch: multiple Morris towns have a general "self-storage prohibited unless specifically permitted"
provision (Hanover §166-119.2) or assign self-storage to specific named districts — reading verbatim
prevents false warehouse-convention needles (Hanover base I would have falsely armed 126 parcels).

## Westchester NY — batch 4 (2026-07-09) — 2nd-tier discovery (mostly no-ops, as expected)

Re-ran the wealth-ring industrial/commercial ranking on remaining un-grounded towns. As the coordinator
predicted, self-storage is narrowly zoned in Westchester → high no-op rate. All eCode360 curl+UA; use
schedules via attachment PDFs (pdfplumber) / embedded HTML tables. Held #37 legacy-code discipline.

| Town | Verdict | Basis |
|---|---|---|
| Bedford | LI/CB/NB/PB-O/PB-R/PB-O(K) → **prohibited** (no-op) | Ch. 125 Use schedules (Principal 125b + Special Permit 125d): self-storage/mini-warehouse named 0×; LI lists only generic "Wholesale business, storage or warehouse" (no-inference). Very-high-wealth but not zoned for it (catch #52). |
| Mount Kisco | GC/CD/CD-2/CL/CB-1/OG/SC → **prohibited** (no-op) | Ch. 110 Art III (71 use tables): self-storage 0×; "warehouse" only generic ("Wholesale, indoor storage and warehousing establishments"; accessory indoor storage). No-inference. |
| Dobbs Ferry | OF1-6/DB/B/CP/WFA/WFB/EI → **prohibited** (no-op) | Ch. 300 Art X use tables + Art XIII + Definitions: self-storage/warehouse/storage named 0×. Office/downtown/waterfront village. |

### ⚠ D-wc-4 — Port Chester: ESCALATE (form-based recode vs legacy parcel codes — Hudson pattern)
Port Chester adopted a **form-based "Character Districts"** code (Ch. 345, §345-302/305). Parcels carry
LEGACY codes **M1/M2** (manufacturing), DW, MUR, C3, VCRA — which do NOT appear in the current
Character-District descriptions (only CD/PMU matched). Cannot ground the legacy M1/M2 parcels against the
current form-based scheme (Hudson/Bridgeport version-mismatch discipline). **Need:** a re-stamp of Port
Chester parcels to the current Character-District codes, OR an old→new crosswalk. LOW priority — small
pool (~10 wealth+sized M1/M2) and Port Chester is lower-wealth (barely clears the ring). Not forced.

Batch-4 needle yield = 0 (3 honest no-ops + 1 version-mismatch escalation). Confirms self-storage is
narrowly zoned to specific industrial districts in Westchester (grounded so far in New Rochelle LI,
Yonkers BR/B/BA, Yorktown I-1/I-2) and absent from these 2nd-tier commercial/office/light-industrial towns.

## Westchester NY — batch 3 (2026-07-09) — data-driven discovery

Ranked un-grounded towns by wealth-ring commercial/industrial parcels; grounded the top 4 with genuine
industrial/commercial ZONING (residential-heavy towns like Bedford/Somers/Scarsdale = correct no-ops,
not forced). All eCode360 via curl+UA; use-schedule attachment PDFs parsed with pdfplumber; DOM-anchor
method for interleaved schedules.

| Town | Verdict | Basis |
|---|---|---|
| **Yorktown** | I-1 + I-2 → **conditional** (0.90, 55 parcels); C-1/2/2R/3/4/CC/O/OB → prohibited | §300-21 schedule places "Self-storage center ... §300-79" in **I-1 Light Industrial Park** + **I-2 Planned Light Industrial** (Planning Board special permit, dead-storage only, ≥2ac). §300-79's "M-1/M-1A/M-2" are LEGACY names for the current I-1/I-2 (DOM-verified via schedule district headers). Commercial C-2 family expressly excludes self-storage buildings (§300-21C(12)). |
| Croton-on-Hudson | WDD/LI/C-1/C-2/WC/O-1 → **prohibited** (no-op) | Schedule of Uses (Attach. B) + Special Permit Schedule (Attach. D) name no self-storage/mini-warehouse; only generic "Warehousing, wholesaling, freight distribution" (§230-18). No-inference. |
| New Castle (Chappaqua) | B-R/I-G/I-P/B-D/B-RP/B-RO-20 → **prohibited** (no-op) | Business & Industrial Use schedule (Attach. 060d) names self-storage/warehouse 0 times; only accessory/incidental storage. Ultra-wealthy, catch #52. |
| Rye Brook | OB-1/2/3/S + C1/C1-P/H-1 → **prohibited** (no-op) | Schedule of Regulations use matrix (18 tables) names no self-storage use; "storage" only in restrictions ("no storage on non-office premises"). Office-campus/PUD village. |

Batch-3 needle yield = Yorktown 55 conditional parcels (subject to wealth+size gate — see verify_batch).
3 honest no-ops confirm the discovery filter (real industrial/commercial zoning ≠ self-storage permission
in these NY towns; self-storage is consistently narrowly zoned).

## Westchester NY — batch 2 (2026-07-09)

### Grounded / resolved this batch
| Town | Verdict | Basis |
|---|---|---|
| Yonkers (industrial) | M/MG/I/PMD/IP + CBD/C/CM/OL → **prohibited** | **Resolves D-wc-1.** §43-27 Schedule of Use Regulations (full use list — 34 manufacturing uses) has NO self-storage row; §43-36.M authorizes "Self-storage warehouse" ONLY in BR/B/BA (2018). Self-storage NOT affirmatively provided in industrial (catch #57); no-inference (generic warehousing ≠ self-storage). Yonkers self-storage yield = BR/B/BA only. Catch #37: PMD = Planned Multi-Use, not Mfg. |
| Tarrytown | WGBD/GB/NS/OB/ID/MU/HC/LB → **prohibited** (honest no-op) | Self-storage / self-service / mini-warehouse NAMED NOWHERE in Ch. 305 (commercial, industrial, WGBD, whole chapter). ID permits only generic "warehousing/storage in buildings" (no-inference). Catch #37: M-1/1.5/2/3/4 = Multifamily Residence, NOT manufacturing — not verdicted. 0 needles. |

### D-wc-1 — RESOLVED (see above): Yonkers industrial does NOT add self-storage needles.
### D-wc-2 (Tarrytown) — RESOLVED (see above): honest no-op.

### ⚠ D-wc-3 — White Plains: Municode-only, API ApiKey-gated (NOT grounded this batch)
White Plains zoning is on **Municode** (library.municode.com/ny/white_plains) — NOT eCode360 (WH1268 =
error), NOT amlegal. Tried the banked Municode content-API unlock: `api.municode.com/CodesContent` needs
a numeric productId/jobId + an **ApiKey** that the Angular SPA injects at runtime (shell HTML shows empty
`ApiKey:`/`ApiUrl:` config placeholders; `/Clients/name`, `/Clients/stateAbbr/NY`, `/products/...` all
404/400 without it). WebFetch on a JS SPA returns only the shell. Needle worth it: LI:134 + CB-1/2/3/4
+ B-1/2/3/6 + C-O in a very-high-wealth ring (~640 wealth+sized commercial). **Need:** the White Plains
Municode productId + jobId (+ ApiKey if required), OR a coordinator paste of the LI/CB/B use table +
any self-storage/self-service-storage/mini-warehouse definition. Deferred to a follow-up.

## Westchester NY — batch 1 (2026-07-09)

### Grounded this batch
| Town | Needle verdict | Basis | source |
|---|---|---|---|
| New Rochelle | LI → **permitted** (0.95, 443 parcels); LSR → **conditional** (0.88, 96, ≤2ac cap) | §331-59.A(13) "Self-storage facility" permitted principal use (litem anchor 331-59A(13)); LSR §331-58 special permit + §331-105.1 (≤2ac). Self-storage named ONLY in LSR/LSR-1/LI/LI-H; rest prohibited. | eCode360 curl+UA (DOM-anchor parse) |
| Yonkers | BR/B/BA → **conditional** (0.80) — PARTIAL | §43-36.M "Self-storage warehouse" (Added 2018) affirmatively regulated in BR/B/BA (retail-liner + storage-only standards). Industrial escalated (below). | eCode360 curl+UA |
| Harrison | business SB-0/B/PB → **prohibited** (honest no-op) | §235 Attach.3 Business Use Table: self-storage NOT a listed use (only "Equipment storage building"); closed table → prohibited. Ultra-wealthy Purchase; catch #52. 0 needles. | eCode360 attachment PDF |

### ⚠ D-wc-0 — Westchester postingest_gate HARD FAIL (pre-existing, NOT this batch)
`postingest_gate.py --jurisdiction 3e706886` **FAILS**: `HARD FAIL: URL-shaped / over-length
zoning_code(s): ['View Preservation Overlay'] (1 distinct)`. Cause: **79 parcels in Hastings-on-Hudson**
carry `zoning_code='View Preservation Overlay'` — an overlay NAME mis-ingested as a base zoning_code
(county-ingest data defect). This is pre-existing and in a town I did NOT touch; my verdicts only write
muni-scoped `zone_use_matrix` rows, never `parcels.zoning_code`. Gate also reflects partial county
coverage (bound_pct 0.86, matrix_coverage 0.77 — Westchester is early-stage, 7+3 towns grounded of 43).
**Not mine to fix** (parcel-data/ingest level, Hastings-on-Hudson). Needs an ingest-side fix: null out or
remap the 79 Hastings 'View Preservation Overlay' zoning_codes to the base district + strip the overlay
to `overlay_tags`. Re-score succeeded (independent of gate); my towns' verdicts + needle tally are valid.

### OPEN escalations

#### D-wc-1 — Yonkers industrial (M/MG/I/PMD): needs Table 43-1
§43-36.M names self-storage warehouse standards for BR/B/BA, but does NOT settle whether the large
INDUSTRIAL districts (M:4316, MG:2364, I:914, PMD:255) permit self-storage/warehouse. Yonkers zoning
uses per-district use lists / Schedule of Use Regulations (Table 43-1, §43-27) that don't render as a
single clean HTML table via curl (the page returns explanatory text only; the schedule is a large
table/attachment I couldn't cleanly extract). **Need:** Table 43-1's self-storage-warehouse + general-
warehouse rows across M/MG/I/PMD (P/SP/X). Big potential pool — high priority for a follow-up with
table-extraction. BR/B/BA already grounded conditional.

#### D-wc-2 — White Plains + Tarrytown: DEFERRED (heavy city codes, this batch)
Both have real commercial pools in the wealth ring (White Plains CB-4/BR-2/C-O ~640 comm; Tarrytown
WGBD/OB/ID + note that Tarrytown's M-1/M-2/M-3 are **Multifamily Residence**, NOT manufacturing —
catch #37, do not treat as industrial). Not parsed this batch due to time (NY city use tables are
attachment/large-table format; New Rochelle's interleaved-section parse alone was heavy). Queued for
Westchester batch 2.

### Method notes (for the next Westchester session)
- eCode360 NY city pages INTERLEAVE sibling district sections; plain text extraction misattributes uses
  across districts. Resolve placements by DOM position: the litem anchor (e.g. `331-59A(13)`) or the
  nearest `data-full-title` section anchor + nearest use-category header. This is how New Rochelle LI was
  confirmed (an earlier text-only read wrongly showed LI without self-storage — it was an adjacent
  district's list).
- Use-schedule TABLES are often eCode360 attachment PDFs: `/attachment/<id>/<file>.pdf` (Harrison's
  business use table came through this way). Try this before declaring a table unparseable.
- catch #37 (verbatim over code-name): read district ENUMERATION names — NY "M-1/2/3" can be Multifamily
  (Tarrytown), not Manufacturing. Triage by district NAME, not letter.

## MontPA carryover (parked for a Nache ruling — from prior batches)
- Upper Dublin Township — amlegal-hosted (not eCode360/Municode; API 404; ALS.pdf is a stub). Needle: CR-I.
  Need amlegal content path / town PDF / OK-to-use-Zoneomics.
- Lower Merion Township — no industrial district (IE/IC = Institutional, catch #37); elite no-op, deferred.
- Bryn Athyn Borough — tiny (LI:7), town-site-only source; marginal.
