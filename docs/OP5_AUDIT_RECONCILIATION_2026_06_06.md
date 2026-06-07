# Op-5 Audit Reconciliation — 2026-06-06

**Owner:** Master Planning Thread
**Source:** `/tmp/operational_count_reconciliation.md` (orchestrator analysis)
**Decision:** Accept API as truth — honest operational count is the operational definition.

---

## Headline

The master tracker has been carrying **45 → 47 operational jurisdictions** since May-31 close. The current prod API reports **15 operational** (which drops to **13** after two stale-snapshot anomalies refresh). The 30-jurisdiction gap is **not a regression and not a bug** — it is the consequence of three audit-logic tightenings that landed in late May.

**The lower count is the honest one.** We tightened the gates deliberately; this is the operational definition we chose.

---

## What tightened (and when)

| Gate | PR / location | Effect |
|---|---|---|
| `parcel_zoning_code_coverage_pct ≥ 70%` | PR #98 (`a29b86e`, 2026-05-26) | Requires real parcel-level zoning coverage before claiming operational |
| `no_zoning_polygons` blocker | `backend/scripts/audit_zoning_coverage.py:427-443` | Parcel-source-zoned jurisdictions need `matrix_zone_match_pct ≥ 90%` to be exempt from polygon requirement |
| `high_unclear_self_storage_share` blocker | `backend/scripts/audit_zoning_coverage.py:423` | Fires when ≥5% of matrix-matched parcels carry `unclear` self_storage verdict |

All three were intentional. PR #98 was the truthfulness pass that the master thread explicitly drove. The `no_zoning_polygons` exception logic and `high_unclear_self_storage_share` were established quality bars.

---

## What dropped (34 silent downgrades since May-31)

### 29 Utah cities — `no_zoning_polygons`

These cities had operational labels via parcel-level zoning data (UGRC + tax-assessor) without a backing zoning polygon layer. Under the post-PR-#98 rules, they need `matrix_zone_match_pct ≥ 90%` to qualify for the polygon-exception. They don't clear that bar.

| Affected | Recovery path |
|---|---|
| American Fork, Bluffdale, Cedar Hills, Cottonwood Heights, Eagle Mountain, Herriman, Holladay, Hurricane, Ivins, Kaysville, Lindon, Midvale, Millcreek, Murray, North Salt Lake, Ogden, Orem, Pleasant Grove, Provo, Roy, Sandy, Santa Clara, Saratoga Springs, South Jordan, Spanish Fork, Springville, Taylorsville, Tooele, Washington, West Haven, West Jordan, West Valley City | Op-5 polygon work per city (operator-assisted, ~30 min/city × 29 = ~15-30h spread over weeks) |

### 1 Somerset County, NJ — `high_unclear_self_storage_share`

Lane E's Somerset matrix work (PR #91) introduced too many `unclear` verdicts (≥5% of matrix-matched parcels). Recoverable.

**Recovery:** Lane E unclear-row cleanup pass. Estimated ~2-3h. Same pattern as Norfolk MA / Middlesex MA / Bergen but operating on existing unclear matrix rows rather than net-new codes.

### 1 Allentown, PA — `high_unclear_self_storage_share`

Same class as Somerset. Same recovery path.

---

## What was added (4 since May-31)

| Jurisdiction | Status | Note |
|---|---|---|
| **Bergen County, NJ** | ✅ Legitimate flip via PR #184 (2026-06-05) | cov=99.8%, matrix=247 zone codes |
| **Morris County, NJ** | ✅ Legitimate flip via PR #186 (2026-06-06) | cov=100%, matrix=186 zone codes |
| Essex County, NJ | ⚠️ Stale snapshot anomaly | Audit captured 2026-05-12; coverage 23.8% (below 70% gate); **will drop to partial on refresh** |
| Draper City, UT | ⚠️ Stale snapshot anomaly | Audit captured 2026-05-12; coverage 65.9% (below 70% gate); **will drop to partial on refresh** |

---

## True operational count

| Count | Definition |
|---|---|
| **15** | What the API currently returns (includes 2 stale anomalies that will drop) |
| **13** | After Essex + Draper refresh under post-PR-#98 rules |
| **15** | Honest baseline + 2 new flips (Bergen + Morris) — using 13 as baseline + 2 confirmed flips |

**The master tracker's 45 → 47 figure was based on deprecated rules.** It is being corrected to 13 baseline + 2 new flips = 15 in this PR.

Bergen and Morris are correctly classified additions under the new rules.

---

## Customer-facing narrative

The discrepancy was **internal master-tracker drift, not customer-facing.** The product API has been returning the honest count the entire time; customer dashboards have rendered reality. The "45" figure only existed in our internal docs and KPI claims.

When investors/customers ask about coverage, the defensible story is:

> *"In late May we shipped a truthfulness pass that tightened our operational definition. We now require ≥70% parcel zoning coverage backed by validated zoning polygons and <5% unclear verdicts on matrix rows. Under the new bar, we recount honestly: 13 operational counties at baseline. This week we added 2 more (Bergen + Morris). Jurisdictions like Salt Lake-area cities and Somerset NJ that previously counted as operational are now classified as partial — same underlying data, stricter trust signal. We're recovering them via targeted quality work."*

That's a discipline story, not a regression story.

---

## Recovery priorities

| Priority | Target | Cause | Effort | Expected gain |
|---|---|---|---|---|
| 1 | Somerset NJ | high_unclear cleanup | ~2-3h | +1 operational |
| 2 | Allentown PA | high_unclear cleanup | ~2-3h | +1 operational |
| 3 | Hunterdon NJ | matrix-completion (pending refresh) | ~2-3h | +1 operational |
| 4 | Monmouth NJ | high_unclear cleanup (quality-pass first) | ~3-5h | +1 operational |
| Deferred | Essex NJ | Cat-B per-town source acquisition | weeks | +1 operational |
| Deferred | Draper UT | Cat-B (coverage gap, not matrix) | TBD | +1 operational |
| Multi-week | 29 UT cities | Op-5 polygon work per city | ~15-30h spread | +29 operational |

**Realistic 1-week recovery path:** Hunterdon (sprint), Somerset (Lane E cleanup), Allentown (Lane E cleanup), Monmouth (Lane E cleanup post-diagnosis) = 4 added → total 19 operational by end of next week.

---

## What this PR does

1. Authors this reckoning doc
2. Updates `docs/PHASE2_PROGRESS.md` §1 KPI snapshot from `≥47` to honest **15** (= 13 baseline + Bergen + Morris)
3. Adds §15 changelog entry for 2026-06-06 documenting the reconciliation finding
4. Updates `coordination/lane_state.json` mode and `nj_tier_s_status` block

No backend, matrix, or UI changes. Tracker honesty + coordination state only.

---

## What this PR does NOT do

- Soften the audit gates (Option 2 — rejected)
- Maintain dual definitions (Option 3 — rejected)
- Backfill historical claims with the new count (the May-31 close was based on deprecated rules; preserved as historical baseline with note)
- Dispatch recovery work (queued for next sprints)
