# Pre-Refresh Prod Survey — Wave-6 Polygons

Date: 2026-06-24
Branch: `adarench/pre-refresh-prod-survey`
Author: Discovery + Coverage Expansion lane
Status: **READ-ONLY DIAGNOSTIC.** Material for Lane A's audit-refresh accuracy planning.

## Bottom line

Of the 17 wave-6 polygons in `backend/data/wave6_pre_stage/_APPLY_CLAIMS.md`, a coverage refresh today would flip **at most 1 to +1 ops** and **resync at most 1 existing snapshot**. The remaining 15 polygons are not refresh-flippable — they need either adapter merges, parcel/zoning ingest runs, or jurisdiction registration first.

| Refresh-outcome bucket | Count | Polygons |
|---|---:|---|
| **A. Will FLIP +1 with refresh** (operational, matrix applied, awaiting tracker bump) | 1 | Cook IL Winnetka |
| **B. Snapshot resync only** (snapshot_stale; refresh updates timestamp but cannot promote to operational) | 1 | Summit UT Park City |
| **C. Zoning-ingest blocked** (parcels loaded, 0 zoning districts; refresh re-confirms `no_zoning_districts`) | 1 | Allegheny PA Fox Chapel |
| **D. Substrate not ingested** (JID registered, no coverage snapshot — refresh has nothing to read) | 8 | Brentwood, Franklin, Sandy Springs, Buckhead, Charlotte, S.Charlotte, Pinecrest, Lake Oswego |
| **E. Jurisdiction not registered** (no JID in prod yet — refresh cannot target) | 6 | Wake Cary, Wake Raleigh, Wake N.Raleigh, Highlands Ranch, Cherry Hills Village, Golden |

Best-case refresh-only ops delta: **+1** (Winnetka → flip to 39). Best-case refresh-only snapshot resyncs: **+1** (Park City moves from `snapshot_stale` to fresh, but still won't be operational unless matrix rows applied).

## Method

Probed prod (`https://capable-serenity-production-0d1a.up.railway.app`):

- `GET /api/jurisdictions` — 142 registered jids; matched each wave-6 polygon
- `GET /api/admin/coverage` — bulk coverage report (104 successful + 177 failure rows)
- `GET /api/admin/op5/uncovered-zone-codes?jurisdiction_id={jid}&limit=5` — per-jid uncovered count

Schema fields per coverage row (when present): `parcel_count`, `parcel_with_zoning_code_count`, `zoning_district_count`, `matrix_zone_count`, `operational_readiness`, `blocking_gaps`, `parcel_zoning_code_coverage_pct`, `self_storage_classified_parcel_pct`, `captured_at`. Failure rows carry: `reason`, `parcel_count`, `bind_pct`, `district_count`, `captured_at`.

## Per-polygon survey

| Polygon | JID | Status | Parcels | Z-dist | Cov% | Op-ready | Captured | Blocker | Refresh outcome |
|---|---|---|---:|---:|---:|---|---|---|---|
| Cook IL Winnetka | `d1c50553…0221` | OK | 5,194 | 64 | **94.2** | **operational** | 2026-06-24 | none | **+1 ops** (Path A apply complete; awaiting Master go-ahead on tracker bump to current_api_truth=39) |
| Summit UT Park City | `13b01b39…4629` | FAILED | 6,651 | 124 | **99.8** (bind_pct) | — | 2026-05-12 | `snapshot_stale` | Resync timestamp; cannot flip — also blocked by polygon-confirmation gate (Phase 6 outlier) |
| Allegheny PA Fox Chapel | `c5e04fa4…3f17` | FAILED | 1,485 | **0** | 0.0 | — | 2026-06-22 | `no_zoning_districts` | Refresh re-confirms blocker; needs PR #346 adapter merge + zoning ingest first |
| Williamson TN Brentwood | `e0df78b2…613c` | MISSING | — | — | — | — | — | no snapshot | No substrate to refresh; needs adapter PR (TBD) + parcel/zoning ingest |
| Williamson TN Franklin | `307285f8…218f` | MISSING | — | — | — | — | — | no snapshot | No substrate to refresh; needs adapter PR (TBD) + parcel/zoning ingest |
| Fulton GA Sandy Springs | `b49ac34f…d706` | MISSING | — | — | — | — | — | no snapshot | PR #348 PREP merged but fire PR pending; needs ingest run |
| Fulton GA Buckhead | `a5d68bcd…9013` | MISSING | — | — | — | — | — | no snapshot | PR #348 PREP merged but fire PR pending; needs ingest run + KMZ sub-AOI |
| Mecklenburg NC Charlotte | `3061acc6…98dc` | MISSING | — | — | — | — | — | no snapshot | PR #354 PREP merged but fire PR pending; needs ingest run |
| Mecklenburg NC South Charlotte | `c9af9445…2271` | MISSING | — | — | — | — | — | no snapshot | PR #354 PREP merged but fire PR pending; needs ingest run + KMZ sub-AOI |
| Miami-Dade FL Pinecrest | `55da99fa…db4f` | MISSING | — | — | — | — | — | no snapshot | PR #351 PREP merged but fire PR pending; needs ingest run |
| Clackamas OR Lake Oswego | `2c1736ee…00c2` | MISSING | — | — | — | — | — | no snapshot | No adapter PR yet; needs full Lane A treatment |
| Wake NC Cary | — | **NO JID** | — | — | — | — | — | not registered | PR #353 OPEN; needs jurisdiction-create + ingest |
| Wake NC Raleigh | — | **NO JID** | — | — | — | — | — | not registered | PR #353 OPEN; needs jurisdiction-create + ingest |
| Wake NC North Raleigh | — | **NO JID** | — | — | — | — | — | not registered | PR #353 OPEN; needs jurisdiction-create + ingest + KMZ sub-AOI |
| Douglas CO Highlands Ranch | — | **NO JID** | — | — | — | — | — | not registered | PR #355 OPEN; needs jurisdiction-create + ingest |
| Arapahoe CO Cherry Hills Village | — | **NO JID** | — | — | — | — | — | not registered | PR #355 OPEN; needs jurisdiction-create + ingest |
| Jefferson CO Golden | — | **NO JID** | — | — | — | — | — | not registered | PR #355 OPEN; needs jurisdiction-create + ingest |

Notes on JID lookup:
- Wake County (`b05b7317…7d17bf`) IS registered but is a county-level row with `parcel_count=0`, `reason=snapshot_stale` and empty `municipality_breakdown`. Per-muni Wake jids (Cary/Raleigh/N.Raleigh) do not exist.
- Arapahoe County (`5c4b612c…3d4e`) IS registered but is not present in the coverage report at all. Cherry Hills Village sub-AOI not registered.
- Douglas County (`ec296fd0…2c45`) IS registered but is not present in the coverage report. Highlands Ranch sub-AOI not registered.
- Jefferson County CO is not registered at all (no county-level jid found).

## Per-bucket Lane A action

### Bucket A — Refresh will flip (1 polygon)

**Cook IL Winnetka** is already `operational` with `parcel_zoning_code_coverage_pct=94.2%`, 64 zoning districts, matrix applied, captured 2026-06-24 02:00Z. The audit refresh itself is not what produces the flip — the matrix apply (PR #356 merged) already did. What's missing is the **tracker bump**: `coordination/lane_state.json honest_operational_count.current_api_truth` 38 → 39, plus `docs/PHASE2_PROGRESS.md` §15 entry. Per `_APPLY_CLAIMS.md` line 105, this is awaiting Master's go-ahead (TRACK B pre-authorization).

**Lane A predicted accuracy:** Audit refresh will report Winnetka as operational with high coverage. ✅ Matches reality.

### Bucket B — Snapshot resync only (1 polygon)

**Summit UT Park City** is `snapshot_stale` per `captured_at=2026-05-12`, but the underlying numbers (6,651 parcels, 124 districts, 99.8% bind_pct) are healthy. A coverage refresh will refresh `captured_at` and move the row from `failures` into `jurisdictions`. However:

- Without a matrix apply, `operational_readiness` will not become `operational`
- Phase 6 polygon-confirmation gate is still open (Park City sub-AOI extent within Summit)
- Refresh produces a green snapshot but does NOT produce +1 ops

**Lane A predicted accuracy:** Audit refresh will show Park City "fresh, but not operational, gate-blocked." ✅ Refresh outcome is expected to be a state transition without an ops-count change.

### Bucket C — Zoning ingest blocked (1 polygon)

**Allegheny PA Fox Chapel** has 1,485 parcels loaded but `district_count=0` → `no_zoning_districts`. PR #346 (Lane A adapter PREP) is still OPEN. A refresh today will:

- Re-confirm `district_count=0` and `bind_pct=0%`
- Keep the row in the `failures` bucket with `reason=no_zoning_districts`
- NOT produce an ops-count change

**Lane A predicted accuracy:** Refresh will surface Fox Chapel as a hard-blocker waiting on adapter merge. ✅ Accurate.

### Bucket D — Substrate not ingested (8 polygons)

These 8 jids exist (created 2026-06-23 or 2026-06-24), but have no coverage snapshot at all — the bulk coverage report does not include them in either the `jurisdictions` or `failures` lists. Per-jid `/api/admin/op5/uncovered-zone-codes` queries return 500 Internal Server Error, consistent with "no parcels indexed."

The 8 polygons fall into two sub-states:

- **PREP merged, awaiting fire** (5): Sandy Springs (#348), Buckhead (#348), Charlotte (#354), South Charlotte (#354), Pinecrest (#351). Adapter code is on main; fire PR (substrate ingest dispatch) is pending Lane A signal.
- **No adapter merged yet** (3): Brentwood, Franklin (Agent 4 TBD), Lake Oswego (Phase 6 outlier rank 3, agent TBD).

A refresh today will not surface these polygons in any audit output. **Lane A predicted accuracy:** the audit will look like the polygons "do not exist" — be careful that Lane A's refresh-tooling does not interpret missing rows as "ingested with zero parcels" (which would be the wrong inference).

### Bucket E — Jurisdiction not registered (6 polygons)

Wake NC munis (Cary, Raleigh, North Raleigh) and CO Front Range munis (Highlands Ranch, Cherry Hills Village, Golden) are not registered as jids. Adapter PRs #353 and #355 are still OPEN. A refresh has nothing to target — there is no JID for the refresh-tooling to address.

**Lane A predicted accuracy:** if the audit refresh tooling iterates over registered jids, these 6 polygons will be silently absent from the audit. If the tooling iterates over a static wave-6-target list, they will surface as "JID-not-found" errors. Either way, no ops-count change is possible until adapters merge AND per-muni jurisdiction-create runs AND ingest fires.

## Predicted ops-count after refresh

| Scenario | Refresh-only delta | Cumulative after refresh |
|---|---:|---:|
| Current (per `coordination/lane_state.json`) | — | **38** |
| Winnetka tracker bump alone | +1 | **39** |
| Full wave-6 refresh against today's prod | +1 | **39** |

Realistic ceiling per `_APPLY_CLAIMS.md` line 84 was +11-17. None of that additional capacity is unlocked by a refresh alone — each polygon requires its respective adapter merge → fire PR → matrix apply sequence first.

## Gotchas for Lane A's audit-refresh tooling

1. **8 jids exist but have no coverage row.** If the audit treats missing rows as "0 parcels, 0 districts," the report will look like a regression. Treat MISSING as "not yet ingested" rather than "ingested with zero data."
2. **6 polygons have no JID at all.** The audit-refresh-by-JID loop will silently skip them. Recommend a separate `wave-6 substrate inventory` view that lists pre-stage files vs registered jids vs coverage rows so the gap is visible.
3. **Winnetka's row is fresh (2026-06-24 02:00Z).** Refreshing again will just re-stamp the same captured_at. Whether the tracker bump happens is a separate Master decision, not a refresh consequence.
4. **Park City's bind_pct shows 99.8%** but it's in the failures list because of `snapshot_stale`, not because of bind quality. A refresh will produce a healthy snapshot — but the polygon-confirmation gate (Phase 6) remains an independent blocker.
5. **Fox Chapel will NEVER flip from a refresh alone.** Its blocker is upstream (no zoning data ingested). Adapter PR #346 must merge first.
6. **South Charlotte and Charlotte share PR #354 but have separate jids** (`3061acc6…` and `c9af9445…`). Both currently missing — they should fire in the same ingest run when Agent 6 fires.

## Endpoints used (for Lane A reproducibility)

```bash
PROD="https://capable-serenity-production-0d1a.up.railway.app"

# Bulk coverage (104 successful, 177 failures as of 2026-06-24)
curl "$PROD/api/admin/coverage"

# Per-jid uncovered codes (500 if no parcels indexed)
curl "$PROD/api/admin/op5/uncovered-zone-codes?jurisdiction_id=$JID&limit=500"

# Per-jid metadata
curl "$PROD/api/jurisdictions/$JID"

# Jurisdiction list (142 total today)
curl "$PROD/api/jurisdictions"
```

## Scope guards honored

- Read-only HTTP probes only. No writes to any prod endpoint. No matrix applies. No coverage-refresh POSTs.
- No new jurisdictions registered.
- No ingest dispatched.
- Lane A is the consumer of this survey, not a co-author.

## Stand-down

Per user budget: HALT-AND-REPORT complete. Re-engagement criteria unchanged (PR #280 audit fix deploy effects, Vessel Tech B2B response, Burlington nache execution support, unexpected wave-6 fire failures needing structural diagnosis).
