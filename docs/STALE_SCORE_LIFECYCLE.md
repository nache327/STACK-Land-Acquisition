# Stale-score lifecycle

How re-scoring fits into the operator workflow without becoming a constant
churn machine. Iteration 3 of the Spatial / CRS lane — companion docs
for `_score-health`, `_rescore-stale-sources`, `_rescore-rollback`.

## When a row becomes (re-)eligible for rescore

Single primitive: `stale_score_remediation.rescore_eligibility(row, ...)`.
A row is eligible when **any** of these is true; otherwise it stays out of
the queue:

| Reason | Detection | Severity | Common cause |
|---|---|---|---|
| `scoring_version_lower` | row's breakdown lacks any marker from `SCORING_VERSION_MARKERS[current_version]` | high | scoring schema bumped (v1→v2 added Component F on 2026-05-12) |
| `jurisdiction_bbox_refreshed` | `jurisdiction.bbox_updated_at > row.updated_at` | medium | parcel ingest refreshed the bbox; Component F was computed against stale bounds |
| `denylist_url_not_reflected` | `row.zoning_endpoint ∈ denylist` AND breakdown lacks `denylist_rejected` | medium | operator rejected the same URL in another jurisdiction since this row was scored |
| `age_exceeds_max` | `row.updated_at` older than `max_age_days` (default 90) | low | safety net for upstream publisher changes we can't detect from metadata alone |

Reasons are evaluated **in order** — `scoring_version_lower` always wins
over the others for the same row, since version drift implies every other
signal is computed under the wrong rules anyway.

### What does NOT make a row stale (by design)

- `validation_status == verified` — operator decisions are durable.
  Verified rows are reported in `not_eligible` regardless of other
  signals; the rescore endpoint never mutates them.
- `validation_status == rejected` — same: operator's reject is durable;
  Component D will keep applying to any new candidates pointing to the
  same URL via the denylist.
- A row whose live spatial verdict changed at the upstream service.
  Without a per-row probe, we can't detect this cheaply. The
  `_spatial-audit` endpoint (iteration 1) covers it on operator demand;
  we do NOT poll it on a schedule.

## What runs automatically vs operator-mediated

| Action | Mode | Frequency | Rationale |
|---|---|---|---|
| `GET /_score-health` dashboard poll | **automated**, read-only | once per dashboard load + every 10 min if visible | DB-only; ~ms per jurisdiction. Cheap enough to embed in the operator screen. |
| `GET /admin/score-health` morning report | **automated**, read-only | daily, optionally cron-emailed | one indexed scan; tells the operator if Bergen drifted overnight |
| `GET /_spatial-audit` per-jurisdiction probe | **operator-triggered** | on-demand | fans out HTTP probes; can hit ArcGIS quota |
| `POST /_rescore-stale-sources` (dry-run) | **operator-triggered** | per investigation | same probe cost; reveals the actual delta |
| `POST /_rescore-stale-sources` (live) | **operator-triggered**, never automated | weekly per priority county, otherwise as drift surfaces | mutates `confidence_*` fields; should never run without a saved snapshot |
| `POST /_rescore-rollback` | **operator-triggered** | rare, only when a rescore caused regret | safety valve; takes the snapshot the live run returned |
| Bumping `SCORING_VERSION` | **operator-triggered** | on intentional scoring change | manual constant bump in `zoning_discovery.py` + commit; staleness propagates automatically |

The hard rule: **no automated writes to zoning_sources.** Everything that
mutates rows requires a deliberate operator call. The automated surface
is strictly read-only metrics and dry-run reports.

## Recommended cadence

### Daily (cheap — no probes)

- `GET /admin/score-health` — read aggregate eligibility counts; operator
  flags any jurisdiction whose `eligible_total` jumped overnight (usually
  signals a fresh parcel ingest refreshing the bbox).

### Weekly (per priority county, one at a time)

1. `GET /jurisdictions/{id}/_score-health` — confirm there's something
   worth rescoring (eligible_total ≥ 10 is the rough trigger).
2. `python scripts/rescore_stale_sources.py {id}` — dry-run.
3. Inspect `summary.newly_below_threshold_70`, `summary.live_verdict_disjoint`,
   and the per-row deltas.
4. `python scripts/rescore_stale_sources.py {id} --apply --snapshot-out
   rescore-{county}-$(date +%s).json` — apply, keep the snapshot for at
   least 7 days.

### After a scoring-version bump

1. Bump `SCORING_VERSION` in `zoning_discovery.py` + commit.
2. Every persisted row is now reported as `scoring_version_lower` until
   re-scored. `GET /admin/score-health` shows the universe-wide impact.
3. Operator works through the priority counties in order (Bergen first,
   then NJ counties with active discovery sweeps, then long-tail).

### Reactive — operator rejects a generic FP URL

When the operator bulk-rejects a URL that recurs across jurisdictions
(e.g. a Florida zoning layer that was matching every NJ "Park"-suffixed
town), Component D's `denylist_rejected = -80` should now fire for every
other row that points to that URL. `_score-health` flags those rows as
`denylist_url_not_reflected` — rescore the affected counties next.

## Cost analysis

| Operation | DB cost | HTTP cost | Wall-clock (Bergen ≈ 710 rows) |
|---|---|---|---|
| `_score-health` (one jurisdiction) | 1 indexed scan | 0 | <100 ms |
| `_score-health` (cross-jurisdiction) | 1 indexed scan over all | 0 | ~1 s for 70+ counties |
| `_rescore-stale-sources` (dry-run, 200 rows) | 1 indexed scan | 200 probes @ concurrency 8 | 30-60 s, dominated by upstream ArcGIS |
| `_rescore-stale-sources` (live, 200 rows) | + 1 UPDATE per changed row | same | same |
| `_spatial-audit` (one jurisdiction, with district stats) | 3 small queries + audit fanout | up to N probes | proportional to row count |

The probe cost is the dominant operational concern. Rough envelope:
60 probes/min sustained (concurrency 8, p50 latency ~1 s per upstream
layer). Bergen's ~700 rows = ~12 min if probed in full. We never need to:
ban `stale_only=False` rescore unless the operator is investigating a
specific concern; the eligibility filter keeps the working set small.

## Risk analysis

### Risks we accept

- **A row that's eligible but rescored to the same score.** Cost is one
  probe + one UPDATE that changes only `updated_at`. Annoying but harmless;
  filtered out of `changes` by the `is_no_op` check.
- **A row eligible by `age_exceeds_max` whose upstream layer hasn't
  changed in 91 days.** Same cost; no behavior change. Operator can set
  `max_age_days=null` if this becomes noisy.

### Risks we mitigate

- **Verified-row corruption.** Already enforced — `_MUTABLE_STATUSES =
  {pending, needs_review}` is the single gate. Three layers of test cover
  it (`test_live_mode_never_mutates_verified_rows`,
  `test_recompute_preserves_verified_label_regardless_of_score`,
  `test_rollback_skips_rows_that_were_verified_after_rescore`).
- **Cascade rescores destabilizing operator queues.** Bounded by
  `max_rows` (server cap 1000) + the eligibility filter + the
  operator-only write path. Drift is visible via `_score-health` long
  before it becomes a queue-flood.
- **Snapshot loss on apply.** The CLI script refuses `--apply` without
  `--snapshot-out`. The endpoint returns the full `before` payload in
  the response either way; the operator can recover from any client
  that saved that JSON.

### Risks we explicitly DO NOT mitigate

- **A scoring-version bump that flips a verified row's recomputed score
  below 70.** Verified status is durable; the row stays verified, the
  recomputed score doesn't apply. The operator may want to unverify if
  the new score is genuinely worse than the bar — but that's a manual
  call. We do not silently downgrade verified rows.
- **Upstream layer disappearing (404).** The live probe records
  `verdict=error`; that row is flagged in `_spatial-audit` errors but
  the persisted score stays. Manual reject is the right response.

## Future work this design enables

- Adding a Component G next iteration → bump `SCORING_VERSION` to 3
  + extend `SCORING_VERSION_MARKERS[3]` with the new marker name. Every
  v1/v2 row immediately becomes eligible without code changes elsewhere.
- A separate Railway cron that calls `/admin/score-health` once daily
  and emails the operator the eligibility deltas (a few lines on top of
  the existing `daily_email` worker pattern; not built this iteration).
- Adding a `scoring_version` integer column to `zoning_sources` if the
  marker-inference approach ever produces ambiguous answers (currently
  it doesn't — every v2 marker is unambiguous, and future versions can
  keep that invariant).
