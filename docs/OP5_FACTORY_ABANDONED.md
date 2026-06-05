# Op-5 25-Agent Factory — Abandoned

**Owner:** Master Planning Thread
**Decided:** 2026-06-10
**Source artifacts:** `docs/OP5_PROOF_DECISION.md`, `docs/OP5_FACTORY_72H_PLAN.md`, `docs/OP5_PRE_BUILD_REPORT.md` (CP-Pre v1/v2/v3)
**Replaced by:** `docs/OP5_OPERATOR_TOOLKIT.md` + `docs/OP5_OPERATOR_RUNBOOK.md`

---

## Decision

**ABANDON the 25-agent unattended Op-5 factory thesis.** Honor the hard-cap iteration constraint from CP-Pre v3:

> "Two more pre-build iterations maximum. If CP-Pre v3 review shows we still don't have green-path success on both an ArcGIS muni AND a PDF muni in Bergen, Master will abandon the 25-agent factory thesis and shift to operator-assisted Op-5 at scale."

CP-Pre v3 outcome: 0/2 green-paths validated (Westwood ArcGIS failed at ingest mapper; Ridgewood PDF blocked at TIGER WAF). Strict reading of the cap applies.

---

## The cumulative evidence

Seven distinct issues surfaced across four iterations of factory pre-build, against only two attempted muni runs. The pattern itself is the signal — not any single bug.

| iteration | finding | what was discovered |
|---:|---|---|
| CP-Pre v1 | 1 | Supavisor session-mode pool capped at 15 clients → 25-agent factory loses ~44% of agents at connect time |
| CP-Pre v1 | 2 | A2 shipped runner with stubbed extraction/ingest/backfill/audit defaults; pre-build PR was scaffolding-only |
| CP-Pre v1 | 3 | C1 shipped 0/140 `map_url` populated across the 4 new-county directories |
| CP-Pre v2 | 4 | `op5_town` tag collision risk — `normalize_muni_token('Garfield city')` collides with proof state `op5_town='garfield'` tag |
| CP-Pre v2 | (1 runtime) | Census Geocoder onelineaddress doesn't resolve plain place names → swapped to TIGERweb REST |
| CP-Pre v2 | (2 runtime) | PDF render at 300 DPI OOM-kills on oversized municipal maps (Westwood 48"×66" page = 285 Mpx) |
| CP-Pre v2 | (3 runtime) | Anthropic vision API rejects images > 10 MB raw — A2 sent 16.7 MB and got 400 |
| CP-Pre v3 | 5 | Missing ArcGIS classification path — Westwood was sent through PDF/vision pipeline though it's an ArcGIS-served muni |
| CP-Pre v3 | 6 | F5's ArcGIS adapter doesn't normalize FeatureServer field names to platform's `zone_code` → 0 polygons inserted from 3,686 downloaded |
| CP-Pre v3 | 7 | `default_audit_muni` returns jurisdiction-wide coverage % instead of muni-scoped → operational gate computation broken |
| CP-Pre v3 | TIGER WAF | TIGERweb rate-limits a session's repeated programmatic requests → Ridgewood PDF smoke never reached extraction |

## What the cumulative pattern says

The proof's pipeline succeeded on Fort Lee, Garfield, and Hackensack because each muni was run **manually with hand-tuned scripts** — an operator could probe the source, tweak the prompt, adjust DPI, swap the geocoder, normalize field names, etc. **The 25-agent factory thesis assumed that pipeline could be made unattended at scale.** The CP-Pre evidence does not support that assumption:

- Every iteration surfaces at least 2-3 new runtime-shaped bugs that the proof never hit because of the hand-tuning.
- Closing one bug reveals another underneath. Westwood: Census Geocoder broken → swap to TIGER → TIGER WAF blocks → ArcGIS field mapping wrong → audit scope wrong → on and on.
- Per-muni wall clock is dominated by failure handling, not work. Westwood (ArcGIS path) ran 388 s and produced 0 useful polygons.

The 72-hour budget assumed ~3.5 h per muni; even one runtime-bug-per-muni would blow that.

---

## What was kept

The four pre-build PRs (#177, #178, #179, #180) all merged 2026-06-04 as the operator toolkit. None of them are factory-specific:

- **PR #178** — F2 protect-list, F5 ArcGIS-first classifier, discovery classifier, per-muni runner shell (operator can invoke for classification + idempotency without trusting the heavy extraction)
- **PR #177** — `/admin/op5-review` page + backend route (critical for batch matrix sign-off, factory or otherwise)
- **PR #179** — 4 county directories (operator-facing data; the 18 discovered map_urls are real operator-actionable)
- **PR #180** — DB capacity report + check script (operator now knows the 14-concurrent ceiling)

Toolkit summary: `docs/OP5_OPERATOR_TOOLKIT.md`.

## What was abandoned

- The 25-agent unattended factory orchestrator dispatch (Phase 0 + Phase 1 + Phase 3 per `docs/OP5_FACTORY_72H_PLAN.md`).
- The throughput model ("120 munis/day" at 20 agents, "84 munis/day" at 14 agents).
- The unattended assumption that the proof's pipeline scales without per-muni hand-tuning.

## Alternative path adopted (2026-06-10)

1. **Immediate Bergen ArcGIS wins (~14 munis)** — direct ArcGIS ingest scripts per `docs/archive/BERGEN_INGEST_RUNBOOK.md`. Proof munis (Garfield/Fort Lee/Hackensack) promoted preview→prod. NJSEA Meadowlands 10. Westwood via direct ArcGIS with field mapping inlined. Paramus confirmed.
2. **Operator-assisted Op-5 for remaining Bergen PDF munis (~56)** — `docs/OP5_OPERATOR_RUNBOOK.md` (companion PR). Operator throughput 55-80 min/muni in QGIS. 2-3 weeks full-time or 4-5 weeks part-time.
3. **Non-Bergen NJ counties deferred** — Essex, Middlesex NJ, Monmouth, Burlington stay on the shelf until Bergen is complete.

## Classification of carried-forward bugs

| bug | source | classification | rationale |
|---|---|---|---|
| 6 — F5 ArcGIS field normalization | PR #178 ada866c | **Out of scope** — fix only if operator track reveals it blocking other work. | Operator's direct ArcGIS ingests inline the field mapping per BERGEN_INGEST_RUNBOOK.md, bypassing the runner. The bug only matters if someone tries to use the runner unattended on ArcGIS munis — which is the abandoned factory path. |
| 7 — Audit muni scoping | PR #178 ada866c | **Out of scope** — same rationale. | Operator queries `audit_zoning_coverage.py` with the right scope directly; per-muni-summary generation is a factory-only concern. |
| TIGER WAF | PR #178 117cfa6 + 7d0c4fb | **Out of scope** — proof's GENZ2024 shapefile approach is the right fix if needed later. Operator workflow doesn't depend on TIGER per-request. | |

If a future factory attempt re-opens, these are documented entry points.

---

## Cost / outcome accounting

| metric | value |
|---|---|
| Pre-build iterations consumed | 3 (CP-Pre v1/v2/v3) — within budget |
| Agent-hours expended | ~14 across F2/F5/A2/B/C/D agents + orchestrator-led fixes |
| Net code shipped to main (operator toolkit) | 4 PRs, ~9.5K LOC, all CI-green |
| Bergen factory munis unlocked by these iterations | 0 (factory thesis abandoned) |
| Bergen ArcGIS munis unlocked by direct-ingest follow-up | ~14 (immediate wins shipping in companion ticket) |
| Bergen PDF munis routed to operator | ~56 |
| Non-Bergen munis deferred | ~140 |
| Total Op-5 munis presumed operationally accessible post-toolkit + Bergen track | ~70 Bergen (immediate + operator) + 88 deferred non-Bergen + the 3 proof munis |

## Lessons recorded

1. **Hand-tuned proofs don't unattend-scale on first try.** Future automation pre-builds should require ONE end-to-end green-path on a real target before scoping a swarm.
2. **The cumulative-bug pattern is the signal, not any single bug.** Each iteration's bug count and shape should be tracked; rising count is the abandonment trigger.
3. **Pool/connection caps are infrastructure constraints that determine swarm sizing.** Should be measured before agent-count commitments are written into the plan.
4. **The proof's "always-good-enough" infrastructure (Census Geocoder, TIGER, vision-LLM at 300 DPI) was hand-curated; production code can't assume that durability.**

This file lives in `docs/` rather than `docs/archive/` so it's discoverable by future engineers considering similar factory automation. It is NOT a failure post-mortem — it's a successful application of the iteration cap discipline.
