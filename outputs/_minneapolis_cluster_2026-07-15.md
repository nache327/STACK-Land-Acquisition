# Minneapolis cluster — grounding outcome (2026-07-15)

Ring-precomputed 4 of 5 jids (worker path, ≤2 at a time — all small, finished in seconds).
acres were freshly backfilled from geom (the acres=0 defect), so the needle gate is live.
NEEDLE gate = dt10 `median_home_value ≥ 475000` AND `median_hhi ≥ 100000`, acres ≥ 1.5, grounded human
self_storage ∈ {permitted, conditional}. No re-score / CoStar (per instructions).

## Per-city outcome
| City | jid | ring | gate (dt10 HV≥475k) | in-ring industrial | result |
|---|---|---|---|---|---|
| **Eden Prairie** | 455b6dac | done (22,956) | **FAILS — HVmax $449k** | I-2/I-5/I-GEN exist | **correct NO-OP** (sub-$475k ring) |
| **Plymouth** | 7cc5f175 | done (28,001) | passes (14,454) | **I-1=16, B-C=6, O=11** | **needle — BLOCKED on Municode** |
| **Minnetonka** | 3267204b | done (20,911) | passes (2,631) | none (R-1/PURD + B-1/B-2=7) | near-no-op; B-1/B-2 Municode-blocked |
| **Edina** | 2b08fa13 | done (19,927) | passes (708) | none (in-ring = R-1 only, 9) | **correct NO-OP** |
| **Wayzata** | 1729467c | not fired | — | zoned=0, pure-residential | **correct NO-OP** (no zoning, no industrial) |

## Detail / reasoning
- **Eden Prairie — correct no-op (sub-$475k ring).** It IS a real industrial suburb (I-2 193 / I-5 28 /
  I-GEN 9 parcels ≥1.5ac) and rich by income (dt10 HHI avg ~$128k, all pass). BUT its dt10 ring
  `median_home_value` **maxes at $449,227 — never reaches the $475k gate** (HVpass = 0 / 22,956). So
  0 wealth-gated needles structurally, regardless of zoning. Same lesson as Burlington NJ / Fairfield
  sub-$475k. The "best needle potential" expectation was based on industrial presence; the wealth-ring
  HV gate is the binding constraint. Not grounded (would be 0 needles).
- **Edina — correct no-op.** Gate-clearing (708 pass) but the in-ring ≥1.5ac pool is entirely **R-1
  single-family residential** (9 lots); Edina's office/industrial sits outside the wealth ring
  (Hudson lesson). Not grounded.
- **Minnetonka — near-no-op.** Gate-clearing (2,631 pass) but **no in-ring industrial** — in-ring ≥1.5ac =
  R-1 (102) / PURD (29) / PUD (17) residential + a handful of commercial **B-1 (3) + B-2 (4) = 7**. The only
  possible needle is self-storage in B-1/B-2, which needs the ordinance (Municode-blocked). Effectively a no-op.
- **Wayzata — correct no-op.** zoned=0 (would need a bind) AND pure-residential (as expected). No industrial
  regardless; not worth binding. Ring not fired (moot without zoning).

## ⛔ Plymouth — the one real needle, BLOCKED on Municode
Gate-clearing with real in-ring industrial/flex: **I-1 Light Industrial = 16**, **B-C Business Campus = 6**,
**O Office = 11** (in-ring ≥1.5ac). #38: **P-I (43) = Public/Institutional, NOT industrial**; PUD (188) is
heterogeneous (skip). Ordinance = **Municode Ch. XXI (Zoning)**. **Municode content-API is inaccessible this
session**: the client-lookup endpoints (`Clients/name/{name}`, `Clients/stateAbbr/MN`, `Clients`) all now
return **HTTP 404** (the API structure changed since the South Brunswick pass that used client 7740), so I
could not obtain Plymouth's integer `clientId` to enter the working `Products/clientId/{id}` → `Jobs/latest`
→ `CodesContent` sequence. curl+UA gets only the SPA shell; WebFetch 403s the city site. Did NOT naive-read
Zoneomics or guess verdicts (#37 verbatim required; New Rochelle NY-schedule lesson).
**Next pickup:** obtain Plymouth's Municode clientId (browser network tab or a fixed API route) OR paste the
Ch. XXI **I-1 permitted/conditional use list + B-C + O** → then ground (warehouse-by-right ⇒ ss/mw conditional
convention unless self-storage separately named/confined; closed-list sweep). Same for Minnetonka B-1/B-2.

## Handoff to coordinator
- **Grounded needles this session: 0.** Eden Prairie / Edina / Wayzata = correct no-ops (logged). Plymouth
  (~16–33 candidate) + Minnetonka (~7) are Municode-blocked, pending ordinance.
- **Value delivered:** ring-precomputed Eden Prairie / Plymouth / Minnetonka / Edina (permanently unblocks
  the wealth gate on these jids); definitive no-op determinations; Plymouth/Minnetonka needle candidates
  pinned for a Municode-unblock follow-up. Hennepin county jid NOT touched (coordinator-gated).
