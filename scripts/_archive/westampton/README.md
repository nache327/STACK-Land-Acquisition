# Westampton Township, NJ — archived one-off scripts

These four scripts were ad-hoc patches applied between **2026-05-19** and
**2026-05-21** to unblock the first Burlington County deal that landed in
Westampton's B-1 zone. Each was a one-shot apply against prod that's already
done its job. They're preserved here as **documentation and replay artifacts**,
not as runnable scripts — each file's `raise SystemExit(...)` guard at the top
prevents accidental re-execution.

## What happened, in order

| # | Script | Effect |
|---|---|---|
| 1 | [`apply_westampton_zoning.py`](apply_westampton_zoning.py) (v1) | Wrote 16 `zone_use_matrix` rows under the **orphan** Westampton jurisdiction `fd74c349-…`. Wrong scope — that jurisdiction held only 16 stub parcels and zero zoning districts, so the rows could never resolve against any real parcel. |
| 2 | [`apply_westampton_zoning_v2.py`](apply_westampton_zoning_v2.py) | Re-applied the same 16 rows at the **correct** scope: Burlington County jurisdiction `d316fb43-…` with `municipality='Westampton township'`. The municipality string matches the TIGER MCD name produced by `admin/_backfill-nj-parcel-city`, so the rows now join `parcels.city` correctly. |
| 3 | [`delete_westampton_orphan_matrix.py`](delete_westampton_orphan_matrix.py) | Soft-deleted the v1 orphan rows (`deleted_at = now()`) so `matrix_bootstrap` can't auto-resurrect them. |
| 4 | [`override_parcel_0337_201_10.py`](override_parcel_0337_201_10.py) | Manually set `zoning_code='B-1'` and `city='Westampton township'` on the single deal parcel `0337_201_10` (Rancocas Bypass) so the new matrix row would actually resolve for that parcel. |

## What's still load-bearing as of 2026-05-29

- The 16 **`zone_use_matrix` rows under Burlington / `municipality='Westampton township'`** (written by `_v2`) are the canonical Westampton zoning verdicts. They're persisted in prod and behave like any other crosswalked / human-edited row.
- The **`parcels.city='Westampton township'`** value on the deal parcel is now also produced systemically by the `admin/_backfill-nj-parcel-city` job (TIGER MCD spatial join, run county-wide on 2026-05-29). So that half of the parcel override is idempotent — the systemic backfill writes the same value.
- The **`parcels.zoning_code='B-1'`** value on `0337_201_10`, however, is **not** reproducible by any current automation. Westampton's zoning is PDF-only — no ArcGIS layer for the spatial join to populate `zoning_code`. Today this single parcel's `zoning_code` exists only because `override_parcel_0337_201_10.py` ran once.

## Replay note

If Westampton ever needs `zoning_code` re-applied (e.g., DB rebuild from scratch),
the override SQL is preserved in
[`override_parcel_0337_201_10.py`](override_parcel_0337_201_10.py) — delete the
`raise SystemExit(...)` guard at the top and re-run. Same for the v2 matrix
rows via [`apply_westampton_zoning_v2.py`](apply_westampton_zoning_v2.py).

## Long-term systemic replacement

The proper systemic answer to "Westampton's zoning is a PDF" is no longer a
per-parcel override. With NJ's `parcels.city` populated and the per-city
crosswalk pattern validated, the path is:

> **NJDCA Municipal Zoning Directory seed → ordinance URL parser → per-city `zone_use_matrix` row**

Each row in `zoning_sources` with `discovered_by='njdca'` is a (county,
municipality, ordinance_url, map_url) pointer. The unlock is: parse each
muni's ordinance URL once, emit municipality-scoped matrix rows under the
county jurisdiction via the existing
[`zone_matrix_crosswalk`](../../../backend/app/services/zone_matrix_crosswalk.py)
plumbing. Bedminster-on-Somerset and Westampton-on-Burlington v2 are the
manual prototypes for this; the systemic version is the equivalent function
but sourced from NJDCA URL → parser instead of a sibling jurisdiction's
matrix.

See the project memory note `nj-njdca-unlock-2026-05-29` for the full context.

When that systemic path ships, the rows written by `apply_westampton_zoning_v2.py`
either get refreshed in place (if the parser produces the same verdicts) or
flagged for human review (if they diverge). Either way these one-off scripts
stop being load-bearing.
