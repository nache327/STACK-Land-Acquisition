# Tewksbury Township (Hunterdon NJ) — Article VII reviewer table (2026-06-12)

Jurisdiction: Hunterdon County, NJ `e8612f49-218b-48cc-9eb0-a1dd90cf583d`, municipality=`Tewksbury township`
(2,731 parcels, 100% zoned). Source: Nache paste of Article VII §709–710.2 (conservation/residential
districts). **The VB / VO / RO-MXD business districts were truncated (50k limit) and are NOT yet parsed.**

## Zone distribution (the impact universe)
| Zone | Parcels | ≥1.5ac | District | In paste? |
|---|---|---|---|---|
| HL | 1,901 | 1,755 | Highlands (12ac residential/ag) | ✅ §709 |
| VR | 230 | 36 | Village Residential | ❌ |
| **PM** | **206** | **135** | **Piedmont (5ac residential/ag)** | ✅ §710.2 |
| FP | 149 | 139 | Farmland Preservation (7ac) | ✅ §710.1 |
| SO | 85 | 5 | (Senior Overlay?) | ❌ |
| R-1.5 | 75 | 47 | Residential | ❌ |
| TH-V | 30 | 3 | Townhouse-Village | ❌ |
| **VB** | **30** | **2** | **Village Business** | ❌ NEEDS PASTE |
| LT | 16 | 14 | Lamington (10ac residential/ag) | ✅ §710 |
| **RO/MXD** | **4** | **4** | **Research-Office / Mixed** | ❌ NEEDS PASTE |
| **VO** | **3** | **1** | **Village Office** | ❌ NEEDS PASTE |
| R-2 | 2 | 0 | Residential | ❌ |

## Reviewer table — verdicts FROM the pasted text (ground-truthed)
Convention: warehouse permitted by-right as a *principal* use → self_storage/mini_warehouse conditional.
None of the pasted districts permit warehouse or storage as a principal use. "Storage sheds/tool sheds"
= residential accessory; "processing/freezing/storage of farm products" = agricultural accessory;
"School bus storage" (conditional) = institutional bus depot, NOT a warehouse/self-storage use. None
trip the convention.

| Zone | self_storage | mini_warehouse | light_industrial | Basis (Article VII) |
|---|---|---|---|---|
| HL | prohibited | prohibited | prohibited | §709 — 12ac residential/ag; principal uses = ag, SFD, civic, worship, schools, affordable hsg. No commercial/industrial. |
| LT | prohibited | prohibited | prohibited | §710 — 10ac residential/ag; same use set. |
| FP | prohibited | prohibited | prohibited | §710.1 — 7ac farmland preservation; same use set. |
| **PM** | **prohibited** | **prohibited** | **prohibited** | §710.2 — Piedmont 5ac residential/ag; principal uses = ag, SFD, civic, worship, schools, affordable hsg, **kennels**. **CONFIRMS false-friend: Piedmont CONSERVATION, not Manufacturing.** |

**Status of these 4 vs current DB:** all four already resolve to `prohibited` via Hunterdon county-default
rows (municipality=NULL, src=human). Applying muni-specific `human_reviewed=true` rows is **confirmatory
only** — it upgrades provenance (bulk→ground-truthed) but moves zero parcels. The user pre-flagged "NOT
PM" — so applying these is optional busywork unless we want the provenance upgrade.

## The actual needle check — PENDING PASTE
VB (30) / VO (3) / RO-MXD (4) are the only districts where storage could plausibly be permitted/conditional.
Currently all three = prohibited (county-default). **Need their Article VII sections** (they follow §710.2,
likely §710.3+ / Village districts) to confirm or flip. Needle ceiling is tiny (37 parcels, 7 ≥1.5ac) —
consistent with Tewksbury being a wealthy rural conservation township with near-zero commercial/industrial.

## Recommendation
Tewksbury's headline (the 206 PM parcels) is **resolved: confirmed prohibited, no needle.** The remaining
open item is the VB/VO/RO-MXD use lists. Hold all writes per validate-before-apply; await (a) Nache's
greenlight on whether to apply the 4 confirmatory prohibited rows, and (b) the VB/VO/RO-MXD paste.
