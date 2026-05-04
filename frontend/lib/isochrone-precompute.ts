import { fetchIsochrone, fetchCensusTracts } from "@/lib/isochrone";
import type { TractData } from "@/lib/isochrone";
import type { CandidateParcelRow } from "@/lib/schemas";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface PrecomputedRingMetrics {
  totalPopulation: number;
  hnwHouseholds: number;
  weightedMedianHHI: number;
  weightedMedianHomeValue: number;
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
}

// ── Storage keys ───────────────────────────────────────────────────────────────

const META_KEY = (cityId: string) => `parcellogic_precompute_meta_v1_${cityId}`;
const DATA_KEY = (cityId: string) => `parcellogic_precompute_v1_${cityId}`;
const IDB_DB = "parcellogic_precompute";
const IDB_STORE = "cities";
const SMALL_CITY_THRESHOLD = 500;

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
  const totalPopulation = valid.reduce((s, t) => s + (t.household_count ?? 0), 0);

  const hnwHouseholds = valid
    .filter((t) => t.median_hhi != null && t.median_hhi > 150_000)
    .reduce((s, t) => s + (t.household_count ?? 0), 0);

  const hhiTracts = valid.filter((t) => t.median_hhi != null);
  const weightedMedianHHI =
    totalPopulation > 0
      ? hhiTracts.reduce((s, t) => s + t.median_hhi! * t.household_count!, 0) / totalPopulation
      : 0;

  const hvTracts = valid.filter((t) => t.median_home_value != null);
  const weightedMedianHomeValue =
    totalPopulation > 0
      ? hvTracts.reduce((s, t) => s + t.median_home_value! * t.household_count!, 0) / totalPopulation
      : 0;

  return {
    totalPopulation,
    hnwHouseholds,
    weightedMedianHHI,
    weightedMedianHomeValue,
    tractCount: tracts.length,
    lastComputed: new Date().toISOString(),
  };
}

// ── Cache ──────────────────────────────────────────────────────────────────────

export function getCacheMetadata(cityId: string): { lastComputed: string; total: number } | null {
  try {
    const raw = typeof window !== "undefined" ? localStorage.getItem(META_KEY(cityId)) : null;
    return raw ? JSON.parse(raw) : null;
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

export async function saveCityCache(
  cityId: string,
  data: Map<string, PrecomputedParcelData>,
  total: number,
): Promise<void> {
  const meta = { lastComputed: new Date().toISOString(), total };
  try { localStorage.setItem(META_KEY(cityId), JSON.stringify(meta)); } catch { /* quota */ }

  const serialized = JSON.stringify(Object.fromEntries(data));

  if (total <= SMALL_CITY_THRESHOLD) {
    try { localStorage.setItem(DATA_KEY(cityId), serialized); } catch { /* quota */ }
  } else {
    try {
      const db = await openIDB();
      const tx = db.transaction(IDB_STORE, "readwrite");
      tx.objectStore(IDB_STORE).put(serialized, DATA_KEY(cityId));
      await new Promise<void>((res, rej) => {
        tx.oncomplete = () => res();
        tx.onerror = () => rej(tx.error);
      });
    } catch (e) {
      console.warn("[precompute] IDB save failed:", e);
    }
  }
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

export async function precomputeCityIsochrones(
  parcels: CandidateParcelRow[],
  _cityId: string,
  callbacks: {
    onProgress: (status: PrecomputeStatus) => void;
    onParcelComputed: (parcelId: string, data: PrecomputedParcelData) => void;
    signal?: AbortSignal;
  },
): Promise<Map<string, PrecomputedParcelData>> {
  const eligible = parcels.filter((p) =>
    ["permitted", "conditional", "unclear"].includes(p.storage_permission ?? ""),
  );
  const total = eligible.length;
  const results = new Map<string, PrecomputedParcelData>();
  let completed = 0;

  console.log(`[precompute] Starting — ${total} eligible parcels`);

  const CONCURRENCY = 4;
  const MIN_DELAY_MS = 250;
  let lastStart = 0;

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

      results.set(parcelId, data);
      completed++;

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

  if (!callbacks.signal?.aborted) {
    console.log(`[precompute] Complete — ${results.size} parcels computed`);
  }

  return results;
}
