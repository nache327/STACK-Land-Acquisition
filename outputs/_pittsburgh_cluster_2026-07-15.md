# Pittsburgh PA cluster (Phase 6) — DISCOVERY-RANK TRIAGE outcome (2026-07-15)

**Result: the entire cluster is a structural NO-OP — sub-$475k wealth-ring, cluster-wide.** Triage-first
(gate-check before ordinance fetch) resolved all 4 targets with **zero ordinance fetches and zero binds**.
NEEDLE gate = dt10 `median_home_value ≥ 475000` AND `median_hhi ≥ 100000`, acres ≥ 1.5. No re-score/CoStar.

## Threshold data (dt10 ring median_home_value — the binding constraint)
| City | jid | ring HVmax | gate pass | in-ring ≥1.5ac industrial | result |
|---|---|---|---|---|---|
| **O'Hara** | 58e12865 | **$384,012** | 0 / 2,940 | — (zoned=0; NOT bound) | correct NO-OP |
| **Sewickley** | abee4cb9 | **$356,254** | 0 / 1,115 | NONE | correct NO-OP |
| **Fox Chapel** | c5e04fa4 | **$329,097** | 0 / 1,485 | NONE | correct NO-OP |
| **Aspinwall** | ff1f473b | **$296,611** | 0 / 768 | NONE | correct NO-OP |

(Sewickley Heights [2d547740], zoned=0, ultra-residential — not in target list, not fired; same metro,
certain no-op.)

## Why — Pittsburgh-metro ring effect
These are income-wealthy enclaves, but the **10-minute drive-time ring** around each pulls in the broader
Pittsburgh metro, whose median_home_value is **$297k–$384k — nowhere near the $475k gate** (calibrated on
coastal/high-cost metros). So 0 wealth-gated needles regardless of zoning. Same structural lesson as Eden
Prairie MN ($449k), Burlington NJ, Fairfield sub-$475k. HHI is not the constraint here; **HV is**.

- **O'Hara** — the "best bet" (riverfront industrial, zoned=0). Gate FAILS (HVmax $384k) → **did NOT bind
  zoning** (would have been wasted effort on a structural no-op). Triage saved the bind + ordinance fetch.
- **Fox Chapel / Sewickley / Aspinwall** — already zoned; 0 in-ring ≥1.5ac industrial AND sub-$475k ring.

## Actions taken
- Ring-precomputed all 4 targets (worker path; ≤2 concurrent — a 4-way batch stalled 2 jids, re-fired as a
  clean pair, confirming the "stagger 2" rule). Threshold data now on record; jids unblock instantly if the
  gate is ever lowered for lower-cost metros.
- **No ordinance fetch, no GIS bind, no matrix writes** → nothing to verify_batch/gate (no verdicts grounded).
- Hennepin/Allegheny COUNTY jids untouched.

## Handoff to coordinator
- **Grounded needles: 0. All 4 Pittsburgh targets = correct no-ops (sub-$475k ring).** ring-HV thresholds
  logged above. Recommend: Pittsburgh cluster is DONE (no-op) under the current gate — no ordinance work
  warranted. If the wealth gate is ever recalibrated per-metro (Pittsburgh HV ceiling ~$384k), revisit
  O'Hara first (riverfront industrial, would then need a zoning bind).
