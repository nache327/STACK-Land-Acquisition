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

## Historical context (project inception → May 29, 2026)

*Ported verbatim from the canonical May 29 memo (catch #24 final port). The original WHY/HOW below is the
project's founding framing; the current WHY/HOW and the 4-stage pipeline framework above supersede it for
day-to-day work, but this is the authoritative record of how the system was built.*

### The WHY (original) — what this whole thing is for

You are Nache Nielson at Stack Storage. You are building premium storage condo developments modeled on LuxeLocker, targeting Northeast and Mid-Atlantic wealth pockets specifically.

The strategic anchor is the 14-year plan:
- **115 sites by 2040**
- **~$3.1B cumulative revenue**
- **~$885M cumulative profit**

This is a single-customer enterprise (you) building a tool to feed your own development pipeline. Every architectural choice in ParcelLogic exists to surface buildable land that fits this thesis — vacant parcels in wealth-dense corridors where a storage condo development can be entitled, built, and operated profitably under the LuxeLocker premium positioning.

The 57 KMZ wealth pockets are the geographic targeting universe. Northeast / Mid-Atlantic. Anything outside that is Phase D, deferred.

### The HOW — the original architecture (the four-layer system)

ParcelLogic was designed as a layered system, each layer feeding the next:

**Layer 1 — Parcels + Zoning.** Per-parcel zoning classification. Parcels ingested from county ArcGIS / NJOGIS / state cadastral services. Zoning verdicts via spatial join of zoning polygons + per-jurisdiction zone-use matrix. The matrix maps zone codes to self-storage permission (permitted / conditional / prohibited / unclear).

**Layer 2 — Market Saturation.** Storage square footage per capita in drive-time isochrones. Flags oversupplied markets. Census ACS tracts + Mapbox drive-time isochrones produce per-parcel rings at 2/5/10/15-min drive times with population, median HHI, home values, HNW household counts.

**Layer 3 — Buy-Box Scoring.** Server-side scoring against configurable filters. Parcels pass through hard filters (acres, price, demographics) and get a composite score. Hard filters are non-negotiable; scoring is continuous.

**Layer 4 — For-Sale Listings.** CoStar / LoopNet / Crexi listings matched to parcels via address normalization. Hot Deals digest sends top-10 buy-box matches daily at 12:00 UTC to your inbox. Two-tier output: Actionable (clean) and Worth a Look (soft-flagged).

The strategic insight: zoning is the bottleneck. Parcels are cheap to ingest at scale (ArcGIS feeds). Demographics are free (Census). Listings are commercial (CoStar pulls). But zoning is per-municipality, often PDF-only, and every new jurisdiction means matrix adjudication work. That bottleneck is why the matrix-sprint cadence dominated the first month of work.

### The arc — what we shipped, in order (Phases 1–6)

**Phase 1: Tactical deal unblock.** A specific Westampton parcel (`0337_201_10` at Rancocas Bypass) needed zoning resolution. Discovered the polygon-only PDF problem (Westampton's zoning map has zones drawn but no machine-readable boundaries). Manual SQL override unblocked the deal. Surfaced the architectural problem: per-jurisdiction zoning matrix needed real infrastructure, not deal-by-deal patching.

**Phase 2: Architecture primitives.** NJDCA Municipal Zoning Directory ingested as `zoning_sources` seed (1,092 rows across all 565 NJ munis — ordinance URLs, map URLs, contacts). Established the registry pattern: per-jurisdiction source of truth before any matrix work.

**Phase 3: Matrix sprint cadence.** Operationalized three jurisdictions in sequence, each refining the playbook:

- **Howard MD (P0)** → 96.3% operational. Established the brief→verify→promote three-pass QA chain. Added overlay schema (`base_zone_code` + `overlay_codes TEXT[]`), `cited_subsection`, `conditions_json` (B-2 indoor-only conditional rule with 5ac + public utilities requirement). Built the alias_mappings table for 72 typo aliases.
- **Loudoun VA (P0)** → 85.4% then 100% via 1993 ordinance crosswalk. Reused all Howard MD primitives. Added `sub_areas_eligible` (TRC Outer Core, TC Fringe, PD-RV Commercial/Workplace). 88K legacy 1993-ordinance parcels recovered via the official Loudoun crosswalk PDF. Vocabulary differs: Loudoun calls it "Mini-Warehouse."
- **Allentown PA (P1)** → 100%. Three-witness moment for vocabulary normalization ("Self-Service Storage" vs Howard's "Self-Storage Facilities" vs Loudoun's "Mini-Warehouse"). Spawned the `vocabulary_aliases` table. Surfaced that the 2025 LCZO is materially more restrictive than the 2015 ordinance.

**Phase 4: Pipeline correctness.** May 25 audit revealed the matrix work wasn't translating to digest output:
- 48.6% violation rate across digest deals (sub-floor acres, over-ceiling prices)
- Zero deals from Howard / Loudoun / Allentown in 14 days despite ~241K operational parcels
- Dedupe broken — same deals re-appearing across alerts and daily digests
- Tier system inconsistent across days

Four fixes shipped and verified end-to-end: cron timeout (`long_running_session_maker`), `listing_alerts.py` guardrail bypass, 14-day dedupe rule, NULL flood-flag coercion. CTE rewrite gave 78x query speedup (69s → 0.9s). Hot Deals digest confirmed working — Loudoun deal landed May 23, Howard MD May 26.

**Phase 5: Per-city architecture pivot.** The structural breakthrough. A county becomes a single jurisdiction (SLCo's 397k parcels, Burlington's 175k) with `parcels.city` carrying the actual municipality. The matrix is municipality-aware end-to-end via `zone_matrix_crosswalk` service. This retroactively solves Loudoun's 19K TOWNS parcels, NJ's 565 munis (via NJDCA seed), and the whole "many small jurisdictions" overhead.

Combined with the server-side ring precompute (998k rows in 2:15 for SLCo, auto-fires on county ingest, math parity locked with 12 regression tests), the user-facing surface became materially faster. Dashboard loads instantly for cached counties.

**Phase 6: Coverage reconciliation + data quality.** Asking the right strategic questions:
- Where are we against the 57 KMZ wealth pockets?
- The Worth-a-Look digest produces zero matches because `has_structure` is NULL on every SLCo parcel — data quality issue, not thesis problem
- LIR PROP_CLASS backfill is the fix (same source already powers zoning fallback)

### Architectural primitives shipped — the toolbox built along the way

This is the inventory of generalizable infrastructure that compounds with every future jurisdiction:

1. `zone_use_matrix` with `municipality` column — supports per-city verdicts inside a county
2. `zone_matrix_crosswalk` service — copies sibling jurisdictions' matrices into county under municipality tags
3. `alias_mappings` table + `propose_aliases.py` heuristic helper — handles typos, hyphen-strips, ordinance-era variants
4. `vocabulary_aliases` table — same use class, jurisdiction-specific terminology (Mini-Warehouse / Self-Storage Facilities / Self-Service Storage / etc.)
5. `conditions_json` JSONB — structured conditional rules (min_acres, public_utilities, indoor_only, approval_path, sub_areas_eligible)
6. `sub_areas_eligible TEXT[]` — for zones with sub-zone restrictions (TRC Outer Core only, TC Fringe only)
7. `overlay_codes TEXT[]` — for overlay districts that modify base zone verdicts
8. `inherits_from` field — for ordinance cross-references ("M-2 inherits all M-1 by-right uses")
9. `parcel_ring_metrics` server-side cache with 90-day TTL — eliminates client-side Mapbox/Census fan-out
10. CTE-pre-narrowed daily_email query — drives from forsale_listings (~600 rows) instead of parcel_buybox_scores (~354K rows)
11. NJ MCD TIGER city backfill — populates `parcels.city` for all NJ MOD-IV jurisdictions
12. `last_email_sent_at` 14-day cooldown — prevents same-deal re-surfacing
13. Two-tier digest output — Actionable vs Worth a Look with structured soft flags (🏢 building, 💸 no price, ⚖️ conditional, ❓ low-confidence verdict, 📐 acres unverified)

### What changed about how we work (founding behavioral patterns)

Three behavioral patterns the system supported by May 29 that didn't exist at the start:

- **Audit-to-fix-to-verify cycle** as a known-good loop. Gmail audit → DB reconcile → ship → verify via fresh digest. Used twice (May 25 audit, May 27 cron verification), both produced real fixes.
- **Chrome reviewer pass** for ambiguous matrix verdicts. Three jurisdictions verified via direct Chrome reads against Municode / encodeplus (Howard MD §131.0, Loudoun §4.06.06 + Land Use Lookup tool, Allentown §660-37 Use Table). Catches PDF-parser ambiguities that batch ingest misses.
- **Per-city pattern via crosswalk service.** Single jurisdiction holds all parcels, matrix is municipality-tagged, ingest doesn't proliferate small jurisdictions. Solves the worst structural problem of the original architecture.

These three patterns are now institutional. Every future jurisdiction inherits them. (They have since been joined by the ingress/egress/meta validation discipline — see the catch ledger below.)

---

## Where we are today (2026-06-25)

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
