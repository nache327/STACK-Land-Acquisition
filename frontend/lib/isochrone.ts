/**
 * Shared isochrone fetch + Census wealth engine.
 * Used by the Keep scoring layer and the drive-time ring renderer.
 *
 * All results are module-level cached — never refetch a cached key.
 */
import union from "@turf/union";
import booleanPointInPolygon from "@turf/boolean-point-in-polygon";
import intersect from "@turf/intersect";
import type { Feature, Polygon, MultiPolygon, FeatureCollection, Point } from "geojson";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface IsochronePolygons {
  min2:  Feature<Polygon | MultiPolygon>;
  min5:  Feature<Polygon | MultiPolygon>;
  min10: Feature<Polygon | MultiPolygon>;
  min15: Feature<Polygon | MultiPolygon>;
}

export interface IsochroneResult {
  polygons: IsochronePolygons;
  lat: number;
  lng: number;
}

export interface TractData {
  geoid: string;
  statefp: string;
  countyfp: string;
  tractce: string;
  median_hhi: number | null;
  median_home_value: number | null;
  household_count: number | null;
  /** Polygon clipped to the query polygon. Null if no overlap. */
  clipped_geometry: Feature<Polygon | MultiPolygon> | null;
}

// ── Module-level caches ───────────────────────────────────────────────────────

const isochroneCache = new Map<string, IsochroneResult>();
const tractCache = new Map<string, TractData[]>();

export function getIsochroneCache(): ReadonlyMap<string, IsochroneResult> {
  return isochroneCache;
}

export function clearIsochroneCache(): void {
  isochroneCache.clear();
  tractCache.clear();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function bboxOf(feature: Feature<Polygon | MultiPolygon>): [number, number, number, number] {
  const coords: number[][] = [];
  const collect = (c: unknown): void => {
    if (!Array.isArray(c)) return;
    if (typeof c[0] === "number") { coords.push(c as number[]); return; }
    (c as unknown[]).forEach(collect);
  };
  collect(feature.geometry.coordinates);
  const lngs = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

function centroidOf(feature: Feature<Polygon | MultiPolygon>): [number, number] {
  const [minLng, minLat, maxLng, maxLat] = bboxOf(feature);
  return [(minLng + maxLng) / 2, (minLat + maxLat) / 2];
}

function bboxCacheKey(polygon: Feature<Polygon | MultiPolygon>): string {
  const [w, s, e, n] = bboxOf(polygon);
  return `${w.toFixed(2)},${s.toFixed(2)},${e.toFixed(2)},${n.toFixed(2)}`;
}

function mergePolygons(features: Feature[]): Feature<Polygon | MultiPolygon> {
  const polys = features as Feature<Polygon | MultiPolygon>[];
  if (polys.length === 1) return polys[0];
  let merged = polys[0];
  for (let i = 1; i < polys.length; i++) {
    const result = union(
      { type: "FeatureCollection", features: [merged, polys[i]] } as FeatureCollection<Polygon | MultiPolygon>
    );
    if (result) merged = result;
  }
  return merged;
}

// ── fetchIsochrone ────────────────────────────────────────────────────────────

export async function fetchIsochrone(lat: number, lng: number): Promise<IsochroneResult> {
  const key = `${lat.toFixed(4)},${lng.toFixed(4)}`;
  if (isochroneCache.has(key)) return isochroneCache.get(key)!;

  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
  if (!token) throw new Error("NEXT_PUBLIC_MAPBOX_TOKEN not configured");

  const url =
    `https://api.mapbox.com/isochrone/v1/mapbox/driving/${lng},${lat}` +
    `?contours_minutes=2,5,10,15&polygons=true&denoise=0.25&generalize=100` +
    `&access_token=${token}`;

  const res = await fetch(url, { signal: AbortSignal.timeout(10_000) });
  if (!res.ok) throw new Error(`Mapbox isochrone API ${res.status}: ${await res.text()}`);

  const fc = (await res.json()) as FeatureCollection;

  const byContour: Record<number, Feature[]> = { 2: [], 5: [], 10: [], 15: [] };
  for (const f of fc.features) {
    const contour = (f.properties as Record<string, number>)?.contour;
    if (contour in byContour) byContour[contour].push(f);
  }

  for (const [c, feats] of Object.entries(byContour)) {
    if (!feats.length) throw new Error(`Mapbox returned no polygon for ${c}-min contour`);
  }

  const result: IsochroneResult = {
    lat,
    lng,
    polygons: {
      min2:  mergePolygons(byContour[2]),
      min5:  mergePolygons(byContour[5]),
      min10: mergePolygons(byContour[10]),
      min15: mergePolygons(byContour[15]),
    },
  };

  isochroneCache.set(key, result);
  return result;
}

// ── fetchCensusTracts ─────────────────────────────────────────────────────────

type CensusGeocoderResponse = {
  result: {
    geographies: {
      "Census Tracts"?: Array<{ STATE: string; COUNTY: string; TRACT: string }>;
    };
  };
};

async function getFipsFromPoint(lng: number, lat: number): Promise<{ state: string; county: string } | null> {
  try {
    const url =
      `https://geocoding.geo.census.gov/geocoder/geographies/coordinates` +
      `?x=${lng}&y=${lat}&benchmark=Public_AR_Current&vintage=Current_Current` +
      `&layers=Census%20Tracts&format=json`;
    const res = await fetch(url, { signal: AbortSignal.timeout(8_000) });
    if (!res.ok) return null;
    const data = (await res.json()) as CensusGeocoderResponse;
    const tracts = data.result?.geographies?.["Census Tracts"];
    if (!tracts?.length) return null;
    return { state: tracts[0].STATE, county: tracts[0].COUNTY };
  } catch {
    return null;
  }
}

type AcsRow = string[];

async function fetchAcsForCounty(
  statefp: string,
  countyfp: string
): Promise<Map<string, { hhi: number | null; homeValue: number | null; households: number | null }>> {
  const url =
    `https://api.census.gov/data/2022/acs/acs5` +
    `?get=B19013_001E,B25077_001E,B11001_001E` +
    `&for=tract:*&in=state:${statefp}&in=county:${countyfp}`;

  const res = await fetch(url, { signal: AbortSignal.timeout(12_000) });
  if (!res.ok) return new Map();

  const rows = (await res.json()) as AcsRow[];
  const [headers, ...data] = rows;
  const hi = headers.indexOf("B19013_001E");
  const hvi = headers.indexOf("B25077_001E");
  const hhi2 = headers.indexOf("B11001_001E");
  const si = headers.indexOf("state");
  const ci = headers.indexOf("county");
  const ti = headers.indexOf("tract");

  const out = new Map<string, { hhi: number | null; homeValue: number | null; households: number | null }>();
  for (const row of data) {
    const geoid = row[si] + row[ci] + row[ti];
    const parseN = (v: string) => (v === null || v === "-666666666" || v === "" ? null : Number(v));
    out.set(geoid, {
      hhi: parseN(row[hi]),
      homeValue: parseN(row[hvi]),
      households: parseN(row[hhi2]),
    });
  }
  return out;
}

async function fetchTractGeometries(
  bbox: [number, number, number, number]
): Promise<FeatureCollection> {
  const [w, s, e, n] = bbox;
  const geometry = encodeURIComponent(
    JSON.stringify({ xmin: w, ymin: s, xmax: e, ymax: n, spatialReference: { wkid: 4326 } })
  );
  const url =
    `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/14/query` +
    `?geometry=${geometry}&geometryType=esriGeometryEnvelope&spatialRel=esriSpatialRelIntersects` +
    `&outFields=GEOID,STATE,COUNTY,TRACT&returnGeometry=true&f=geojson`;

  const res = await fetch(url, { signal: AbortSignal.timeout(15_000) });
  if (!res.ok) return { type: "FeatureCollection", features: [] };
  return (await res.json()) as FeatureCollection;
}

export async function fetchCensusTracts(
  polygon: Feature<Polygon | MultiPolygon>
): Promise<TractData[]> {
  const cacheKey = bboxCacheKey(polygon);
  if (tractCache.has(cacheKey)) return tractCache.get(cacheKey)!;

  const centroid = centroidOf(polygon);
  const fips = await getFipsFromPoint(centroid[0], centroid[1]);
  if (!fips) return [];

  const [acsData, tractFC] = await Promise.all([
    fetchAcsForCounty(fips.state, fips.county),
    fetchTractGeometries(bboxOf(polygon)),
  ]);

  if (!tractFC.features.length) return [];

  // Build centroid point for each tract to filter by polygon containment
  const results: TractData[] = [];

  for (const feat of tractFC.features) {
    const props = (feat.properties ?? {}) as Record<string, string>;
    const geoid = String(props.GEOID ?? "");
    if (!geoid) continue;

    const tractGeom = feat as Feature<Polygon | MultiPolygon>;

    // Compute centroid of the tract geometry
    const tractBbox = bboxOf(tractGeom);
    const tractCentroid: Feature<Point> = {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [
          (tractBbox[0] + tractBbox[2]) / 2,
          (tractBbox[1] + tractBbox[3]) / 2,
        ],
      },
      properties: {},
    };

    // Only include tracts whose centroid is inside the query polygon
    if (!booleanPointInPolygon(tractCentroid, polygon)) continue;

    // Clip tract geometry to the query polygon
    let clipped: Feature<Polygon | MultiPolygon> | null = null;
    try {
      const fc: FeatureCollection<Polygon | MultiPolygon> = {
        type: "FeatureCollection",
        features: [
          tractGeom as Feature<Polygon | MultiPolygon>,
          polygon as Feature<Polygon | MultiPolygon>,
        ],
      };
      clipped = intersect(fc);
    } catch {
      clipped = tractGeom as Feature<Polygon | MultiPolygon>;
    }

    const acs = acsData.get(geoid);

    results.push({
      geoid,
      statefp:  fips.state,
      countyfp: fips.county,
      tractce:  String(props.TRACT ?? ""),
      median_hhi:         acs?.hhi        ?? null,
      median_home_value:  acs?.homeValue  ?? null,
      household_count:    acs?.households ?? null,
      clipped_geometry: clipped,
    });
  }

  tractCache.set(cacheKey, results);
  return results;
}
