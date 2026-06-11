# Audit Exception Dead-Zone Survey

Date: 2026-06-11

Scope: survey production coverage for jurisdictions with `parcel_zoning_code_coverage_pct` in the 70-79% dead-zone below the current parcel-source-zoned exception threshold in `backend/scripts/audit_zoning_coverage.py`.

## Current Audit Rule

`no_zoning_polygons` is suppressed only when all four conditions pass:

- `parcels_with_zoning_code > 1000`
- `parcel_zoning_code_coverage_pct >= 80.0`
- `matrix_zone_count > 0`
- `matrix_zone_match_pct >= 90.0`

The relevant code is `backend/scripts/audit_zoning_coverage.py:457-462`.

## Headline

Only one production jurisdiction is in the 70-79% dead-zone: Norfolk County, MA.

If the threshold were lowered from 80% to 70%, Norfolk County, MA would satisfy the other parcel-source-zoned exception conditions and `no_zoning_polygons` would clear. Based on the current coverage row, it would flip operational because no other blocking gap is currently reported.

This is low-leverage as a global audit change: 1 total flip, 1 customer-relevant 57-list flip, not the >=3-flip threshold for a separate audit-threshold sprint.

## Dead-Zone Jurisdictions

Production source: `GET https://capable-serenity-production-0d1a.up.railway.app/api/admin/coverage`, pulled 2026-06-11.

The API payload does not currently expose `matrix_zone_match_pct`, so the matrix match was checked directly with the same `parcels.zoning_code = zone_use_matrix.zone_code` join used by the audit.

| Jurisdiction | State | Parcel count | Parcels with zoning code | Zoning coverage | Matrix zones | Matrix zone match | Blocking gaps | `no_zoning_polygons` would clear at 70%? | Would flip operational? | 57-list? |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| Norfolk County, MA | MA | 206,365 | 154,616 | 74.9% | 312 | 100.0% | `no_zoning_polygons` | Yes. Other exception conditions pass: >1,000 zoned parcels, matrix zones >0, match >=90%. | Yes, based on current blocker list. | Yes, Phase 4 / Wellesley center. |

## Norfolk MA Detail

Current production coverage row:

- `jurisdiction_id`: `6cf15e94-4d2b-4434-a5a8-ea0fff78c1c5`
- `parcel_count`: 206,365
- `parcel_zoning_code_coverage_pct`: 74.9%
- `zoning_district_count`: 0
- `matrix_zone_count`: 312
- `operational_readiness`: `partial`
- `blocking_gaps`: `no_zoning_polygons`

Direct production database check:

- `parcels_with_zoning_code`: 154,616
- `audit_matrix_match_pct`: 100.0%
- `zoning_districts` rows for Norfolk: 0

The current blocker is exactly the 80% parcel-source-zoned exception threshold. Norfolk is above PR #98's general 70% coverage gate but below the current 80% exception gate.

## Cross-Reference to the 57-List

Norfolk County, MA is on the 57-list via Phase 4 Boston / Wellesley. No other production jurisdiction sits in the 70-79% dead-zone.

## Recommendation

Keep the 80% parcel-source-zoned exception threshold.

The threshold question is low-leverage because Norfolk MA is the only affected jurisdiction. If Master wants Norfolk operational despite the residual 5.1 percentage-point gap, use a targeted Norfolk audit exception or accept Norfolk as permanent partial-with-residual; do not make a global 80->70 threshold change on this evidence alone.
