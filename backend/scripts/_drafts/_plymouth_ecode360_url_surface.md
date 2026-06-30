# Plymouth Township (Montgomery PA) — eCode360 URL surface (for Nache grab, 2026-06-29)

eCode360 blocks automated fetch (403) → Nache grabs the use tables; Claude Code applies on paste.
**Catch #38: grab Plymouth TOWNSHIP (Montgomery County), NOT Plymouth Borough (Luzerne, Ch.231).**

## Direct links
- **Township root:** https://ecode360.com/PL1880
- **Zoning (Appendix B):** https://ecode360.com/26906730

### PRIORITY grab — the needle zone (19 SN-pass, the entire meaningful pool)
| zone | SN-pass | eCode360 |
|---|---|---|
| **LI Limited Industrial (Article XIV)** | **19** | https://ecode360.com/26907287 |

Article XIV is the high-value grab: WebSearch shows it has an explicit **"Self-service storage facilities"**
regulation. Grab the §-level USE list (permitted / accessory / special-exception / conditional) — confirm
whether self-service storage is by-right (permitted) or special-exception/conditional. That single verdict
drives Plymouth's entire armed pool (~19).

### Optional / low-yield (0 SN-pass — produce 0 needles even if permitted; grab only for completeness)
- HI Heavy Industrial, CI, IP Industrial Park, ID — all 0 wealth-pass.
- Commercial (COMM/LC/SC) + residential (A/AA/B/C/D/MUV) — silence-prohibited coverage if easy.
  (Reconcile idiosyncratic single-letter codes vs ordinance names.)

## On paste, Claude Code runs (fast):
1. Cross-check grabbed codes vs parcels.zoning_code (LI confirmed present, 111 parcels).
2. Apply muni-specific verdicts via `_apply_plymouth_verdicts.py` (direct UPSERT, municipality='Plymouth Township').
3. Re-score vs SN (filter 72409acf-3712-4761-a156-50c2329ad35b) + harvest preview.
4. PR parcellogic/montgomery-pa-plymouth-verdicts (review-gated).
