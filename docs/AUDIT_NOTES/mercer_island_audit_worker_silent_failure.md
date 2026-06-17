# Mercer Island Audit Worker Silent-Failure Diagnostic

**Date:** 2026-06-16
**Trigger:** Mercer Island DB-level state is correct after Task E city-fallback ingest, but `/api/admin/coverage` remains stale at `2026-06-16T17:54:33Z` after 6+ refresh triggers over 2+ hours. Lane A reports DB-level Mercer metrics are already operational-shape: zoning coverage 79.6%, 130 districts, matrix match 94.8%, bbox populated.
**Scope:** Read-only code diagnostic. No code changes, ingest, matrix work, or audit refreshes.

---

## Verdict

The code read does **not** support the specific hypothesis that a non-empty `unmatched_zone_samples` JSON aggregate for 3 missing zone codes / 309 parcels creates exponential complexity versus Bellevue's empty aggregate.

The audit query does have a real targeted-refresh pathology: `backend/scripts/audit_zoning_coverage.py` applies the jurisdiction filter only in the final `SELECT`, after the heavy CTEs have already scanned and grouped all parcels and all matrix rows. A Mercer-targeted refresh therefore still runs county-scale / platform-scale `parcel_stats`, `distinct_parcel_zones`, `parcel_zone_matrix`, and `unmatched_zone_samples` work before discarding all but Mercer.

The service wrapper also still hides the actionable failure phase. It catches audit SQL/build exceptions, per-row snapshot insert exceptions, and final commit exceptions. The endpoint was improved to return 502 when `snapshots_written=0`, but the operator still only sees a stale snapshot and a generic 502 unless Railway logs are pulled.

**Primary fix recommendation:** add an early jurisdiction scope to the audit SQL for targeted refreshes, and re-raise targeted-refresh failures with the failing phase in the 502 body. If Lane A needs the fastest tactical unblock, add a targeted-only SQL path or inject a `target_jurisdiction` CTE and join every parcel/matrix CTE through it.

**Secondary verification recommendation:** pull Railway worker/API logs for the first targeted Mercer refresh after Task E. Code read can identify likely failure modes, but only logs can distinguish "audit SQL timed out/cancelled" from "snapshot insert failed" from "commit failed."

---

## CTE chain findings

### `parcel_stats`

Location: [backend/scripts/audit_zoning_coverage.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/scripts/audit_zoning_coverage.py:201)

Shape:

```sql
FROM parcels p
GROUP BY p.jurisdiction_id
```

Inputs that scale:

- every row in `parcels`, not just the requested jurisdiction;
- boolean/count filters over geom, zoning_code, zone_class, binding method, structure/flood/wetland flags.

Targeted-refresh issue:

- The final `WHERE lower(j.name)=...` appears only at lines 371-374, after this CTE has already aggregated all jurisdictions.
- A Mercer-only refresh still pays for all parcel rows in the database.

Exponential risk from Mercer unmatched codes: **NO.** This CTE does not touch matrix matches or JSON.

### `distinct_parcel_zones`

Location: [backend/scripts/audit_zoning_coverage.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/scripts/audit_zoning_coverage.py:215)

Shape:

```sql
FROM parcels p
WHERE p.zoning_code IS NOT NULL
  AND btrim(p.zoning_code) <> ''
GROUP BY p.jurisdiction_id
```

Inputs that scale:

- every zoned parcel in all jurisdictions;
- distinct `zoning_code` cardinality per jurisdiction.

Targeted-refresh issue:

- No early jurisdiction predicate, so targeted refresh still scans all populated zoning codes.

Exponential risk from Mercer unmatched codes: **NO.** Distinct aggregation grows with zoned parcel count and distinct code count, but 3 additional unmatched codes is linear/cardinality-small.

### `matrix_stats`

Location: [backend/scripts/audit_zoning_coverage.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/scripts/audit_zoning_coverage.py:225)

Shape:

```sql
FROM zone_use_matrix zum
WHERE zum.deleted_at IS NULL
GROUP BY zum.jurisdiction_id
```

Inputs that scale:

- all live `zone_use_matrix` rows across all jurisdictions.

Targeted-refresh issue:

- No early jurisdiction predicate.

Exponential risk from Mercer unmatched codes: **NO.** It is matrix-row cardinality only. Mercer having 3 unmatched parcel codes does not change this CTE materially.

### `parcel_zone_matrix`

Location: [backend/scripts/audit_zoning_coverage.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/scripts/audit_zoning_coverage.py:245)

Shape:

```sql
FROM parcels p
LEFT JOIN zone_use_matrix zum
  ON zum.jurisdiction_id = p.jurisdiction_id
 AND zum.zone_code = p.zoning_code
 AND zum.deleted_at IS NULL
GROUP BY p.jurisdiction_id
```

Inputs that scale:

- every parcel row;
- every nonblank `zoning_code` lookup into `zone_use_matrix`;
- join fanout if duplicate live matrix rows exist for a `(jurisdiction_id, zone_code)` pair.

Targeted-refresh issue:

- This is the most likely CTE-level cost center. It scans all parcels and joins into matrix rows for every jurisdiction even when the endpoint asked for one small per-muni jurisdiction.
- `backend/app/db.py` documents a prior Hunterdon failure where this CTE "blew the plan" at 165 distinct zone codes and 51,751 uncovered parcels, prompting the long-running engine bump to 3600s at lines 102-107.

Exponential risk from Mercer unmatched codes: **NO for 3 codes / 309 parcels.** The join is linear-ish in parcel rows and lookup cost, plus any duplicate matrix fanout. Mercer having a small non-empty unmatched set should not be a qualitative jump from Bellevue. The broader query can still be slow because it is not scoped early.

### `unmatched_zone_samples`

Location: [backend/scripts/audit_zoning_coverage.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/scripts/audit_zoning_coverage.py:298)

Shape:

```sql
SELECT sample.jurisdiction_id,
       json_agg(sample.zoning_code ORDER BY sample.parcel_count DESC, sample.zoning_code)
FROM (
  SELECT p.jurisdiction_id,
         p.zoning_code,
         COUNT(*) AS parcel_count,
         ROW_NUMBER() OVER (
           PARTITION BY p.jurisdiction_id
           ORDER BY COUNT(*) DESC, p.zoning_code
         ) AS rn
  FROM parcels p
  LEFT JOIN zone_use_matrix zum
    ON zum.jurisdiction_id = p.jurisdiction_id
   AND zum.zone_code = p.zoning_code
   AND zum.deleted_at IS NULL
  WHERE p.zoning_code IS NOT NULL
    AND btrim(p.zoning_code) <> ''
    AND zum.zone_code IS NULL
  GROUP BY p.jurisdiction_id, p.zoning_code
) sample
WHERE sample.rn <= 10
GROUP BY sample.jurisdiction_id
```

Inputs that scale:

- all zoned parcels across the database;
- unmatched distinct zone codes per jurisdiction;
- top-10 JSON aggregation per jurisdiction after grouping.

Targeted-refresh issue:

- Again, there is no early jurisdiction predicate.
- The JSON aggregate itself is capped to at most 10 strings per jurisdiction. The expensive work is the all-jurisdiction anti-join and grouping before the JSON aggregate, not the JSON output.

Exponential risk from Mercer unmatched codes: **NO.** A non-empty JSON aggregate of 3 codes is tiny. It should not be meaningfully different from Bellevue's empty aggregate except that the anti-join emits three grouped rows for Mercer. If this CTE is involved in the stall, the reason is unscoped all-jurisdiction work or a bad anti-join plan, not JSONB/JSON aggregation size.

Reference comparison:

- `backend/app/api/admin_op5_uncovered.py` implements the same uncovered-code logic for an operator endpoint, but it scopes early with `WHERE p.jurisdiction_id = :jurisdiction_id` at lines 138 and 164. Its comments say the `(jurisdiction_id, zoning_code)` parcel index keeps the bounded query fast for Bergen-sized data.

---

## Refresh invocation path findings

### Actual SQL query

Location: [backend/app/services/coverage_audit.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/services/coverage_audit.py:126)

`refresh_all_snapshots()` imports `audit_zoning_coverage`, opens `long_running_session_maker`, then executes:

```python
result = await conn.execute(
    az._build_audit_sql(schema),
    {"jurisdiction_name": jurisdiction_name},
)
audits = [az._build_audit(row, schema) for row in result]
```

The only filter passed to the SQL builder is `jurisdiction_name`, which is applied in the final `WHERE` clause inside `_build_audit_sql()`. The SQL builder has no `jurisdiction_id` parameter and no early target scope.

### Timeout behavior

Relevant locations:

- [backend/app/services/coverage_audit.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/services/coverage_audit.py:60)
- [backend/app/db.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/db.py:96)
- [backend/app/services/coverage_audit.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/services/coverage_audit.py:115)

Findings:

- Audit reads use `long_running_session_maker`, whose engine is configured with asyncpg `command_timeout=3600`.
- The wrapper runs `SET LOCAL statement_timeout = 0` before the audit SQL.
- The injected request `db` uses the default 90s command timeout, but only for snapshot inserts/flush/commit, not the audit read.

So there is no obvious per-jurisdiction timeout shorter than the advertised one in the audit read path. Railway's HTTP proxy can still return 502 quickly while the backend continues, but a snapshot that remains stale after 2+ hours means either the backend failed/cancelled before writing or is still wedged past reasonable expectations.

### Exception swallowing / silent-failure points

Locations:

- Audit SQL/build catch: [backend/app/services/coverage_audit.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/services/coverage_audit.py:125)
- Per-row prep / municipality breakdown catch: [backend/app/services/coverage_audit.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/services/coverage_audit.py:152)
- Snapshot insert catch: [backend/app/services/coverage_audit.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/services/coverage_audit.py:207)
- Final commit catch: [backend/app/services/coverage_audit.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/services/coverage_audit.py:219)
- Endpoint 502 wrapper: [backend/app/api/jurisdictions.py](/Users/arench/conductor/workspaces/STACK-Land-Acquisition/cambridge/backend/app/api/jurisdictions.py:1049)

Findings:

- The endpoint now returns 502 when `written == 0 and failed > 0`, which is better than the pre-PR #194 silent-200 pattern.
- But the service still collapses the audit SQL/build failure into `{"snapshots_written": 0, "snapshots_failed": 1, "summary": {"error": ...}}`.
- Snapshot insert failures are logged, rolled back, counted as failed, and then the loop continues.
- Final commit failures are logged and rolled back, but **do not increment `failed` or re-raise**. That can produce a misleading response if rows were flushed but the transaction did not commit.
- For a targeted refresh, continuing after failure is not useful. There is only one intended snapshot. The wrapper should surface the failing phase and exception class/message directly.

From code read alone, there is no proof that Mercer is hitting a swallowed insert/commit failure. But the wrapper design makes the API response insufficient to distinguish SQL timeout, SQL exception, insert failure, or commit failure without logs.

---

## Proposed Lane A fix

### Fix 1: add early target scoping to audit SQL

Recommended implementation shape:

1. Change `_build_audit_sql()` to accept a target parameter shape that can filter by `jurisdiction_id`, not just `jurisdiction_name`.
2. Add a small `target_jurisdictions` CTE:

```sql
WITH target_jurisdictions AS (
  SELECT j.id
  FROM jurisdictions j
  WHERE CAST(:jurisdiction_id AS uuid) IS NULL
     OR j.id = CAST(:jurisdiction_id AS uuid)
),
parcel_stats AS (
  SELECT ...
  FROM parcels p
  JOIN target_jurisdictions tj ON tj.id = p.jurisdiction_id
  GROUP BY p.jurisdiction_id
),
...
matrix_stats AS (
  SELECT ...
  FROM zone_use_matrix zum
  JOIN target_jurisdictions tj ON tj.id = zum.jurisdiction_id
  WHERE zum.deleted_at IS NULL
  GROUP BY zum.jurisdiction_id
),
...
SELECT ...
FROM jurisdictions j
JOIN target_jurisdictions tj ON tj.id = j.id
...
```

3. Apply the same `JOIN target_jurisdictions` pattern to:
   - `parcel_stats`
   - `distinct_parcel_zones`
   - `zoning_stats`
   - `matrix_stats`
   - `parcel_zone_matrix`
   - `unmatched_zone_samples`

Why this should help Mercer:

- It makes a targeted Mercer refresh proportional to Mercer parcels/districts/matrix rows, not all King umbrella residual parcels plus the whole database.
- It mirrors the scoped shape already used by `admin_op5_uncovered.py`.
- It removes most plan variability from unrelated jurisdictions.

### Fix 2: targeted refresh should raise phase-specific failures

Recommended service change:

- If `jurisdiction_id is not None`, do not swallow audit SQL/build failures at lines 125-140. Log with `logger.exception()` and re-raise, or return a structured failure with:
  - `phase="audit_sql_build"`
  - `jurisdiction_id`
  - `jurisdiction_name`
  - exception type and message.
- If snapshot insert fails for the single targeted row, re-raise or return:
  - `phase="snapshot_insert"`
  - exception type and message.
- If final commit fails, increment failure and re-raise or return:
  - `phase="snapshot_commit"`
  - exception type and message.

Full sweeps can preserve best-effort continuation. Targeted operator refreshes should be fail-fast and diagnostic.

### Fix 3: add minimum progress logging around the audit phases

Add log lines around:

1. audit SQL start/end with jurisdiction ID/name;
2. audit row count returned;
3. per-muni breakdown start/end;
4. snapshot flush start/end;
5. commit start/end.

This is not a substitute for the SQL scoping fix, but it would make the next Mercer-style stall diagnosable from logs immediately.

---

## What is probably not the fix

### Do not special-case `unmatched_zone_samples` JSON output

The JSON aggregate is capped to top 10 zone codes per jurisdiction and aggregates strings only. Mercer has 3 unmatched codes. Removing JSON output might reduce a little work, but the expensive part is the unscoped anti-join/grouping before the JSON aggregate.

### Do not only raise the HTTP timeout

The audit read already uses asyncpg `command_timeout=3600` and `statement_timeout=0`. The observed 502s in <=42s are likely Railway proxy behavior or an early backend failure surfaced as 502, not evidence that the audit read has a 42s internal timeout.

### Do not treat umbrella King County as the direct cause from code alone

The code does not show umbrella King contaminating Mercer's calculation semantically, assuming Mercer parcels were updated to the Mercer jurisdiction ID. The problem is operational: targeted refresh still computes global CTEs and then filters. King residual may increase global cost, but it is not a special semantic blocker in the SQL as written.

---

## Bottom-line recommendation

Dispatch Lane A to ship a backend fix with two parts:

1. **Scope audit CTEs early for targeted refreshes by `jurisdiction_id`.**
2. **Make targeted refresh failures phase-specific and non-swallowed.**

If Lane A wants confirmation before coding, pull Railway logs for the Mercer refresh attempts and look for one of:

- `audit SQL/build failed for jurisdiction_name=Mercer Island...`
- `snapshot insert failed for jurisdiction ...`
- `final commit failed ...`
- asyncpg timeout/cancellation on the `parcel_zone_matrix` or `unmatched_zone_samples` part of the query.

From code read alone, the highest-confidence concrete fix is early CTE scoping. The highest-confidence observability fix is fail-fast targeted refresh errors.
