"use client";

import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useParcelMapLayer } from "@/hooks/useParcels";
import { useJurisdictionBounds } from "@/hooks/useJurisdictionBounds";
import type { FilterState } from "@/components/FilterPanel";
import { LayerControl, type LayerVisibility } from "@/components/LayerControl";
import { LAYER_REGISTRY, ZONE_CLASS_COLORS } from "@/lib/layers";

// ─── Satellite base style ─────────────────────────────────────────────────────

const SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "© Esri, Maxar, Earthstar Geographics",
      maxzoom: 19,
    },
    labels: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
    },
  },
  layers: [
    { id: "satellite-layer", type: "raster", source: "satellite" },
    {
      id: "labels-layer",
      type: "raster",
      source: "labels",
      paint: { "raster-opacity": 0.85 },
    },
  ],
};

// ─── Filter builder for parcels layer ─────────────────────────────────────────

function buildQualifyingFilter(
  filters: FilterState
): maplibregl.FilterSpecification | null {
  const conditions: maplibregl.ExpressionSpecification[] = [];

  if (filters.vacantOnly) {
    conditions.push(["!=", ["get", "has_structure"], true] as maplibregl.ExpressionSpecification);
  }
  if (filters.excludeFlood) {
    conditions.push(["!=", ["get", "in_flood_zone"], true] as maplibregl.ExpressionSpecification);
  }
  if (filters.excludeWetland) {
    conditions.push(["!=", ["get", "in_wetland"], true] as maplibregl.ExpressionSpecification);
  }
  if (filters.zones.length > 0) {
    conditions.push(
      ["in", ["get", "zoning_code"], ["literal", filters.zones]] as maplibregl.ExpressionSpecification
    );
  }
  if (filters.zoneClasses && filters.zoneClasses.length > 0) {
    conditions.push(
      ["in", ["get", "zone_class"], ["literal", filters.zoneClasses]] as maplibregl.ExpressionSpecification
    );
  }
  if (filters.minAcres != null) {
    conditions.push(
      [">=", ["to-number", ["get", "acres"]], filters.minAcres] as maplibregl.ExpressionSpecification
    );
  }
  if (filters.maxAcres != null) {
    conditions.push(
      ["<=", ["to-number", ["get", "acres"]], filters.maxAcres] as maplibregl.ExpressionSpecification
    );
  }

  if (conditions.length === 0) return null;
  if (conditions.length === 1) return conditions[0] as unknown as maplibregl.FilterSpecification;
  return ["all", ...conditions] as unknown as maplibregl.FilterSpecification;
}

// ─── Component ────────────────────────────────────────────────────────────────

interface MapProps {
  jurisdictionId: string;
  filters: FilterState;
  selectedParcelId?: number | null;
  onParcelClick?: (parcelId: number) => void;
  visibility: LayerVisibility;
  onVisibilityChange: (next: LayerVisibility) => void;
}

const PARCEL_SOURCE = "parcels";
const PARCEL_DIM = "parcels-dim";
const PARCEL_FILL = "parcels-fill";
const PARCEL_LINE = "parcels-line";
const PARCEL_SELECTED = "parcels-selected";

// Fallback color for parcels that lack a zone_class value (e.g., jurisdictions
// without a zoning polygon layer, or parcels outside any district).
const UNCLASSIFIED_PARCEL_COLOR = "#94a3b8";

const TILESERV_URL = process.env.NEXT_PUBLIC_TILESERV_URL ?? null;
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
// Center of the continental US — used when we have no jurisdiction bbox yet.
const DEFAULT_CENTER: [number, number] = [-98.5, 39.5];

export default function Map({
  jurisdictionId,
  filters,
  selectedParcelId,
  onParcelClick,
  visibility,
  onVisibilityChange,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const tooltipRef = useRef<maplibregl.Popup | null>(null);

  const { data: geojson } = useParcelMapLayer(jurisdictionId);
  const { data: bounds } = useJurisdictionBounds(jurisdictionId);

  // ── Initialise map ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: SATELLITE_STYLE,
      center: DEFAULT_CENTER,
      zoom: 4,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(
      new maplibregl.ScaleControl({ maxWidth: 100, unit: "imperial" }),
      "bottom-left"
    );

    tooltipRef.current = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 8,
    });

    mapRef.current = map;
    return () => {
      tooltipRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Fit to jurisdiction bbox once available ──────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bounds) return;
    map.fitBounds(
      [
        [bounds[0], bounds[1]],
        [bounds[2], bounds[3]],
      ],
      { padding: 40, maxZoom: 14, duration: 800 }
    );
  }, [bounds]);

  const jurisdictionIdRef = useRef(jurisdictionId);
  jurisdictionIdRef.current = jurisdictionId;
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  // ── Add registry layers (zoning + overlays) ──────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !jurisdictionId) return;

    const addRegistryLayers = () => {
      for (const layer of LAYER_REGISTRY) {
        // parcels source is managed below; skip it here
        if (layer.id === "parcels") continue;

        const src = layer.source({
          jurisdictionId,
          tileservUrl: TILESERV_URL,
          apiBaseUrl: API_BASE_URL,
        });

        // Remove stale source/layers if reusing map
        for (const mlId of layer.mapLayerIds) {
          if (map.getLayer(mlId)) map.removeLayer(mlId);
        }
        if (map.getSource(src.id)) map.removeSource(src.id);

        if (src.type === "vector") {
          map.addSource(src.id, {
            type: "vector",
            tiles: src.tiles,
            minzoom: src.minzoom,
            maxzoom: src.maxzoom,
          });
        } else {
          map.addSource(src.id, { type: "geojson", data: src.data });
        }

        for (const spec of layer.layers({
          jurisdictionId,
          tileservUrl: TILESERV_URL,
          apiBaseUrl: API_BASE_URL,
        })) {
          map.addLayer(spec);
        }
      }
    };

    if (map.isStyleLoaded()) {
      addRegistryLayers();
    } else {
      map.once("load", addRegistryLayers);
    }
  }, [jurisdictionId]);

  // ── Parcel source + layers (kept dynamic: filter-driven paint) ───────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || (!TILESERV_URL && !geojson)) return;

    const addParcelLayers = () => {
      for (const id of [PARCEL_SELECTED, PARCEL_LINE, PARCEL_FILL, PARCEL_DIM]) {
        if (map.getLayer(id)) map.removeLayer(id);
      }
      if (map.getSource(PARCEL_SOURCE)) map.removeSource(PARCEL_SOURCE);

      const sourceLayer = TILESERV_URL ? "parcels" : undefined;

      if (TILESERV_URL) {
        map.addSource(PARCEL_SOURCE, {
          type: "vector",
          tiles: [`${TILESERV_URL}/public.parcels/{z}/{x}/{y}.pbf`],
          minzoom: 10,
          maxzoom: 22,
        });
      } else {
        map.addSource(PARCEL_SOURCE, {
          type: "geojson",
          data: geojson!,
          generateId: false,
        });
      }

      const jFilter: maplibregl.FilterSpecification | null = TILESERV_URL
        ? ["==", ["get", "jurisdiction_id"], jurisdictionIdRef.current ?? ""]
        : null;

      map.addLayer({
        id: PARCEL_DIM,
        type: "fill",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        ...(jFilter ? { filter: jFilter } : {}),
        paint: { "fill-color": "#0f172a", "fill-opacity": 0.25 },
      } as maplibregl.LayerSpecification);

      const qualFilter = buildQualifyingFilter(filtersRef.current);
      map.addLayer({
        id: PARCEL_FILL,
        type: "fill",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        filter: qualFilter ?? ["boolean", true],
        paint: {
          "fill-color": [
            "match", ["get", "storage_permission"],
            "permitted",    "#10b981",
            "conditional",  "#f59e0b",
            "prohibited",   "#6b7280",
            UNCLASSIFIED_PARCEL_COLOR,
          ] as maplibregl.ExpressionSpecification,
          "fill-opacity": [
            "match", ["get", "storage_permission"],
            "permitted",    0.82,
            "conditional",  0.45,
            "prohibited",   0.35,
            0.45,
          ] as maplibregl.ExpressionSpecification,
        },
      } as maplibregl.LayerSpecification);

      map.addLayer({
        id: PARCEL_LINE,
        type: "line",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        ...(jFilter ? { filter: jFilter } : {}),
        paint: { "line-color": "#ffffff", "line-width": 0.4, "line-opacity": 0.3 },
      } as maplibregl.LayerSpecification);

      map.addLayer({
        id: PARCEL_SELECTED,
        type: "fill",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        paint: { "fill-color": "#fbbf24", "fill-opacity": 0.85 },
        filter: ["==", ["id"], -1],
      } as maplibregl.LayerSpecification);

      // Fit bounds for GeoJSON fallback (vector tiles use jurisdiction bbox)
      if (!TILESERV_URL && geojson && geojson.features.length > 0 && !bounds) {
        let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
        for (const f of geojson.features) {
          if (!f.geometry) continue;
          for (const [lng, lat] of flattenCoords(f.geometry as GeoJSON.Geometry)) {
            if (lng < minLng) minLng = lng;
            if (lat < minLat) minLat = lat;
            if (lng > maxLng) maxLng = lng;
            if (lat > maxLat) maxLat = lat;
          }
        }
        if (isFinite(minLng)) {
          map.fitBounds([[minLng, minLat], [maxLng, maxLat]], {
            padding: 40, maxZoom: 14,
          });
        }
      }
    };

    if (map.isStyleLoaded()) {
      addParcelLayers();
    } else {
      map.once("load", addParcelLayers);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geojson]);

  // ── Update parcel qualifying filter when filters change ──────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(PARCEL_FILL)) return;
    const f = buildQualifyingFilter(filters);
    map.setFilter(PARCEL_FILL, f ?? ["boolean", true]);
  }, [filters]);

  // ── Apply visibility + opacity from LayerControl ─────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const layer of LAYER_REGISTRY) {
      const state = visibility[layer.id];
      if (!state) continue;
      for (const mlId of layer.mapLayerIds) {
        if (!map.getLayer(mlId)) continue;
        map.setLayoutProperty(
          mlId,
          "visibility",
          state.visible ? "visible" : "none"
        );
        // Apply opacity to whichever paint property this layer supports
        try {
          const type = (map.getLayer(mlId) as maplibregl.LayerSpecification)?.type;
          if (type === "fill") {
            map.setPaintProperty(mlId, "fill-opacity", state.opacity);
          } else if (type === "line") {
            map.setPaintProperty(mlId, "line-opacity", state.opacity);
          }
        } catch {
          /* no-op — layer may not yet be added */
        }
      }
    }
  }, [visibility]);

  // ── Click + hover handlers on parcels layer ──────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: [PARCEL_FILL, PARCEL_DIM],
      });
      if (features.length > 0) {
        const id = features[0].properties?.id as number | undefined;
        if (id !== undefined) onParcelClick?.(id);
      }
    };
    map.on("click", PARCEL_FILL, onClick);
    map.on("click", PARCEL_DIM, onClick);
    return () => {
      map.off("click", PARCEL_FILL, onClick);
      map.off("click", PARCEL_DIM, onClick);
    };
  }, [onParcelClick]);

  useEffect(() => {
    const map = mapRef.current;
    const popup = tooltipRef.current;
    if (!map || !popup) return;

    const onMouseMove = (e: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: [PARCEL_FILL, PARCEL_DIM],
      });
      if (features.length === 0) {
        popup.remove();
        map.getCanvas().style.cursor = "";
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      const props = features[0].properties ?? {};
      const isVacant = props.has_structure === false;
      const hasFlood = props.in_flood_zone === true;
      const hasWetland = props.in_wetland === true;
      const klass = (props.zone_class as string | undefined) ?? "unknown";

      popup
        .setLngLat(e.lngLat)
        .setHTML(
          `<div style="font-size:12px;line-height:1.5">
            <div style="font-family:monospace;font-weight:700">${props.apn ?? "—"}</div>
            <div>${props.zoning_code ?? "—"} · ${
              props.acres != null ? Number(props.acres).toFixed(2) + " ac" : "—"
            }</div>
            <div style="color:${ZONE_CLASS_COLORS[klass as keyof typeof ZONE_CLASS_COLORS] ?? "#94a3b8"};font-weight:500">${klass}</div>
            ${isVacant ? '<div style="color:#059669;font-weight:500">Vacant</div>' : ""}
            ${hasFlood ? '<div style="color:#dc2626;font-weight:500">⚠ Flood zone</div>' : ""}
            ${hasWetland ? '<div style="color:#2563eb;font-weight:500">⚠ Wetland</div>' : ""}
          </div>`
        )
        .addTo(map);
    };

    const onMouseLeave = () => {
      popup.remove();
      map.getCanvas().style.cursor = "";
    };

    map.on("mousemove", PARCEL_FILL, onMouseMove);
    map.on("mousemove", PARCEL_DIM, onMouseMove);
    map.on("mouseleave", PARCEL_FILL, onMouseLeave);
    map.on("mouseleave", PARCEL_DIM, onMouseLeave);
    return () => {
      map.off("mousemove", PARCEL_FILL, onMouseMove);
      map.off("mousemove", PARCEL_DIM, onMouseMove);
      map.off("mouseleave", PARCEL_FILL, onMouseLeave);
      map.off("mouseleave", PARCEL_DIM, onMouseLeave);
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(PARCEL_SELECTED)) return;
    map.setFilter(
      PARCEL_SELECTED,
      selectedParcelId != null
        ? ["==", ["get", "id"], selectedParcelId]
        : ["==", ["id"], -1]
    );
  }, [selectedParcelId]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      <LayerControl visibility={visibility} onChange={onVisibilityChange} />
    </div>
  );
}

// ─── Geometry helpers ─────────────────────────────────────────────────────────

function flattenCoords(geometry: GeoJSON.Geometry): [number, number][] {
  switch (geometry.type) {
    case "Point": return [geometry.coordinates as [number, number]];
    case "MultiPoint":
    case "LineString": return geometry.coordinates as [number, number][];
    case "MultiLineString":
    case "Polygon": return (geometry.coordinates as [number, number][][]).flat();
    case "MultiPolygon": return (geometry.coordinates as [number, number][][][]).flat(2);
    case "GeometryCollection": return geometry.geometries.flatMap(flattenCoords);
    default: return [];
  }
}
