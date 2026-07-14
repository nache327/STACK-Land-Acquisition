# Session D exceptions — Westchester County NY (jid 3e706886) + MontPA carryover

Per-session file (not the shared queue).

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
