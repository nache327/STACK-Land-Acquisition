import type { Feature, Polygon, MultiPolygon } from "geojson";

import { fetchIsochrone, fetchCensusTracts } from "@/lib/isochrone";
import type { TractData } from "@/lib/isochrone";
import type { CandidateParcelRow } from "@/lib/schemas";
import { api } from "@/lib/api";
import type { ServerRingMetricRow, RingDemographicWrite } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface PrecomputedRingMetrics {
  totalPopulation: number;
  hnwHouseholds: number;
  weightedMedianHHI: number;
  weightedMedianHomeValue: number;
  // Wealth-density counts — populated only when the user enables one of
  // the three home-density sliders (lazy backend fetch). null when not
  // yet measured. See fetchHomeDensityForRing().
  homesOver1M: number | null;
  homesOver2M: number | null;
  homesOver5M: number | null;
  tractCount: number;
  lastComputed: string; // ISO date string
}

export interface PrecomputedParcelData {
  parcelId: string;
  rings: {
    2: PrecomputedRingMetrics;
    5: PrecomputedRingMetrics;
    10: PrecomputedRingMetrics;
    15: PrecomputedRingMetrics;
  };
}

export interface PrecomputeStatus {
  progress: number;
  total: number;
  complete: boolean;
  lastComputed?: string;
  /**
   * True when the per-parcel client precompute loop was intentionally NOT
   * run because the jurisdiction's eligible-parcel set is too large (the
   * server-side precompute actor handles it instead). Demographic/wealth
   * features stay gated on `complete` while deferred; a later reload picks
   * up the warm server cache. See Phase 2B / progressive dashboard load.
   */
  deferred?: boolean;
}

export interface CacheMeta {
  lastComputed: string;
  /** Number of parcel entries persisted in the data blob. */
  saved: number;
  /** Number of eligible parcels at the time of the run. A reload that
   *  finds saved < expected treats the cache as partial and resumes. */
  expected: number;
}

// ── Storage keys ───────────────────────────────────────────────────────────────

// v7: CacheMeta gained `saved` and `expected` so the load path can detect a
// partial cache (where mid-run failures left some eligible parcels missing)
// and resume instead of poisoning the UI into a permanent "complete" state.
// v6 meta only carried {lastComputed, total} where total === saved, so there
// was no way to tell "20 of 2253 succeeded" apart from "20 of 20 succeeded";
// any Somerset-shaped jurisdiction whose first precompute pass was rate-
// limited or partially-failed locked every missed parcel into "Computing…"
// in the drawer. Bump to invalidate v6 entries so the new contract takes.
// v6: PrecomputedRingMetrics gained three homesOver{1,2,5}M fields. The
// fields are nullable (only populated when the wealth-density sliders are
// enabled) — but the shape change means v5 blobs deserialize without
// them, which TS treats as undefined and the reducer treats as 0. Bump
// to force a clean rebuild so cached entries don't silently miss values
// after a user enables a slider for the first time.
// v5: HNW count switched from tract-median-binary proxy to ACS B19001_017E
// (actual count of households with income >= $200K per tract). Cached blobs
// from v4 don't have the new field — must invalidate so the next paint
// pulls fresh numbers from Census.
// v4: HNW tract-median threshold raised from $150K to $200K. Invalidates
// every cached metrics blob so the new cutoff takes effect.
// v3: invalidate the empty caches v2 created on first load when mapParcels
// hadn't populated yet (race condition fixed in dashboard/[jobId]/page.tsx).
// v2: weighted-mean denominator bug fix (HHI / home value were divided by
// totalPopulation instead of sum-of-household-counts, deflating values ~2.7×).
const META_KEY = (cityId: string) => `parcellogic_precompute_meta_v7_${cityId}`;
const DATA_KEY = (cityId: string) => `parcellogic_precompute_v7_${cityId}`;
const IDB_DB = "parcellogic_precompute";
const IDB_STORE = "cities";
const SMALL_CITY_THRESHOLD = 500;

function isQuotaError(e: unknown): boolean {
  const err = e as { name?: string; code?: number } | null;
  return !!err && (err.name === "QuotaExceededError" || err.code === 22);
}

// ── Internal helpers ───────────────────────────────────────────────────────────

function parcelCentroid(parcel: CandidateParcelRow): [number, number] | null {
  const geom = parcel.geom as unknown as { coordinates: unknown } | null;
  if (!geom?.coordinates) return null;

  const coords: number[][] = [];
  const collect = (c: unknown): void => {
    if (!Array.isArray(c)) return;
    if (typeof c[0] === "number") { coords.push(c as number[]); return; }
    (c as unknown[]).forEach(collect);
  };
  collect(geom.coordinates);
  if (!coords.length) return null;

  const lngs = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  return [
    (Math.min(...lngs) + Math.max(...lngs)) / 2,
    (Math.min(...lats) + Math.max(...lats)) / 2,
  ];
}

function computeRingMetrics(tracts: TractData[]): PrecomputedRingMetrics {
  const valid = tracts.filter((t) => t.household_count != null && t.household_count > 0);
  // Use actual population (B01003_001E) when available; fall back to household count
  // for backwards-compat with any cached TractData that predates the population field.
  const totalPopulation = valid.reduce((s, t) => s + (t.population ?? t.household_count ?? 0), 0);

  // Actual count of households earning >= $200K per tract, summed across
  // tracts that intersect the ring. Sources ACS B19001_017E directly — the
  // top bracket of the household-income series. Replaces the prior
  // tract-median binary proxy, which over-counted tracts above the cutoff
  // and under-counted high-income households in mixed-income tracts.
  const hnwHouseholds = valid.reduce(
    (s, t) => s + (t.households_over_200k ?? 0),
    0,
  );

  // Household-weighted means: numerator is weighted by household_count, so the
  // denominator must be sum(household_count) — NOT totalPopulation. Dividing
  // a household-weighted sum by population deflated NJ values by ~2.7×
  // (the average household size), e.g. Marlboro's $148K HHI showed ~$54K.
  const hhiTracts = valid.filter((t) => t.median_hhi != null);
  const totalHHIHouseholds = hhiTracts.reduce((s, t) => s + (t.household_count ?? 0), 0);
  const weightedMedianHHI =
    totalHHIHouseholds > 0
      ? hhiTracts.reduce((s, t) => s + t.median_hhi! * t.household_count!, 0) / totalHHIHouseholds
      : 0;

  const hvTracts = valid.filter((t) => t.median_home_value != null);
  const totalHVHouseholds = hvTracts.reduce((s, t) => s + (t.household_count ?? 0), 0);
  const weightedMedianHomeValue =
    totalHVHouseholds > 0
      ? hvTracts.reduce((s, t) => s + t.median_home_value! * t.household_count!, 0) / totalHVHouseholds
      : 0;

  return {
    totalPopulation,
    hnwHouseholds,
    weightedMedianHHI,
    weightedMedianHomeValue,
    homesOver1M: null,
    homesOver2M: null,
    homesOver5M: null,
    tractCount: tracts.length,
    lastComputed: new Date().toISOString(),
  };
}

// ── Lazy backend fetch for wealth-density ──────────────────────────────────
//
// Calls POST /api/parcels/value-density for one ring polygon, asking the
// server to count residential parcels above $1M / $2M / $5M and cache the
// result in parcel_ring_metrics. Returns the three counts.

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchHomeDensityForRing(
  polygon: { type: "Polygon" | "MultiPolygon"; coordinates: unknown },
  options: { parcelId?: number; driveTimeMinutes?: 2 | 5 | 10 | 15 } = {},
): Promise<{ homesOver1M: number; homesOver2M: number; homesOver5M: number }> {
  const res = await fetch(`${API_BASE_URL}/api/parcels/value-density`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      polygon,
      parcel_id: options.parcelId,
      drive_time_minutes: options.driveTimeMinutes,
    }),
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) {
    throw new Error(`value-density HTTP ${res.status}`);
  }
  const data = (await res.json()) as {
    homes_over_1m: number;
    homes_over_2m: number;
    homes_over_5m: number;
  };
  return {
    homesOver1M: data.homes_over_1m,
    homesOver2M: data.homes_over_2m,
    homesOver5M: data.homes_over_5m,
  };
}

// ── Shared server cache (parcel_ring_metrics) ───────────────────────────────
//
// Seed the precompute from the server-side cache so a city computed by ANY
// user/session is reused, instead of re-running Mapbox + Census per parcel.
// Demographics are written back from processOne (best-effort); wealth-density
// homes_over_* flow through the value-density path.

const _RING_TIMES = [2, 5, 10, 15] as const;

function finiteOrNull(n: number | null | undefined): number | null {
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

/** Group flat server rows into the 4-ring PrecomputedParcelData shape. A
 *  parcel is included ONLY when all four drive-time rings are present, so a
 *  partial row set recomputes fully on the next run. */
function serverRowsToPrecomputed(
  rows: ServerRingMetricRow[],
): Map<string, PrecomputedParcelData> {
  const byParcel = new Map<string, Map<number, ServerRingMetricRow>>();
  for (const r of rows) {
    const pid = String(r.parcel_id);
    let rings = byParcel.get(pid);
    if (!rings) { rings = new Map(); byParcel.set(pid, rings); }
    rings.set(r.drive_time_minutes, r);
  }

  const out = new Map<string, PrecomputedParcelData>();
  byParcel.forEach((rings, pid) => {
    if (!_RING_TIMES.every((dt) => rings.has(dt))) return;
    const ring = (dt: 2 | 5 | 10 | 15): PrecomputedRingMetrics => {
      const r = rings.get(dt)!;
      return {
        totalPopulation: r.population ?? 0,
        hnwHouseholds: r.hnw_households ?? 0,
        weightedMedianHHI: r.median_hhi ?? 0,
        weightedMedianHomeValue: r.median_home_value ?? 0,
        homesOver1M: r.homes_over_1m,
        homesOver2M: r.homes_over_2m,
        homesOver5M: r.homes_over_5m,
        tractCount: 0, // display-only; not persisted server-side
        lastComputed: r.computed_at,
      };
    };
    out.set(pid, {
      parcelId: pid,
      rings: { 2: ring(2), 5: ring(5), 10: ring(10), 15: ring(15) },
    });
  });
  return out;
}

/** Fetch the jurisdiction's cached ring metrics. Best-effort: returns an
 *  empty map on any error so the dashboard still renders + falls back to the
 *  client precompute. */
export async function loadServerRingMetrics(
  jurisdictionId: string,
): Promise<Map<string, PrecomputedParcelData>> {
  try {
    const rows = await api.getJurisdictionRingMetrics(jurisdictionId);
    return serverRowsToPrecomputed(rows);
  } catch (err) {
    console.warn("[precompute] server ring-metrics load failed:", err);
    return new Map();
  }
}

// ── Cache ──────────────────────────────────────────────────────────────────────

export function getCacheMetadata(cityId: string): CacheMeta | null {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(META_KEY(cityId)) : null;
    return raw ? (JSON.parse(raw) as CacheMeta) : null;
  } catch {
    return null;
  }
}

function openIDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_DB, 1);
    req.onupgradeneeded = (e) => {
      (e.target as IDBOpenDBRequest).result.createObjectStore(IDB_STORE);
    };
    req.onsuccess = (e) => resolve((e.target as IDBOpenDBRequest).result);
    req.onerror = () => reject(req.error);
  });
}

async function writeToIDB(key: string, value: string): Promise<void> {
  const db = await openIDB();
  const tx = db.transaction(IDB_STORE, "readwrite");
  tx.objectStore(IDB_STORE).put(value, key);
  await new Promise<void>((res, rej) => {
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
  });
}

export async function saveCityCache(
  cityId: string,
  data: Map<string, PrecomputedParcelData>,
  expected: number,
): Promise<void> {
  const serialized = JSON.stringify(Object.fromEntries(data));

  // Write data first; only write meta once we know the data persisted.
  // The prior order (meta first, data second) could orphan meta pointing
  // to a blob that never landed, and the load path then trusted meta as
  // proof the run had completed.
  let persisted = false;

  // localStorage path for tiny cities. On QuotaExceededError, fall through
  // to IDB rather than dropping silently. (Somerset-sized cities already
  // take the IDB branch directly via SMALL_CITY_THRESHOLD.)
  if (expected <= SMALL_CITY_THRESHOLD) {
    try {
      localStorage.setItem(DATA_KEY(cityId), serialized);
      persisted = true;
    } catch (e) {
      if (!isQuotaError(e)) {
        console.warn("[precompute] localStorage save failed (non-quota):", e);
      }
    }
  }

  if (!persisted) {
    try {
      await writeToIDB(DATA_KEY(cityId), serialized);
      persisted = true;
    } catch (e) {
      console.warn("[precompute] IDB save failed:", e);
    }
  }

  if (persisted) {
    const meta: CacheMeta = {
      lastComputed: new Date().toISOString(),
      saved: data.size,
      expected,
    };
    try { localStorage.setItem(META_KEY(cityId), JSON.stringify(meta)); } catch { /* meta is tiny */ }
  } else {
    // Don't leave stale meta pointing at data we couldn't persist — that
    // re-creates the v6 "complete but empty" poisoning the load path used
    // to fall into.
    try { localStorage.removeItem(META_KEY(cityId)); } catch { /* ignore */ }
  }
}

/**
 * Scan localStorage for `parcellogic_precompute_meta_v*_*` keys where
 * the corresponding data blob is missing from BOTH localStorage and
 * IndexedDB, and delete those orphan meta entries.
 *
 * Background: pre-v7 saves wrote meta first and the data blob second,
 * so any IDB write that failed silently (quota, race) left an orphan
 * meta pointing to nothing. The load path then read that meta, saw
 * "total > 0," and treated the jurisdiction as cached + complete —
 * every drawer click thereafter showed "Computing…" forever. Observed
 * in production on Somerset County, NJ: v6 meta said `total: 141`,
 * no data anywhere.
 *
 * Cheap to run (one localStorage scan + one IDB read per orphan), so
 * we just call it once per dashboard mount.
 */
export async function purgeOrphanMeta(): Promise<number> {
  if (typeof window === "undefined") return 0;

  const candidates: { metaKey: string; dataKey: string }[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (!k) continue;
    const m = /^parcellogic_precompute_meta_(v\d+)_(.+)$/.exec(k);
    if (!m) continue;
    const [, version, cityPart] = m;
    candidates.push({
      metaKey: k,
      dataKey: `parcellogic_precompute_${version}_${cityPart}`,
    });
  }
  if (candidates.length === 0) return 0;

  let db: IDBDatabase | null = null;
  try {
    db = await openIDB();
  } catch {
    db = null;
  }

  const orphans: string[] = [];
  for (const { metaKey, dataKey } of candidates) {
    if (localStorage.getItem(dataKey) !== null) continue;
    let idbHas = false;
    if (db) {
      try {
        const tx = db.transaction(IDB_STORE, "readonly");
        const req = tx.objectStore(IDB_STORE).get(dataKey);
        idbHas = await new Promise<boolean>((resolve) => {
          req.onsuccess = () => resolve(req.result != null);
          req.onerror = () => resolve(false);
        });
      } catch {
        // If IDB read errored, be conservative — don't delete meta
        // when we can't confirm the data is missing.
        idbHas = true;
      }
    }
    if (!idbHas) orphans.push(metaKey);
  }

  for (const k of orphans) {
    try { localStorage.removeItem(k); } catch { /* ignore */ }
  }
  if (orphans.length > 0) {
    console.log(
      `[precompute] purged ${orphans.length} orphan meta entr${orphans.length === 1 ? "y" : "ies"}`,
    );
  }
  return orphans.length;
}

export async function clearCityCache(cityId: string): Promise<void> {
  try { localStorage.removeItem(META_KEY(cityId)); } catch { /* ignore */ }
  try { localStorage.removeItem(DATA_KEY(cityId)); } catch { /* ignore */ }
  try {
    const db = await openIDB();
    const tx = db.transaction(IDB_STORE, "readwrite");
    tx.objectStore(IDB_STORE).delete(DATA_KEY(cityId));
    await new Promise<void>((res) => { tx.oncomplete = () => res(); tx.onerror = () => res(); });
  } catch { /* ignore */ }
}

export async function loadCityCacheAsync(
  cityId: string,
): Promise<Map<string, PrecomputedParcelData> | null> {
  // Fast path: localStorage (small cities)
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(DATA_KEY(cityId)) : null;
    if (raw) {
      const obj = JSON.parse(raw) as Record<string, PrecomputedParcelData>;
      return new Map(Object.entries(obj));
    }
  } catch { /* fall through */ }

  // Slow path: IndexedDB (large cities)
  try {
    const db = await openIDB();
    return new Promise((resolve) => {
      const tx = db.transaction(IDB_STORE, "readonly");
      const req = tx.objectStore(IDB_STORE).get(DATA_KEY(cityId));
      req.onsuccess = () => {
        try {
          const raw = req.result as string | undefined;
          if (!raw) { resolve(null); return; }
          const obj = JSON.parse(raw) as Record<string, PrecomputedParcelData>;
          resolve(new Map(Object.entries(obj)));
        } catch { resolve(null); }
      };
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

// ── Main batch processor ───────────────────────────────────────────────────────

export interface PrecomputeRunResult {
  results: Map<string, PrecomputedParcelData>;
  /** Total eligible parcels for the jurisdiction at run time — the
   *  yardstick the load path uses to detect a partial save. Counts the
   *  full eligible population, NOT just the parcels this run had to
   *  process (which excludes anything already in existingData). */
  expected: number;
}

export async function precomputeCityIsochrones(
  parcels: CandidateParcelRow[],
  _cityId: string,
  callbacks: {
    onProgress: (status: PrecomputeStatus) => void;
    onParcelComputed: (parcelId: string, data: PrecomputedParcelData) => void;
    signal?: AbortSignal;
    existingData?: Map<string, PrecomputedParcelData>;
    /** When true, also call POST /api/parcels/value-density for each ring
     *  and merge `homesOver{1,2,5}M` into the ring metrics. Off by default
     *  so the existing precompute path costs nothing extra. Dashboard sets
     *  this when the user has a wealth-density slider enabled. */
    fetchHomeDensity?: boolean;
  },
): Promise<PrecomputeRunResult> {
  // When fetchHomeDensity=true, an already-cached parcel still needs
  // re-processing if its rings don't carry homesOver{1,2,5}M (which
  // were null in the cache from before the user enabled the slider).
  // Without this, Recompute is a no-op for the wealth-density path.
  const needsHomeDensityRefetch = (data: PrecomputedParcelData): boolean =>
    Object.values(data.rings).some((r) => r.homesOver1M == null);

  const skipIds = new Set<string>();
  if (callbacks.existingData) {
    callbacks.existingData.forEach((data, pid) => {
      if (callbacks.fetchHomeDensity && needsHomeDensityRefetch(data)) return;
      skipIds.add(pid);
    });
  }

  const allEligible = parcels.filter((p) =>
    ["permitted", "conditional", "unclear"].includes(p.storage_permission ?? ""),
  );
  const expected = allEligible.length;
  const eligible = allEligible.filter((p) => !skipIds.has(String(p.parcel_id)));

  const total = eligible.length;
  // Pre-populate results with already-computed data so saveCityCache includes everything
  const results = new Map<string, PrecomputedParcelData>(callbacks.existingData ?? []);
  let completed = 0;

  if (total === 0) {
    console.log("[precompute] All parcels already computed — nothing to do");
    return { results, expected };
  }

  console.log(`[precompute] Starting — ${total} parcels to compute (${skipIds.size} already cached)`);

  const CONCURRENCY = 4;
  const MIN_DELAY_MS = 250;
  let lastStart = 0;

  // Write-through buffer for the shared server cache. Demographics for each
  // freshly-computed parcel are batched and POSTed best-effort, so the next
  // load (any user) reads them back instead of recomputing. Failures are
  // swallowed — they must never block or abort the precompute.
  const writeBuffer: RingDemographicWrite[] = [];
  const flushWriteBuffer = async (): Promise<void> => {
    const batch = writeBuffer.splice(0, 200);
    if (batch.length === 0) return;
    await api.upsertRingDemographicsBulk(batch).catch(() => {});
  };

  async function processOne(parcel: CandidateParcelRow): Promise<void> {
    if (callbacks.signal?.aborted) return;

    const now = Date.now();
    const wait = Math.max(0, lastStart + MIN_DELAY_MS - now);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    if (callbacks.signal?.aborted) return;
    lastStart = Date.now();

    const centroid = parcelCentroid(parcel);
    if (!centroid) {
      console.warn(`[precompute] No centroid for parcel ${parcel.parcel_id}`);
      return;
    }

    const [lng, lat] = centroid;
    const parcelId = String(parcel.parcel_id);

    try {
      console.log(`[precompute] Fetching isochrone for parcel ${parcelId} (${lat.toFixed(4)},${lng.toFixed(4)})`);
      const isoResult = await fetchIsochrone(lat, lng);
      if (callbacks.signal?.aborted) return;

      console.log(`[precompute] Got isochrone for ${parcelId}, fetching census tracts...`);
      const [tracts2, tracts5, tracts10, tracts15] = await Promise.all([
        fetchCensusTracts(isoResult.polygons.min2),
        fetchCensusTracts(isoResult.polygons.min5),
        fetchCensusTracts(isoResult.polygons.min10),
        fetchCensusTracts(isoResult.polygons.min15),
      ]);
      if (callbacks.signal?.aborted) return;

      const data: PrecomputedParcelData = {
        parcelId,
        rings: {
          2:  computeRingMetrics(tracts2),
          5:  computeRingMetrics(tracts5),
          10: computeRingMetrics(tracts10),
          15: computeRingMetrics(tracts15),
        },
      };

      if (callbacks.fetchHomeDensity) {
        // One backend call per ring. The endpoint caches by
        // (parcel_id, drive_time_minutes) so repeat calls are O(1).
        const parcelIdNum = Number(parcelId);
        const ringPairs: Array<[2 | 5 | 10 | 15, Feature<Polygon | MultiPolygon>]> = [
          [2,  isoResult.polygons.min2  as Feature<Polygon | MultiPolygon>],
          [5,  isoResult.polygons.min5  as Feature<Polygon | MultiPolygon>],
          [10, isoResult.polygons.min10 as Feature<Polygon | MultiPolygon>],
          [15, isoResult.polygons.min15 as Feature<Polygon | MultiPolygon>],
        ];
        const densities = await Promise.all(
          ringPairs.map(([dt, feat]) =>
            fetchHomeDensityForRing(feat.geometry as never, {
              parcelId: Number.isFinite(parcelIdNum) ? parcelIdNum : undefined,
              driveTimeMinutes: dt,
            }).catch(() => null),
          ),
        );
        ringPairs.forEach(([dt], idx) => {
          const d = densities[idx];
          if (!d) return;
          const ring = data.rings[dt];
          ring.homesOver1M = d.homesOver1M;
          ring.homesOver2M = d.homesOver2M;
          ring.homesOver5M = d.homesOver5M;
        });
      }

      results.set(parcelId, data);
      completed++;

      // Write demographics through to the shared server cache (best-effort,
      // batched). homes_over_* are NOT sent here — they persist via the
      // value-density endpoint, so we don't risk clobbering them.
      const parcelIdNum = Number(parcelId);
      if (Number.isFinite(parcelIdNum)) {
        for (const dt of _RING_TIMES) {
          const ring = data.rings[dt];
          writeBuffer.push({
            parcel_id: parcelIdNum,
            drive_time_minutes: dt,
            population: finiteOrNull(ring.totalPopulation),
            median_hhi: finiteOrNull(ring.weightedMedianHHI),
            median_home_value: finiteOrNull(ring.weightedMedianHomeValue),
            hnw_households: finiteOrNull(ring.hnwHouseholds),
          });
        }
        if (writeBuffer.length >= 200) void flushWriteBuffer();
      }

      console.log(`[precompute] ✓ ${parcelId} — ${completed}/${total} — pop@10min: ${data.rings[10].totalPopulation.toLocaleString()}`);

      callbacks.onParcelComputed(parcelId, data);
      callbacks.onProgress({ progress: completed, total, complete: completed === total });
    } catch (err) {
      if (callbacks.signal?.aborted) return;
      console.warn(`[precompute] Failed for parcel ${parcelId}:`, err);
      // Skip failed parcels — don't abort the whole run
    }
  }

  // Manual concurrency semaphore: N workers each drain the queue
  const queue = [...eligible];
  const workers: Promise<void>[] = [];
  for (let i = 0; i < CONCURRENCY; i++) {
    workers.push(
      (async () => {
        while (queue.length > 0 && !callbacks.signal?.aborted) {
          const parcel = queue.shift()!;
          await processOne(parcel);
        }
      })(),
    );
  }

  await Promise.allSettled(workers);

  // Drain any remaining write-through items to the shared cache.
  while (writeBuffer.length > 0) {
    await flushWriteBuffer();
  }

  if (!callbacks.signal?.aborted) {
    console.log(`[precompute] Complete — ${results.size} parcels computed`);
  }

  return { results, expected };
}
