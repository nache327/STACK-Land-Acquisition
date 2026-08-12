# Mercer County NJ — grounding exceptions (session 2026-08-12)

## RP-1 .. RP-11 (West Windsor township) — Princeton Junction Redevelopment Plan
- **83 parcels** bind to RP-* codes from the township zoning layer (RP-7: 33,
  RP-6: 14, RP-1: 10, ...), ~66 of them wealth-gated ≥1.5ac.
- Chapter 200 (the zoning ordinance) does NOT regulate these districts — its
  district table lists each as "RP-x **of the Princeton Junction Redevelopment
  Plan**", a separately adopted redevelopment plan document (N.J.S.A. 40A:12A).
- The plan text was not fetched this session; the districts are TOD
  residential/mixed-use around Princeton Junction station, so storage yield is
  unlikely but NOT verified. Verdicts were deliberately **not** written (#37:
  no verbatim basis without the plan text).
- To close: fetch the current Princeton Junction Redevelopment Plan (+ all
  amendments) from westwindsortwp.gov, ground the RP-1..RP-12 use lists, and
  extend `scripts/_apply_west_windsor.py`.

## Hopewell Township / Lawrence Township / East Windsor Township — no spatial bind
- Discovery agent verified NO public zoning GIS layer exists for any of the
  three (AGO, Hub, township orgs, Mercer County org, third-party aggregator).
  Two wrong-jurisdiction traps documented and rejected: "Hopewell Township
  Zoning" (Seneca County OHIO) and "Hopewell Township Interactive Zoning Map"
  (York County PENNSYLVANIA) — catch #38.
- Ordinances ARE located: Hopewell `ecode360.com/HO4061`; East Windsor
  `ecode360.com/EA4077` (Ch. 20 = 36451542); Lawrence's eCode has NO zoning
  chapter — the adopted Land Use Ordinance is self-hosted
  (`lawrencetwp.com/.../Land_Use_Ordinance_2019.pdf` + post-2019 amendment
  ordinances; no consolidated current text online).
- Zoning map PDFs exist for Hopewell (DocumentCenter/View/465) and Lawrence
  (Zoning Map dated 2021); East Windsor's official map is on file in Township
  offices only.
- Status: parcels ingested + rings complete; zoning_code NULL pending a bind
  source (DVRPC dataset is token-gated; county org has parcels only).
