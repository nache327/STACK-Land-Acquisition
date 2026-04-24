/**
 * Layer registry — single source of truth for MapLibre data layers.
 *
 * `Map.tsx` iterates this registry to add sources + layers. `LayerControl.tsx`
 * iterates it to render toggles + a dynamic legend. Adding a new layer =
 * editing this file only.
 *
 * Visibility model:
 *   - Each LayerDef lists one or more MapLibre layer IDs (`mapLayerIds`).
 *     These are the layers that belong to the logical "data layer" and flip
 *     together when the user toggles it. For `parcels`, this is dim + fill +
 *     line + selected — they all share a source and must stay in sync.
 *
 * Paint policy for the zoning-districts class colors is centralized so other
 * components (legend, intensity renderers) can re-use it.
 */
import type { FilterSpecification, LayerSpecification } from "maplibre-gl";
import type { ZoneClass } from "./schemas";

// ── Color palette for zone_class ──────────────────────────────────────────────

export const ZONE_CLASS_COLORS: Record<ZoneClass, string> = {
  residential: "#60a5fa",   // blue-400
  commercial: "#f472b6",    // pink-400
  industrial: "#a78bfa",    // violet-400
  mixed_use: "#fbbf24",     // amber-400
  agricultural: "#84cc16",  // lime-500
  open_space: "#22c55e",    // green-500
  special: "#e879f9",       // fuchsia-400
  overlay: "#f87171",       // red-400
  unknown: "#94a3b8",       // slate-400
};

export const ZONE_CLASS_LABELS: Record<ZoneClass, string> = {
  residential: "Residential",
  commercial: "Commercial",
  industrial: "Industrial",
  mixed_use: "Mixed Use",
  agricultural: "Agricultural",
  open_space: "Open Space",
  special: "Special",
  overlay: "Overlay",
  unknown: "Unclassified",
};

// ── Source + layer types ──────────────────────────────────────────────────────

export type LayerCategory = "base" | "data" | "overlay";

export interface LegendSwatch {
  color: string;
  label: string;
}

export interface LayerDef {
  id: string;
  title: string;
  description: string;
  category: LayerCategory;
  defaultVisible: boolean;
  // Opacity UI default (0–1)
  defaultOpacity: number;
  // MapLibre source spec factory — receives jurisdiction context.
  source: (ctx: LayerContext) => LayerSourceSpec;
  // One or more MapLibre layer specs (fill + line, fill + extrusion, etc.).
  layers: (ctx: LayerContext) => LayerSpecification[];
  // MapLibre layer IDs owned by this logical layer; toggles flip visibility
  // on all of them.
  mapLayerIds: string[];
  // Static legend swatches. Dynamic legends (e.g., zoning by class) pass
  // swatches via LegendSwatch.
  legend?: LegendSwatch[];
}

export interface LayerContext {
  jurisdictionId: string;
  tileservUrl: string | null;
  apiBaseUrl: string;
}

export type LayerSourceSpec =
  | {
      id: string;
      type: "vector";
      tiles: string[];
      minzoom?: number;
      maxzoom?: number;
      sourceLayer: string; // name published by pg_tileserv
    }
  | {
      id: string;
      type: "geojson";
      data: string; // URL to GeoJSON blob (FeatureCollection)
    };

// ── Layer definitions ─────────────────────────────────────────────────────────

// Zoning districts — rendered *below* parcels-fill so parcels stay clickable.
const ZONING_DISTRICTS: LayerDef = {
  id: "zoning_districts",
  title: "Zoning Districts",
  description: "Zoning-polygon boundaries, colored by class",
  category: "data",
  defaultVisible: false,
  defaultOpacity: 0.45,
  source: ({ jurisdictionId, tileservUrl, apiBaseUrl }) =>
    tileservUrl
      ? {
          id: "zoning-districts",
          type: "vector",
          tiles: [
            `${tileservUrl}/public.zoning_districts/{z}/{x}/{y}.pbf?filter=jurisdiction_id='${jurisdictionId}'`,
          ],
          sourceLayer: "zoning_districts",
          minzoom: 8,
          maxzoom: 22,
        }
      : {
          id: "zoning-districts",
          type: "geojson",
          data: `${apiBaseUrl}/api/jurisdictions/${jurisdictionId}/zoning-districts/map`,
        },
  layers: ({ tileservUrl }) => {
    const sourceLayer = tileservUrl ? { "source-layer": "zoning_districts" } : {};
    return [
      {
        id: "zoning-districts-fill",
        type: "fill",
        source: "zoning-districts",
        ...(sourceLayer as object),
        paint: {
          "fill-color": [
            "match",
            ["get", "zone_class"],
            "residential", ZONE_CLASS_COLORS.residential,
            "commercial", ZONE_CLASS_COLORS.commercial,
            "industrial", ZONE_CLASS_COLORS.industrial,
            "mixed_use", ZONE_CLASS_COLORS.mixed_use,
            "agricultural", ZONE_CLASS_COLORS.agricultural,
            "open_space", ZONE_CLASS_COLORS.open_space,
            "special", ZONE_CLASS_COLORS.special,
            "overlay", ZONE_CLASS_COLORS.overlay,
            ZONE_CLASS_COLORS.unknown,
          ],
          "fill-opacity": 0.45,
        },
      } as LayerSpecification,
      {
        id: "zoning-districts-line",
        type: "line",
        source: "zoning-districts",
        ...(sourceLayer as object),
        paint: {
          "line-color": "#1e293b",
          "line-width": 0.7,
          "line-opacity": 0.6,
        },
      } as LayerSpecification,
    ];
  },
  mapLayerIds: ["zoning-districts-fill", "zoning-districts-line"],
  legend: Object.entries(ZONE_CLASS_COLORS).map(([key, color]) => ({
    color,
    label: ZONE_CLASS_LABELS[key as ZoneClass],
  })),
};

// Parcels — kept on top so click/hover still target parcels. Note: parcel
// source + layers are built inside Map.tsx because they need a dynamic filter
// (qualifying parcels) that changes over time; this registry entry only
// declares metadata and mapLayerIds for the visibility toggle.
const PARCELS: LayerDef = {
  id: "parcels",
  title: "Parcels",
  description: "Individual parcel boundaries",
  category: "data",
  defaultVisible: true,
  defaultOpacity: 0.85,
  source: () => ({
    id: "parcels",
    type: "vector",
    tiles: [],
    sourceLayer: "parcels",
  }),
  layers: () => [],
  mapLayerIds: ["parcels-dim", "parcels-fill", "parcels-line", "parcels-selected"],
};

// FEMA flood zones — pg_tileserv serves the overlays_flood_sfha view.
const OVERLAY_FLOOD: LayerDef = {
  id: "overlay_flood",
  title: "Flood Zones (FEMA)",
  description: "FEMA NFHL Special Flood Hazard Areas",
  category: "overlay",
  defaultVisible: false,
  defaultOpacity: 0.4,
  source: ({ tileservUrl, apiBaseUrl, jurisdictionId }) =>
    tileservUrl
      ? {
          id: "overlay-flood",
          type: "vector",
          tiles: [
            `${tileservUrl}/public.overlays_flood_sfha/{z}/{x}/{y}.pbf?filter=jurisdiction_id='${jurisdictionId}'`,
          ],
          sourceLayer: "overlays_flood_sfha",
          minzoom: 6,
          maxzoom: 22,
        }
      : {
          id: "overlay-flood",
          type: "geojson",
          data: `${apiBaseUrl}/api/overlays/flood_sfha/map?jurisdiction_id=${jurisdictionId}`,
        },
  layers: ({ tileservUrl }) => {
    const sourceLayer = tileservUrl
      ? { "source-layer": "overlays_flood_sfha" }
      : {};
    return [
      {
        id: "overlay-flood-fill",
        type: "fill",
        source: "overlay-flood",
        ...(sourceLayer as object),
        paint: {
          "fill-color": "#2563eb",
          "fill-opacity": 0.35,
        },
      } as LayerSpecification,
    ];
  },
  mapLayerIds: ["overlay-flood-fill"],
  legend: [{ color: "#2563eb", label: "FEMA SFHA (100-yr floodplain)" }],
};

const OVERLAY_WETLAND: LayerDef = {
  id: "overlay_wetland",
  title: "Wetlands (USFWS)",
  description: "USFWS National Wetlands Inventory",
  category: "overlay",
  defaultVisible: false,
  defaultOpacity: 0.4,
  source: ({ tileservUrl, apiBaseUrl, jurisdictionId }) =>
    tileservUrl
      ? {
          id: "overlay-wetland",
          type: "vector",
          tiles: [
            `${tileservUrl}/public.overlays_wetland_nwi/{z}/{x}/{y}.pbf?filter=jurisdiction_id='${jurisdictionId}'`,
          ],
          sourceLayer: "overlays_wetland_nwi",
          minzoom: 6,
          maxzoom: 22,
        }
      : {
          id: "overlay-wetland",
          type: "geojson",
          data: `${apiBaseUrl}/api/overlays/wetland_nwi/map?jurisdiction_id=${jurisdictionId}`,
        },
  layers: ({ tileservUrl }) => {
    const sourceLayer = tileservUrl
      ? { "source-layer": "overlays_wetland_nwi" }
      : {};
    return [
      {
        id: "overlay-wetland-fill",
        type: "fill",
        source: "overlay-wetland",
        ...(sourceLayer as object),
        paint: {
          "fill-color": "#06b6d4",
          "fill-opacity": 0.35,
        },
      } as LayerSpecification,
    ];
  },
  mapLayerIds: ["overlay-wetland-fill"],
  legend: [{ color: "#06b6d4", label: "NWI Wetland" }],
};

// Order matters: entries that render below should come first (base first,
// then zoning, then parcels, then overlays).
export const LAYER_REGISTRY: LayerDef[] = [
  ZONING_DISTRICTS,
  PARCELS,
  OVERLAY_FLOOD,
  OVERLAY_WETLAND,
];

// Helper: build the MapLibre filter that scopes a vector tile layer to a
// single jurisdiction. Works whether the source is vector (server filtered
// via the pg_tileserv ?filter= query param, but we add belt-and-suspenders)
// or GeoJSON (per-jurisdiction blob endpoint).
export function jurisdictionFilter(
  jurisdictionId: string | null
): FilterSpecification | null {
  if (!jurisdictionId) return null;
  return ["==", ["get", "jurisdiction_id"], jurisdictionId];
}
