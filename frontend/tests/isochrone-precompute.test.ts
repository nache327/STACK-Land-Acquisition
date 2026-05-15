/**
 * Unit + integration tests for the partial-cache recovery in
 * isochrone-precompute. See the v7 changelog comment in
 * lib/isochrone-precompute.ts for the bug these tests guard against:
 * a partial precompute run on a Somerset-sized jurisdiction used to
 * persist as "complete," locking every un-fetched parcel into
 * "Computing…" in the drawer forever.
 */

// ── Minimal in-memory IndexedDB shim ──────────────────────────────────────
// jsdom doesn't ship IndexedDB and we don't want to pull fake-indexeddb
// just for these tests. The shim implements only what openIDB / writeToIDB
// / loadCityCacheAsync touch: open with onupgradeneeded creating a store,
// transaction("readwrite"|"readonly"), objectStore.put/get/delete with
// onsuccess/onerror events, and tx.oncomplete/onerror.
type Store = Map<string, unknown>;
const _idbStores: Map<string, Map<string, Store>> = new Map();
let _idbThrowOnWrite = false;

function installIDBShim(): void {
  const indexedDB = {
    open(dbName: string, _version: number) {
      const req: Record<string, unknown> = {};
      queueMicrotask(() => {
        let db = _idbStores.get(dbName);
        const isNew = !db;
        if (!db) {
          db = new Map();
          _idbStores.set(dbName, db);
        }
        const result = {
          transaction(storeName: string, _mode: string) {
            const store = db!.get(storeName) ?? (() => {
              const s: Store = new Map();
              db!.set(storeName, s);
              return s;
            })();
            const tx: Record<string, unknown> = {
              objectStore(_n: string) {
                return {
                  put(value: unknown, key: string) {
                    if (_idbThrowOnWrite) {
                      queueMicrotask(() => {
                        (tx.onerror as (() => void) | undefined)?.();
                      });
                    } else {
                      store.set(key, value);
                    }
                    return { onsuccess: null, onerror: null };
                  },
                  get(key: string) {
                    const r: Record<string, unknown> = { result: store.get(key) };
                    queueMicrotask(() => {
                      (r.onsuccess as (() => void) | undefined)?.();
                    });
                    return r;
                  },
                  delete(key: string) {
                    store.delete(key);
                    return { onsuccess: null, onerror: null };
                  },
                };
              },
              oncomplete: null,
              onerror: null,
            };
            queueMicrotask(() => {
              if (!_idbThrowOnWrite) {
                (tx.oncomplete as (() => void) | undefined)?.();
              }
            });
            return tx;
          },
          createObjectStore(name: string) {
            const s: Store = new Map();
            db!.set(name, s);
            return s;
          },
        };
        if (isNew) {
          const upgradeEvent = { target: { result } } as unknown as Event;
          (req.onupgradeneeded as ((e: Event) => void) | undefined)?.(upgradeEvent);
        }
        const successEvent = { target: { result } } as unknown as Event;
        (req.onsuccess as ((e: Event) => void) | undefined)?.(successEvent);
      });
      return req;
    },
  };
  (globalThis as unknown as { indexedDB: unknown }).indexedDB = indexedDB;
}

function resetIDB(): void {
  _idbStores.clear();
  _idbThrowOnWrite = false;
}

installIDBShim();

// ── Now safe to import the module under test ──────────────────────────────
import {
  saveCityCache,
  loadCityCacheAsync,
  getCacheMetadata,
  clearCityCache,
  purgeOrphanMeta,
  type PrecomputedParcelData,
  type CacheMeta,
} from "@/lib/isochrone-precompute";

const CITY = "test-city-uuid";

function makeRing() {
  return {
    totalPopulation: 1000,
    hnwHouseholds: 10,
    weightedMedianHHI: 100_000,
    weightedMedianHomeValue: 500_000,
    homesOver1M: null,
    homesOver2M: null,
    homesOver5M: null,
    tractCount: 1,
    lastComputed: "2026-05-15T00:00:00Z",
  };
}

function makeParcel(id: string): PrecomputedParcelData {
  return {
    parcelId: id,
    rings: { 2: makeRing(), 5: makeRing(), 10: makeRing(), 15: makeRing() },
  };
}

function buildResults(n: number): Map<string, PrecomputedParcelData> {
  const m = new Map<string, PrecomputedParcelData>();
  for (let i = 0; i < n; i++) m.set(`p${i}`, makeParcel(`p${i}`));
  return m;
}

beforeEach(() => {
  localStorage.clear();
  resetIDB();
});

describe("CacheMeta v7 shape", () => {
  it("persists saved + expected + lastComputed", async () => {
    const results = buildResults(20);
    await saveCityCache(CITY, results, 100);

    const meta = getCacheMetadata(CITY) as CacheMeta | null;
    expect(meta).not.toBeNull();
    expect(meta!.saved).toBe(20);
    expect(meta!.expected).toBe(100);
    expect(typeof meta!.lastComputed).toBe("string");
  });

  it("ignores stale v6 entries by using new key prefix", () => {
    // Simulate a v6 entry that should be invisible to v7 readers.
    localStorage.setItem(
      "parcellogic_precompute_meta_v6_" + CITY,
      JSON.stringify({ lastComputed: "old", total: 50 }),
    );
    expect(getCacheMetadata(CITY)).toBeNull();
  });
});

describe("partial save detection", () => {
  it("meta.saved < meta.expected signals partial", async () => {
    await saveCityCache(CITY, buildResults(20), 100);
    const meta = getCacheMetadata(CITY)!;
    expect(meta.saved).toBeLessThan(meta.expected);
  });

  it("full save reports saved === expected", async () => {
    await saveCityCache(CITY, buildResults(50), 50);
    const meta = getCacheMetadata(CITY)!;
    expect(meta.saved).toBe(meta.expected);
  });
});

describe("storage routing by expected size", () => {
  it("small cities (<= 500) use localStorage", async () => {
    await saveCityCache(CITY, buildResults(10), 100);
    const raw = localStorage.getItem("parcellogic_precompute_v7_" + CITY);
    expect(raw).not.toBeNull();
    const obj = JSON.parse(raw!);
    expect(Object.keys(obj)).toHaveLength(10);
  });

  it("large cities (> 500) use IndexedDB, leaving localStorage clean", async () => {
    await saveCityCache(CITY, buildResults(600), 2253);
    expect(localStorage.getItem("parcellogic_precompute_v7_" + CITY)).toBeNull();
    const loaded = await loadCityCacheAsync(CITY);
    expect(loaded).not.toBeNull();
    expect(loaded!.size).toBe(600);
  });
});

describe("localStorage quota fallback to IndexedDB", () => {
  it("falls through to IDB on QuotaExceededError", async () => {
    const real = Storage.prototype.setItem;
    const spy = jest.spyOn(Storage.prototype, "setItem");
    spy.mockImplementation(function (this: Storage, k: string, v: string) {
      // Only the data blob trips the quota; meta is tiny and proceeds.
      if (k === "parcellogic_precompute_v7_" + CITY) {
        const err: Error & { name?: string } = new Error("quota");
        err.name = "QuotaExceededError";
        throw err;
      }
      return real.call(this, k, v);
    });

    try {
      await saveCityCache(CITY, buildResults(50), 100);
      // Data fell through to IDB, so localStorage has no data blob…
      // …but meta IS in localStorage because IDB persisted.
      const meta = getCacheMetadata(CITY);
      expect(meta).not.toBeNull();
      expect(meta!.saved).toBe(50);
      // And the data is readable via load (which checks IDB next).
      const loaded = await loadCityCacheAsync(CITY);
      expect(loaded).not.toBeNull();
      expect(loaded!.size).toBe(50);
    } finally {
      spy.mockRestore();
    }
  });
});

describe("meta is not written when persistence fails", () => {
  it("clears meta if IDB write fails (no poisoned 'complete' on next load)", async () => {
    // Seed a prior good meta so we can confirm it gets cleared.
    localStorage.setItem(
      "parcellogic_precompute_meta_v7_" + CITY,
      JSON.stringify({ lastComputed: "stale", saved: 999, expected: 999 }),
    );

    _idbThrowOnWrite = true;
    // Use a large expected to force IDB branch.
    await saveCityCache(CITY, buildResults(600), 600);

    expect(getCacheMetadata(CITY)).toBeNull();
  });
});

describe("save order — meta only after data persists", () => {
  it("does NOT write meta when both localStorage and IDB writes fail", async () => {
    // Force the small-city localStorage path AND make it throw quota,
    // then force IDB to fail too — meta must not appear.
    const spy = jest.spyOn(Storage.prototype, "setItem");
    spy.mockImplementation(function (this: Storage, k: string, _v: string) {
      // Block the data blob; permit unrelated keys.
      if (k.startsWith("parcellogic_precompute_v7_")) {
        const err: Error & { name?: string } = new Error("quota");
        err.name = "QuotaExceededError";
        throw err;
      }
      // Also block meta to detect any rogue meta write.
      if (k.startsWith("parcellogic_precompute_meta_v7_")) {
        throw new Error("meta should not be written when data failed");
      }
    });
    _idbThrowOnWrite = true;
    try {
      // expected=100 → small-city path tries localStorage first, falls
      // through to IDB which also throws. Both fail → no meta.
      await saveCityCache(CITY, buildResults(50), 100);
    } finally {
      spy.mockRestore();
    }
    // getCacheMetadata reads the real localStorage (mock is gone) — meta key absent.
    expect(getCacheMetadata(CITY)).toBeNull();
  });
});

describe("purgeOrphanMeta — cross-version meta cleanup", () => {
  it("deletes v6 meta when no v6 data exists anywhere (the Somerset bug)", async () => {
    localStorage.setItem(
      "parcellogic_precompute_meta_v6_somerset-jid",
      JSON.stringify({ lastComputed: "2026-05-14T12:00:00Z", total: 141 }),
    );

    const purged = await purgeOrphanMeta();

    expect(purged).toBe(1);
    expect(localStorage.getItem("parcellogic_precompute_meta_v6_somerset-jid")).toBeNull();
  });

  it("keeps meta when corresponding data IS in localStorage", async () => {
    localStorage.setItem(
      "parcellogic_precompute_meta_v6_keep-jid",
      JSON.stringify({ lastComputed: "x", total: 5 }),
    );
    localStorage.setItem("parcellogic_precompute_v6_keep-jid", "{}");

    const purged = await purgeOrphanMeta();

    expect(purged).toBe(0);
    expect(localStorage.getItem("parcellogic_precompute_meta_v6_keep-jid")).not.toBeNull();
  });

  it("keeps meta when corresponding data IS in IDB", async () => {
    // Stage data into IDB via a real save under a v7 key, then add a
    // matching meta and confirm purge leaves it alone.
    await saveCityCache("lehi-jid", buildResults(600), 600); // forces IDB

    const purged = await purgeOrphanMeta();

    expect(purged).toBe(0);
    expect(getCacheMetadata("lehi-jid")).not.toBeNull();
  });

  it("scans across all v{N} versions", async () => {
    localStorage.setItem("parcellogic_precompute_meta_v3_a", JSON.stringify({ total: 1 }));
    localStorage.setItem("parcellogic_precompute_meta_v6_b", JSON.stringify({ total: 1 }));
    localStorage.setItem("parcellogic_precompute_meta_v7_c", JSON.stringify({ saved: 1, expected: 1 }));

    const purged = await purgeOrphanMeta();

    expect(purged).toBe(3);
    expect(localStorage.getItem("parcellogic_precompute_meta_v3_a")).toBeNull();
    expect(localStorage.getItem("parcellogic_precompute_meta_v6_b")).toBeNull();
    expect(localStorage.getItem("parcellogic_precompute_meta_v7_c")).toBeNull();
  });

  it("ignores unrelated localStorage keys", async () => {
    localStorage.setItem("satThresholdLow", "5000");
    localStorage.setItem("some_other_app_data", JSON.stringify({ x: 1 }));

    const purged = await purgeOrphanMeta();

    expect(purged).toBe(0);
    expect(localStorage.getItem("satThresholdLow")).toBe("5000");
    expect(localStorage.getItem("some_other_app_data")).not.toBeNull();
  });
});

describe("orphan meta in load path (the actual reported failure)", () => {
  it("getCacheMetadata returns null after purge cleans an orphan v7 entry", async () => {
    // Pre-populate v7 meta with no data anywhere — mirrors the
    // production Somerset state if a save attempt had partially written.
    localStorage.setItem(
      "parcellogic_precompute_meta_v7_" + CITY,
      JSON.stringify({ lastComputed: "x", saved: 141, expected: 141 }),
    );

    expect(getCacheMetadata(CITY)).not.toBeNull(); // present before purge
    await purgeOrphanMeta();
    expect(getCacheMetadata(CITY)).toBeNull();     // gone after purge

    // And loadCityCacheAsync returns null — confirming "no cache" state.
    const cached = await loadCityCacheAsync(CITY);
    expect(cached).toBeNull();
  });
});

describe("clearCityCache wipes all v7 locations", () => {
  it("removes meta, localStorage data, and IDB data", async () => {
    await saveCityCache(CITY, buildResults(50), 50);
    expect(getCacheMetadata(CITY)).not.toBeNull();

    await clearCityCache(CITY);

    expect(getCacheMetadata(CITY)).toBeNull();
    expect(localStorage.getItem("parcellogic_precompute_v7_" + CITY)).toBeNull();
    expect(await loadCityCacheAsync(CITY)).toBeNull();
  });
});
