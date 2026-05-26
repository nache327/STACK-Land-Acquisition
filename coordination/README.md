# Coordination Protocol

Repo-shared operational memory lives in this directory. It is intentionally tiny, machine-readable, and limited to orchestration state.

## Rules

- Do not put product logic, secrets, implementation code, logs, or large artifacts here.
- Update only the lane or blocker records you own unless you are the orchestration layer reconciling shared state.
- Keep timestamps in UTC ISO-8601 format.
- Prefer additive status changes over rewriting history needed by another lane.
- If a blocker clears, move it from `active_blockers` to `recently_cleared_blockers`.
- If a lane starts work, update `lane_state.json` before dispatching duplicate work elsewhere.
- If a lane opens, merges, retries, or pauses work, update `dispatch_queue.json` so other workspaces can see the dependency order.

## Files

- `lane_state.json`: current lane status, task, branch, blocker, wake condition, KPI delta, and timestamp.
- `blockers.json`: active and recently cleared blockers with owners and unblock conditions.
- `dispatch_queue.json`: next actions, wakeups, merge sequencing, retry sequencing, and dependency ordering.
