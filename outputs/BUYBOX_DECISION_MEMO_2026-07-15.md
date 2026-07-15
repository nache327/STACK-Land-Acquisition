# Buy-box decision memo — 3 calls for Nache (2026-07-15)

Audit context: the scoring pipeline is healthy (ON CONFLICT fix + Actionable-only digest shipped in
`fix/buybox-onconflict-holdworthalook`; NULL homes_over_1m columns confirmed inert — never gate or
skew). These three are **design decisions**, not defects — the system works as built; the question
is whether "as built" is what you want when contracts ride on it.

## 1. The composite score is WEALTH-BLIND (ranking, not selection)

Wealth (ring median home value / HHI) decides which parcels are *needles* (the wealth_gate:
HV≥475k + HHI≥100k), but once a parcel is in the pool, its **deal score ignores wealth entirely**.
Current score factors: base 50 · permitted +30 / conditional +15 / prohibited −25 · acres ≤+20 ·
traffic AADT ≤+15 · flood −25 · wetland −15 · vacant +5 · listed +15.

**Implication:** a 96-score parcel in a $480k ring ranks above a 90-score parcel in a $1.6M ring.
If ring wealth should *rank* deals (not just gate them), we'd add a graduated factor (e.g.
+0..+15 scaling from $475k → $1M ring HV). **Recommendation: add it** — the thesis is
wealth-pocket-first, and the score should agree with the thesis when you're choosing which 5 of 50
deals to pursue. Small, contained change in `buybox_scoring.score_for_parcel`.

## 2. The $475k ring-HV gate — evidence from this cycle

The gate excluded genuinely-industrial towns at: Eden Prairie MN $449k · Pittsburgh cluster
$297–384k · Bloomfield Twp MI $367k · Burlington NJ tail $356–412k. All correct under the current
thesis (suburban coastal wealth), but note the *shape*: $449k Eden Prairie is 5% under the bar;
Pittsburgh is 20–40% under. Options:
- **Keep $475k (default/recommended):** the thesis is premium pockets; the misses are mostly deep, not marginal.
- **Drop to $450k:** re-admits Eden Prairie (+its I-2/I-5 industrial) and little else. Cheap re-score.
- **Per-metro calibration:** more honest long-term (a $384k Pittsburgh ring is top-decile locally)
  but adds a knob to maintain — defer until a non-coastal metro actually matters to the plan.
Also parked here: the 1.5ac floor (urban-infill question, unchanged).

## 3. Score floors + alert thresholds (as-built, for awareness)

- Daily digest includes parcels ≥40 score (≥70 when the filter sets requireListed).
- Instant on-upload alerts fire at ≥85 only.
- Digest tiers: **Actionable** (zero soft flags) vs **Worth a Look** (any of: has-building,
  no-price, conditional-zoning, confidence<0.70, flood, wetland, acres-unverified). Your Hot-Deals
  emails now carry Actionable only; WAL held in-app (config applied; code activates on PR merge).
- Note conditional-zoning is a *soft flag* → most conditional-verdict needles will land in the held
  Worth-a-Look tier, not the email. If you want conditional needles (the majority of the map — the
  ss/mw-conditional convention) in the email, we should drop `soft_conditional` from the demotion
  list or add a filter knob. **Flagging because it materially shrinks what emails.**

**Asks:** (1) yes/no on the wealth ranking factor; (2) keep $475k or drop to $450k; (3) should
conditional-verdict needles email as Actionable, or stay held?
