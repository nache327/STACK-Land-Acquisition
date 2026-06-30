# West Conshohocken Borough (Montgomery PA) — eCode360 URL surface (for Nache grab, 2026-06-29)

eCode360 blocks automated fetch (403) → Nache grabs use tables; Claude Code applies on paste.
**Catch #38: West Conshohocken Borough (Ch.113), NOT Conshohocken Borough (Ch.27, east-bank muni).**

## Direct links
- **Chapter 113 Zoning:** https://ecode360.com/8252545

### PRIORITY grab — the one table that determines both needle zones (15 SN-pass)
| zone | SN-pass | eCode360 | note |
|---|---|---|---|
| **LI Limited Industrial (Article XI)** | 10 | https://ecode360.com/8253076 | the base use list — HI inherits it |
| **HI Heavy Industrial** | 5 | https://ecode360.com/8253135 | "any use permitted in LI, except adult entertainment" + noxious exclusions → **follows LI verdict** |

Grab **LI Article XI** first — it sets both. Check: is self-storage / self-service storage / mini-warehouse
named? Is warehouse/storage/distribution by-right? (LI intent = "nonpolluting smaller-scale industrial,
R&D and office" — could be permissive or office-leaning; read the use list.) Then confirm HI just adds
the noxious exclusions on top.

### Skip / 0-yield
O/O-1 (office), IB/LC (commercial), R-1/R-2/GA (residential) — silence-prohibited; grab only for completeness.

## On paste, Claude Code runs:
1. Cross-check codes vs parcels.zoning_code (LI/HI confirmed present).
2. Apply via `_apply_west_conshohocken_verdicts.py` (direct UPSERT, municipality='West Conshohocken Borough').
3. Re-score vs SN + harvest preview. PR parcellogic/montgomery-pa-west-conshohocken-verdicts.
