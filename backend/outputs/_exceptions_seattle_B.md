# Session B — Seattle WA cluster (Phase 6), 2026-07-15

Acres freshly backfilled; targets bound per-city, ring=0. WA parcels.city mixed-case. Did NOT touch
King COUNTY jid (coordinator-gated). Ring-precompute run per-city (≤2 concurrent).

## Bellevue WA (jid 71a53bba-8697-4b8d-93e9-e3de091b8706) — DONE: 46 needles
- Ring-precompute done (40 tracts) → 978 wealth&1.5ac town-wide. Bound 85%. municipality='Bellevue'.
- Ordinance = Bellevue LUC Chart 20.10.440 (city site bellevue.municipal.codes is **Cloudflare-JS-gated**;
  chart obtained from a static broker-PDF reproduction of Chart 20.10.440, x-position-aligned, cross-checked
  to LUC 20.10.300). Non-residential column order: PO O OLB OLB2 **LI GC** NB NMU CB F1 F2 F3.
- Use "637 Warehousing and Storage Services" cells aligned by x (−6.4pt offset): **LI=P, GC=P** (by-right);
  CB/F1=S (special, not by-right). No distinct self-storage/mini-storage use named → warehouse-by-right
  convention ⇒ **LI & GC: ss/mw CONDITIONAL, li PERMITTED**, lgc prohibited. LUC 20.10.300 corroborates
  (LI = "manufacturing, wholesale trade and distribution").
- **NEEDLES = 46 (SELECT-confirmed): LI 28 + GC 18.** verify_batch CLEAN, gate PASS.
- **FLAGGED (not armed — JS-blocked, need column-verified confirmation):** O(54)/OLB(42)/OLB2(26) office,
  CB(25, warehousing='S'), and the BR-* Bel-Red corridor zones (BR-GC 25, BR-CR 19, BR-ORT 10 …, separate
  chart LUC 20.10.375). Coordinator: paste/JS-fetch the Bel-Red + office use charts to assess.

## Mercer Island WA (jid bdf769db-4150-45da-baa5-529995e7246f) — NO-OP (as expected)
- Ring done → 97 wealth&1.5ac (ring maxHV $1.83M — very wealthy). **No industrial zone.** Zones are
  residential (R-15/R-8.4/R-9.6/MF-*), Public Institution (PI), Open Space (OS), and a small Town-Center
  retail/office core (PBZ Planned Business 5, C-O Commercial-Office 4, TC Town Center 1 wealth&1.5ac).
  No self-storage-permitting district exists (retail/office town-center, like Darien/Winnetka). → 0 needles.
  Not grounded (BIMC on JS-gated codepublishing; no-op holds from the zone profile — no industrial).

## Bainbridge Island WA (jid c6af2bd5-6ecb-4c4a-a9af-d51345c615c0) — NO-OP (self-storage BANNED)
- Ring done → 1,896 wealth&1.5ac (ring maxHV $1.0M). NOT pure-residential — has B/I (Business/Industrial,
  12 wealth&1.5ac), WD-I (Water-Dependent Industrial, 3), MUTC (Mixed Use Town Center, 20).
- **Bainbridge Island City Council BANNED new self-storage development town-wide** (was previously permitted
  in B/I + Neighborhood Service Center; ban removes those as options for new projects, existing may expand).
  → self_storage PROHIBITED town-wide ⇒ 0 needles, despite the industrial zoning. WD-I is water-dependent
  (marine, excludes self-storage); MUTC is mixed-use retail/residential.
- Not grounded: primary BIMC 18.09 use table is on JS-gated codepublishing; the ban is confirmed by
  trade-press (InsideSelfStorage) + the 2026 Title-18 update ordinance. No-op conclusion is definitive; did
  not write speculative verdicts (#37). If a needle-hunt is wanted later, paste BIMC 18.09.020 to confirm
  B/I self-storage is prohibited verbatim.
