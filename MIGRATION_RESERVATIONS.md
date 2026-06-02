# Migration number reservations

Migrations land sequentially. Two branches reaching for the same number
produces the `0023` collision pattern (see commit `8767150`). To prevent
it: **claim the number here before authoring the alembic file.**

## Workflow

1. Before creating `backend/alembic/versions/00NN_*.py`, add a row to the
   table below in a separate commit (or as the first commit on the branch).
2. Author the migration on the same branch.
3. After it lands on `main`, remove the row.
4. If two branches both claim the same number, the **second-to-merge** rebases
   their migration onto the next available number and updates `down_revision`.

## Active claims

| # | Reserved by (branch) | Description | Claimed (UTC) | Notes |
|---|---|---|---|---|
| 0038 | adarench/nearest-district-fallback | parcels.zone_binding_method varchar + index for Op-5 spatial_backfill nearest-fallback | 2026-06-04T18:00 | Dispatch J |
| (open) | | | | next available number for new claims |

## Rules

- Lane B (non-integration) requests a number by opening a PR that adds a row
  here. Lane A (integration owner) merges that PR atomically with the
  migration PR — or has Lane B include both in one PR.
- A claim older than 7 days with no merged migration may be reclaimed by
  anyone after pinging the original owner.
- The `(open)` row stays as the bottom row; new claims insert above it.
- Do not author `down_revision` chains that fork — always linear.
