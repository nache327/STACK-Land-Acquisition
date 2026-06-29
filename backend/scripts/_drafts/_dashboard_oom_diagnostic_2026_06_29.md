# Dashboard OOM on large counties — root-cause analysis (2026-06-29)

Repro: Chrome "Aw, Snap! — Out of Memory" opening a large county dashboard
(`/dashboard/{jobId}?parcel_id=…`). Hit on Bucks PA (~237k parcels); recurs on Salt Lake (~397k),
Montgomery PA (~301k).

## It is NOT the client per-parcel Mapbox loop
That loop is already gated off for large counties: `CLIENT_PRECOMPUTE_MAX_ELIGIBLE = 1500`
([page.tsx:574-586](../../../frontend/app/dashboard/[jobId]/page.tsx)). On Bucks the eligible set is far
over 1500 → `startPrecompute` short-circuits, loop never runs. (The plan's Phase 2B already addressed this.)

## The actual driver — parcel-render path
1. **5,000 full-resolution polygons per viewport.** `MAP_PAGE_SIZE = 5000` ([page.tsx:65]) × slim payload
   that still carries full `geom` ([schemas.ts:254]) × server simplify tolerance only ~1m
   ([candidate_search.py:239] `ST_SimplifyPreserveTopology(geom, 0.00001)`) → each polygon keeps ~all vertices.
2. **Held 3-4× simultaneously:** React state (TanStack Query `mapResults.items`) → `Map.tsx`
   `parcelCollection` useMemo rebuilds a full parallel FeatureCollection ([Map.tsx:343-386]) → MapLibre
   clones into its GeoJSON source on every `setData` ([Map.tsx:631]) → `heatCollection` centroid copy
   ([Map.tsx:404-419]) + MapLibre worker hit-test copy.
3. **Amplifier — identity thrash:** `const mapParcels = mapResults?.items ?? []` ([page.tsx:364]) was a
   fresh array every render, so the saturation effect, `parcelCollection` memo, `setData` + per-parcel
   `setFeatureState` ([Map.tsx:858-876]) all re-ran and re-uploaded the whole GeoJSON on every settled
   pan/zoom. GC lags a rapid pan → several viewports of garbage stack → tab exceeds renderer memory ceiling.

Rough math: dense polygon ~1-4KB GeoJSON; 5000 × ~2KB ≈ 10MB/copy × ~4 ≈ 40MB/viewport, multiplied by
rebuild-without-reclaim during panning = OOM.

## Secondary (not the driver)
- `useParcelScores` fetches up to 10,000 score rows on mount unconditionally ([useParcelScores.ts:28]) —
  no geometry, few MB. Low urgency; could be bbox-bounded.
- Large-county guard computes `expected` from the 5000-row viewport, not a county-level count
  ([page.tsx:560-563]) — viewport-relative "large" detection; latent Phase-2B correctness gap, not OOM.

## Fixes
**This PR (parcellogic/dashboard-oom-quick-wins) — friction-reducers, low risk:**
1. `MAP_PAGE_SIZE` 5000 → 1000 ([page.tsx:65]) — caps per-viewport polygons 5×.
2. simplify tolerance 0.00001 → 0.0003 (~30m) ([candidate_search.py:239]) — ~10× fewer vertices/polygon.
3. memoize `mapParcels` ([page.tsx:364]) — stops the rebuild/re-upload storm during panning.

**Durable fix (separate, larger):** switch the parcel layer to **vector tiles** — geometry never enters
the JS heap, MapLibre streams tiles. The `TILESERV_URL` / `LAYER_REGISTRY` vector-source plumbing already
exists in `Map.tsx:580-586`. Recommend as the real Phase-2B-adjacent "parcel-render scale" item.

Credit: diagnosed by a read-only sub-investigation over page.tsx / Map.tsx / isochrone-precompute.ts /
useParcels / useParcelScores / candidate_search.py.
