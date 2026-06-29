# Upper Merion Township (Montgomery County PA) — Stage-4 harvest preview (2026-06-29)

First Montgomery PA muni grounded. 7 muni-specific human verdicts via direct UPSERT (catch #29),
municipality='Upper Merion Township'. jurisdiction = Montgomery County PA. Re-scored vs SN filter
(72409acf), 301,509 parcels.

## Verdicts applied (7 zones, GIS codes)
| zone (GIS) | ordinance | self_storage | light_ind | conf | basis (catch #37) |
|---|---|---|---|---|---|
| HI | HI Heavy Industrial | **permitted** | permitted | 0.90 | §165-153 **catch-all** "any lawful purpose not elsewhere prohibited" — 6th distinct basis |
| LI | LI Limited Industrial | **conditional** | permitted | 0.92 | §165-144.B warehousing by-right + self-storage unnamed → Cresskill; §165-144.F similar-use SE |
| SC | SC Shopping Center | prohibited | unclear | 0.88 | Table CD.1 silence rule |
| CN | NC Neighborhood Commercial | prohibited | unclear | 0.88 | Table CD.1 silence (GIS CN = ord NC, catch #34) |
| CL | LC Limited Commercial | prohibited | unclear | 0.88 | Table CD.1 silence (GIS CL = ord LC) |
| CG | GC General Commercial | prohibited | unclear | 0.88 | Table CD.1 silence (GIS CG = ord GC) |
| KPMU | King of Prussia Mixed-Use | **prohibited** | permitted | 0.95 | Table KPMU 1 **"Mini storage NP" EXPLICIT** — 7th distinct basis (first explicit prohibition; ordinance distinguishes general warehousing P from mini-storage NP) |

## Armed pool (verdict permitted/conditional + sized 1.5–15ac + SN wealth gate dt=10 HV≥475k & HHI≥100k)
| zone | sized | SN-wealth-pass |
|---|---|---|
| HI (permitted) | 67 | 33 |
| LI (conditional) | 65 | 58 |
| **TOTAL LI+HI** | **132** | **91** |

**91 armed needle-candidate parcels** in Upper Merion (verdict-PASS on permitted/conditional industrial +
clear the wealth gate + sized). This is the strongest Montgomery PA pool (Upper Merion led the SN-pass
ranking at 94 across all industrial zones; 91 on LI/HI specifically).

## Live needles: 0 (expected — catch #45)
No Stage-2 CoStar listing data refreshed for Montgomery PA. Armed pool (91) is ready; live needles
surface only when a CoStar listing matches an armed parcel. Stage-2 CoStar refresh is the deferred 2nd
pass (Nache). storageVerdictMode='only' is now satisfiable on LI/HI (human_reviewed verdicts exist).

## Cross-corridor (Main Line PA county_gis trio — Stage 4)
- Chester: Tredyffrin, Willistown, East Whiteland, etc. (prior sessions)
- Bucks: Newtown, Doylestown Borough (prior)
- **Montgomery PA: Upper Merion (NEW — 7 zones, 91 armed)** ← first Montgomery muni grounded
Live needles across the trio remain 0 pending Stage-2 CoStar refresh.

## Held (need own use schedules)
SM/SM-1 (Suburban Metropolitan — KoP retail/office core, ~176 parcels), C-O, NMU, AR/A-R, CA. HIR overlay
(§165-153.E) + data-center conditional uses (§165-144.K/§165-153.I) noted, not applied.
