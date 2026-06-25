# ParcelLogic — Strategic Memo: the WHY and the HOW

**Canonical, in-repo copy.** Last refreshed **2026-06-25** (prior state: 2026-05-29).

> **Provenance / catch #24 closure.** This memo previously lived only in chat / Nache's local machine
> (see `backend/scripts/_drafts/_strategic_docs_reconciliation.md`), which let the strategic universe
> drift across partially-divergent copies. This file is the committed canonical version. The narrative
> for **Phases 1–6** (pre-2026-05-29) should be ported in from Nache's local copy where marked; the
> Phase 7–8, framework, ledger, and forward-looking sections below are written fresh from verified
> 2026-06 work. The authoritative target universe remains `docs/TARGET_MARKETS.md` (57 KMZ pockets).

---

## WHY — the thesis

ParcelLogic finds **needles in a haystack**: the handful of parcels inside wealthy suburban "pockets"
where self-storage / mini-warehouse / light-industrial / luxury-garage-condo ("The Keep" / LuxeLocker)
development is *both zoning-permitted and economically live* (currently for sale, right size, right
price, surrounded by wealth/density). The moat is **verdict truth at the municipality level** —
knowing, per parcel, whether the use is actually allowed by that town's ordinance — across ~57 target
wealth pockets that generic CRE tools treat as undifferentiated.

We do **not** optimize for sprint volume or county breadth for its own sake. One correctly-grounded live
needle in a Tier-1 pocket beats a thousand armed-but-dormant parcels. (See `project_thesis_and_workflow`.)

---

## HOW — the 4-stage pipeline (central organizing concept)

A wealth pocket produces **live deal-flow** (a Storage-Needles digest fire) only when **all four stages**
are present for its parcels. Diagnosing "why 0 needles" = finding the missing stage.

| Stage | What | Owner | Usual binding constraint? |
|---|---|---|---|
| **1 — parcels + zoning bind** | parcels ingested, `zoning_code` populated (≥70%) | Adam's op5 factory substrate, or Nache for new counties (Chester/Bucks via county_gis crosswalk) | sometimes |
| **2 — CoStar listings** | per-county upload → ingest → worker match | **Uniquely Nache** (CoStar access) | **YES — most common** |
| **3 — ring metrics precompute** | drive-time wealth rings; without it `ringHV=0` → wealth gate can't evaluate | System (worker, post-Stage-1) | **YES — common** |
| **4 — verdict apply** | eCode360 grab → muni-specific human-UPSERT on needle zones | Nache + Claude Code | the *finishing move*, not the bottleneck |

**Implicit Stage 5 — delivery gates.** Even with all 4 stages, the digest only emails a needle that also
clears: `match_confidence ≥ 0.85` (listing↔parcel trust), `score ≥ 70` (`_MIN_SCORE_LISTED`), the SN hard
filter (acres 1.5–15, ≤$7.5M total, ≤$2M/acre, ring HHI≥100k / HV≥475k / HNW≥4400 / pop≥50k), and the
dual dedup (`notified_at` + `notified_listings` 14-day). See catch #41.

**Recommended per-pocket sequence:** **1 → 3 → 4 (verify-first) → 2 → matches surface.**
**Highest-EV refresh:** a pocket already at Stages 1/3/4 with a *stale* Stage 2 — one fresh CoStar pull
activates dormant deal-flow (validated on Bergen NJ, 2026-06-25).

**Discipline lesson:** verdict paste alone does NOT produce deal-flow. Newtown/Willistown needles needed
all four stages warm; Bergen confirmed it end-to-end.

---

## Where we are today (2026-06-25)

*(Phases 1–6: port the pre-2026-05-29 narrative from Nache's local memo here.)*

### Phase 7 — PA county_gis scale-up
- Built the **PA county_gis crosswalk** (`JurisdictionConfig.city_override` + `muni_field`/`muni_name_map`)
  so PA parcel layers carrying only integer MUNI codes map to real municipality names.
- **Chester County** onboarded to full-county coverage (192,856 parcels, ~100% zoned after the catch #36
  cache-guard fix).
- **Bucks County** onboarded (parcels + zoning) — Main Line / Bucks corridor now in the operational set.
- Main Line corridor verdicts applied (Tredyffrin, East Whiteland, Willistown).

### Phase 8 — Production deal-flow loop
- Burlington NJ Hot Deal → real broker conversation (880 Route 73).
- **3 cross-corridor live needles** surfaced/delivered across the wealth corridors.
- **Tripwire automation** shipped (`armed_pool_tripwire.py`) — armed-pool monitoring, dynamic pool,
  shared dedup with the digest.
- **Bergen NJ Stage-2 refresh** (2026-06-25): 22 new / 337 updated / 73 dropped, 348/359 matched,
  281,646 re-scored → 2 live needles (Paramus HCC-2 fired; Fort Lee I-1 surfaced). Playbook validated.
- **Broker outreach briefs** for the live needles drafted (incl. voicemail/cold-call variants).
- **Email fly-to UX** deployed (deep-links land on the parcel) — compounds across all future alerts.

### Operational state
- **Tier-1 hand-verdicted munis:** Tredyffrin, East Whiteland, Willistown, Newtown Township (Bucks),
  Doylestown Borough (Bucks) — plus ~24 Bergen NJ munis from earlier sessions.
- **Armed pool:** 186+ parcels across 4 munis under tripwire monitoring.
- **Delivery chain:** digest cron verified **healthy** (force-fire test 2026-06-25); dual-dedup +
  match-confidence floor working as designed.

---

## Catch ledger summary (through #43)

10 institutional catches in 24–48h. Three discipline patterns now standing:

1. **Ingress validation** — bind-test after every ingest (#27, #34, #36).
2. **Egress validation** — query-divergence audits + force-fire tests (#39a–c, #40, #41).
3. **Meta-validation** — the discipline auditing itself (#42, #43).

| # | Lesson |
|---|---|
| 33–36 | PA county_gis infra: numeric MUNI codes, UPI APN field, city-override precedence, zoning force-flag |
| 37 | Idiosyncratic-invert: 5 munis × distinct verdict-bases; dashboard heuristic insufficient for binding |
| 38 | Same-name-wrong-county disambiguation (Bucks vs Delaware County Newtown) |
| 39a/b/c | Tripwire/digest divergence; dual-dedup stores; premature-staleness escalation (false-positive) |
| 40 | Test-before-escalate — run the cheap positive test before routing to another lane |
| 41 | Reverse-divergence — the **digest was correct**, the tripwire was wrong (not the alarming direction) |
| 42 | Authored-vs-committed — verify the patch is in the file + on the remote branch, not just written |
| 43 | Default-to-coordinate bias — confirm cross-lane is on the critical path before recommending it |

(Full entries: `feedback_discipline_catch_ledger` memory.)

---

## What's next

- **Fairfield CT corridor** — next pocket. Rings are cold → **run Stage-3 precompute first**, then a
  CoStar pull (a 2-step, unlike Bergen's 1-step refresh).
- **Norfolk MA + Mecklenburg NC** — following sprints.
- **DelcoGIS test (Radnor + Haverford)** — last-mile coverage question (host blocked from Nache's
  network; needs a reachable path).
- **Broker-conversion compound** — every live needle is a potential broker conversation; the outreach
  briefs + fly-to UX make each one cheap to action.

---

## Strategic deferrals (no proactive work)

- **Burlington NJ trio** (Medford / Mt Laurel / Moorestown) — waiting on adapter delivery.
- **Vessel Tech partnership** — passive.
- **Maryland MDP statewide** — passive.
- **Mount Laurel / Moorestown shapefiles** — GovPilot black-box; adapter pending.

---

*Maintainer note:* keep this file as the single committed strategic memo. Reconcile against
`docs/TARGET_MARKETS.md` (KMZ pocket list) on each major refresh.
