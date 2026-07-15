# Session B — White Plains NY + resort-commercial residuals (closers), 2026-07-15

Playwright-headless method unblocked the JS-gated codes. No re-score/CoStar.

## 1. White Plains NY (in Westchester jid 3e706886) — DONE: 5 needles (LI)
- municipality='White Plains'; 2,372 wealth&1.5ac town-wide. Zoning ordinance is a SEPARATE doc (Municode
  Ch. 9-2 explicitly excludes it) → city PDF (DocumentCenter/8865, amended 2-5-2024).
- Use table column-aligned by pdfplumber x-position (page 81 industrial block); validated: Manufacturing /
  Printing / Wholesale-storage-warehousing / "Mini-storage facility" all = PP (permitted) in the Light
  Industrial column (x≈912.6, header IL / DB code "LI"). §4.4.28 defines "Mini-storage facility" = a
  self-storage facility. Mini-storage appears in NO other district column → confined to LI.
- **NEEDLES = 5 (SELECT-confirmed, all LI).** CB-4 (335 w15) / RM-* / BR-2 clear the ring but permit no
  self-storage (mini-storage confined to LI) → correct no-op. verify_batch CLEAN, gate PASS (Westchester
  total 127 incl. Session-D towns; 3 on-needle CoStar).

## 2. Pinecrest FL (jid 55da99fa) — NO-OP (confirmed)
- Municode content-API (client 10759, node prefix COORVIPIFL_CH30LADERE_ART4ZODIRE). In-ring BU districts
  BU-1/BU-1A/BU-2 (4+14+5 w15) EXPLICITLY exclude mini-storage ("not intended to accommodate warehousing,
  mini-storage, outside storage or light manufacturing"). Only **BU-3** permits mini-storage ("can
  accommodate ... mini-storage ... within an enclosed building") — but BU-3 has 10 parcels, **0 in-ring
  wealth&1.5ac**. → 0 needles. Not grounded.

## 3. Park City UT (jid 13b01b39) — NO-OP (confirmed)
- parkcity.municipalcodeonline.com print view (static). General Commercial (GC) district allowed-use list:
  no self-storage / mini-storage / warehouse use (9 "storage" hits are all outdoor-retail / refuse /
  bicycle / snow storage). Park City is a ski resort with no industrial zone; commercial = resort/Main-St
  retail. DB "Comm" (325/15 w15) = general commercial → no self-storage. → 0 needles. Not grounded.

## 4. Snyderville/Promontory UT (Summit County jid 72492dd8) — DONE: 3 needles (CC)
- Summit County Title 10 Snyderville Basin Development Code Ch. 2 use table (Municode-mirror, Playwright).
  Columns RR HS MR CC SC NC. Row "Storage, self-service" = * * * **L L** * → Allowed (L) in CC (Community
  Commercial) + SC (Service Commercial); * elsewhere. → CC/SC self_storage PERMITTED.
- **NEEDLES = 3 (SELECT-confirmed), all CC.** SC has 0 in-ring (INDUS/LI/SC corridor out of the wealth
  ring). NC self-service=* → prohibited.
- **TC (Town Center, 21 in-ring) = INDETERMINATE, not grounded:** TC is NOT in the Ch. 2 use table — TC
  uses are set case-by-case via §10-2-12 (master-plan/development-agreement), with no fixed by-right/
  conditional self-storage entitlement. Did not force a verdict (#37). If the coordinator wants the 21 TC
  lots pursued, it requires reading specific TC master-plan/development-agreement documents (per-project).

## Batch total: +8 needles (White Plains 5 + Snyderville CC 3); Pinecrest + Park City = confirmed no-ops.
