# Mercer County NJ — grounding exceptions (session 2026-08-12)

## RP-1 .. RP-11 (West Windsor township) — RESOLVED same session
- Initially escalated (the district table calls them "RP-x of the Princeton
  Junction Redevelopment Plan", a separately adopted plan) — but the plan's
  regulatory provisions turn out to be CODIFIED as Ch. 200 **Part 5**
  (§§ 200-258..200-269.3, eCode guid 13508419). Grounded verbatim and applied
  via `scripts/_apply_west_windsor.py`: all RP districts ss/mw prohibited
  (closed clauses, no storage use named); RP-5 li conditional (legacy
  electronics manufacturing confined to the existing building, § 200-264A(2)(b));
  RP-6 li prohibited by affirmative carve-out (§ 200-265A(2)(a)). RP-11-Overlay
  left out deliberately (overlay, not a base zone the layer emits).

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
