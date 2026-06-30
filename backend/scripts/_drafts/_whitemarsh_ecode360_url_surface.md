# Whitemarsh Township (Montgomery PA) — eCode360 URL surface (for Nache grab, 2026-06-29)

eCode360 blocks automated fetch (403) → Nache grabs use tables; Claude Code applies on paste.
Catch #38: Whitemarsh Township, Montgomery County PA (Lafayette Hill/Flourtown). Chapter 116 Zoning.

## Direct links
- **Township root:** https://ecode360.com/WH0819
- **Chapter 116 Zoning:** https://ecode360.com/11708888

### PRIORITY grab — the likely-needle industrial zones (~17 SN-pass)
| zone | SN-pass | eCode360 | prediction |
|---|---|---|---|
| **LIM / LIM-X Limited Industrial** | 9 | https://ecode360.com/11709925 | likely permitted/conditional (warehousing) |
| **HVY Heavy Industrial (Art. XXI)** | 8 | https://ecode360.com/11710036 | likely permitted/conditional |

### Verify-the-trap grab — likely PROHIBITED (confirm office/lab, not storage)
| zone | SN-pass | eCode360 | prediction |
|---|---|---|---|
| **CLI-X Modified Campus-Type Limited Industrial** | 15 | https://ecode360.com/11709888 | **PROHIBITED** (office+lab only per eCode360 preview; no storage) |
| **CLI Campus-Type Limited Industrial** | 12 | https://ecode360.com/11709833 | likely PROHIBITED (campus office/lab) |

Grabbing CLI/CLI-X matters: if they're office/lab (as the preview shows), they're prohibited and the 27
SN-pass they carry drop OUT of the pool — so confirming them prevents 27 false needle-candidates.

### Skip / negligible
- EX Extraction — quarrying use class, self-storage silence-prohibited; 1 SN-pass (negligible).
- Residential (A/AA/AAA/AAAA/B/AD/APT*) + commercial (CR-H/CR-L, VC-1..4) — silence-prohibited if grabbed.

## On paste, Claude Code runs:
1. Cross-check grabbed codes vs parcels.zoning_code (CLI/CLI-X/LIM/HVY/EX confirmed present; check LIM-X).
2. Apply via `_apply_whitemarsh_verdicts.py` (direct UPSERT, municipality='Whitemarsh Township').
3. Re-score vs SN + harvest preview. PR parcellogic/montgomery-pa-whitemarsh-verdicts.
