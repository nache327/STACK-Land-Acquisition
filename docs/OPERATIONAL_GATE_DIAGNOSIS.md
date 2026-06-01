# Norfolk MA Operational Gate Diagnosis

Date: 2026-06-01
Owner: Lane A
Subject: why Norfolk County MA stayed partial after PR #155 despite `parcel_zoning_code_coverage_pct=74.9`.

## Finding

Norfolk County MA is not blocked by the 70% truthfulness floor. It passes that floor, but `_operational_readiness` still returns `partial` because `blocking_gaps` is not empty.

The real blockers in `backend/tmp/audit_may31_close.json` are:

- `high_unclear_self_storage_share`
- `no_zoning_polygons`

This is not a fake-operational flag and not a matrix-match-completeness issue. The matrix is fully matched for the parcel zoning codes currently present.

## Evidence

From `backend/tmp/audit_may31_close.json` for Norfolk County MA:

- `operational_readiness`: `partial`
- `parcel_count`: `206365`
- `parcel_zoning_code_coverage_pct`: `74.9`
- `parcels_with_zoning_code`: `154616`
- `parcels_with_matrix_match`: `154616`
- `matrix_zone_count`: `312`
- `matrix_zone_match_pct`: `100.0`
- `matrix_distinct_zone_match_pct`: `100.0`
- `matrix_self_storage_unclear_count`: `77`
- `parcels_self_storage_unclear`: `13428`
- `self_storage_classified_parcel_pct`: `91.3`
- `zoning_district_count`: `0`
- `zoning_polygon_coverage_flag`: `false`
- `blocking_gaps`: `["high_unclear_self_storage_share", "no_zoning_polygons"]`

PR evidence:

- PR #100 / `6eb9eaf`: Norfolk batch 1 moved 16,489 parcels unclear to classified.
- PR #155 / `b94361a`: Norfolk batch 2 moved 1,210 parcels unclear to classified.
- May-31 final audit artifact records no operational flip after PR #155.

## Code Reference

Readiness is computed in `backend/scripts/audit_zoning_coverage.py`.

- Lines 331-342: `_operational_readiness` returns `not_loaded` only for zero parcels, returns `partial` below 70% parcel zoning-code coverage, returns `operational` only when `blocking_gaps` is empty, and otherwise returns `partial`.
- Lines 383-384: `high_unclear_self_storage_share` is added when `self_storage_classified_parcel_pct < 95.0`.
- Lines 389-403: if there are no zoning polygons, parcel-source zoning is sufficient only when parcel zoning-code coverage is at least 80%, matrix rows exist, and matrix match is at least 90%.
- `backend/app/services/coverage_audit.py` is a wrapper that imports the script logic and persists `operational_readiness` plus `blocking_gaps` into snapshots; it does not define a separate readiness gate.

## Gate Math

Norfolk clears the 70% truthfulness floor:

- Current zoning-code coverage: `74.9%`
- Operational floor: `70.0%`

Norfolk does not clear the parcel-source zoning substitute for missing polygons:

- Required when `zoning_district_count=0`: at least `80.0%` parcel zoning-code coverage.
- Current: `154,616 / 206,365 = 74.9%`.
- Needed for 80%: `165,092` zoned parcels.
- Gap: `10,476` more parcels with zoning codes, unless actual zoning polygons are loaded.

Norfolk does not clear the self-storage classification gate:

- Required: at least `95.0%` of matrix-matched parcels classified permitted/conditional/prohibited.
- Current: `91.3%`, with `13,428` unclear-bound parcels.
- Matrix-matched denominator: `154,616`.
- Maximum unclear at 95% classified: about `7,730` parcels.
- Gap: classify at least `5,699` additional unclear-bound parcels, assuming the denominator does not change.

## Lane E Implication

Lane E matrix work can target `high_unclear_self_storage_share`, but matrix work alone will not clear `no_zoning_polygons` unless it also increases parcel zoning-code coverage or another lane loads zoning polygons. Norfolk is therefore a threshold-edge partial with two gates:

1. Reduce unclear-bound parcels from `13,428` to roughly `7,730` or fewer.
2. Raise parcel zoning-code coverage from `74.9%` to at least `80.0%`, or load zoning polygons.

Next Norfolk work should not assume that reducing the 77 unclear matrix rows is sufficient for an operational flip.
