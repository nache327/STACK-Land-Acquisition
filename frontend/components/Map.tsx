"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useParcelMapLayer } from "@/hooks/useParcels";
import type { FilterState } from "@/components/FilterPanel";

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

// ─── Filter builder ───────────────────────────────────────────────────────────
//
// Returns a MapLibre filter that includes only QUALIFYING parcels.
// Returns null when no filters are active (show everything).
//
// Strategy: two layers —
//   PARCEL_DIM   = all parcels, dark gray, always visible (provides context)
//   PARCEL_FILL  = qualifying parcels only, bright green (set via setFilter)
//
// This avoids complex paint expressions that can fail silently.

function buildQualifyingFilter(
  filters: FilterState
): maplibregl.FilterSpecification | null {
  const conditions: maplibregl.ExpressionSpecification[] = [];

  if (filters.vacantOnly) {
    // Only exclude parcels we KNOW have a structure (true).
    // null = unknown = treat as potentially vacant.
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

  if (conditions.length === 0) return null; // no filter = show all
  if (conditions.length === 1) return conditions[0] as unknown as maplibregl.FilterSpecification;
  return ["all", ...conditions] as unknown as maplibregl.FilterSpecification;
}

// ─── Component ────────────────────────────────────────────────────────────────

interface MapProps {
  jurisdictionId: string;
  filters: FilterState;
  selectedParcelId?: number | null;
  onParcelClick?: (parcelId: number) => void;
}

const PARCEL_SOURCE   = "parcels";
const PARCEL_DIM      = "parcels-dim";      // always visible, dark gray
const PARCEL_FILL     = "parcels-fill";     // qualifying only, bright green
const PARCEL_LINE     = "parcels-line";
const PARCEL_SELECTED = "parcels-selected";

const TILESERV_URL = process.env.NEXT_PUBLIC_TILESERV_URL ?? null;
const DEFAULT_CENTER: [number, number] = [-111.868, 40.524];

export default function Map({
  jurisdictionId,
  filters,
  selectedParcelId,
  onParcelClick,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef       = useRef<maplibregl.Map | null>(null);
  const tooltipRef   = useRef<maplibregl.Popup | null>(null);

  const { data: geojson } = useParcelMapLayer(jurisdictionId);

  // ── Initialise map ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: SATELLITE_STYLE,
      center: DEFAULT_CENTER,
      zoom: 12,
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

  const jurisdictionIdRef = useRef(jurisdictionId);
  jurisdictionIdRef.current = jurisdictionId;

  // keep latest filters in a ref so the once("load") closure can access them
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  // ── Load parcel layers once map + data are ready ──────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || (!TILESERV_URL && !geojson)) return;

    const addLayers = () => {
      // Remove stale layers/source if re-running
      [PARCEL_SELECTED, PARCEL_LINE, PARCEL_FILL, PARCEL_DIM].forEach((id) => {
        if (map.getLayer(id)) map.removeLayer(id);
      });
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

      // 1. Dim base — every parcel, always, very dark
      map.addLayer({
        id: PARCEL_DIM,
        type: "fill",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        ...(jFilter ? { filter: jFilter } : {}),
        paint: {
          "fill-color": "#0f172a",
          "fill-opacity": 0.25,
        },
      } as maplibregl.LayerSpecification);

      // 2. Bright qualifying layer — filtered, green gradient
      const qualFilter = buildQualifyingFilter(filtersRef.current);
      map.addLayer({
        id: PARCEL_FILL,
        type: "fill",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        filter: qualFilter ?? ["boolean", true],
        paint: {
          // Confirmed vacant = neon green; unknown = bright green
          "fill-color": [
            "case",
            ["==", ["get", "has_structure"], false], "#39ff14",
            "#00e676",
          ],
          "fill-opacity": 0.72,
        },
      } as maplibregl.LayerSpecification);

      // 3. Outline
      map.addLayer({
        id: PARCEL_LINE,
        type: "line",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        ...(jFilter ? { filter: jFilter } : {}),
        paint: {
          "line-color": "#ffffff",
          "line-width": 0.4,
          "line-opacity": 0.3,
        },
      } as maplibregl.LayerSpecification);

      // 4. Selected highlight on top
      map.addLayer({
        id: PARCEL_SELECTED,
        type: "fill",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        paint: {
          "fill-color": "#fbbf24",
          "fill-opacity": 0.85,
        },
        filter: ["==", ["id"], -1],
      } as maplibregl.LayerSpecification);

      // Fit bounds to parcels
      if (!TILESERV_URL && geojson && geojson.features.length > 0) {
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
            padding: 40,
            maxZoom: 14,
          });
        }
      }
    };

    if (map.isStyleLoaded()) {
      addLayers();
    } else {
      map.once("load", addLayers);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geojson]);

  // ── Update qualifying filter when filters change ───────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(PARCEL_FILL)) return;
    const f = buildQualifyingFilter(filters);
    map.setFilter(PARCEL_FILL, f ?? ["boolean", true]);
  }, [filters]);

  // ── Click handler ─────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: [PARCEL_FILL, PARCEL_DIM] });
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

  // ── Hover tooltip ─────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    const popup = tooltipRef.current;
    if (!map || !popup) return;

    const onMouseMove = (e: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: [PARCEL_FILL, PARCEL_DIM] });
      if (features.length === 0) {
        popup.remove();
        map.getCanvas().style.cursor = "";
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      const props = features[0].properties ?? {};
      const isVacant  = props.has_structure === false;
      const hasFlood  = props.in_flood_zone === true;
      const hasWetland = props.in_wetland === true;

      popup
        .setLngLat(e.lngLat)
        .setHTML(
          `<div class="text-xs space-y-0.5">
            <div class="font-mono font-semibold">${props.apn ?? "—"}</div>
            <div>${props.zoning_code ?? "—"} &middot; ${
              props.acres != null ? Number(props.acres).toFixed(2) + " ac" : "—"
            }</div>
            ${isVacant ? '<div class="text-green-700 font-medium">Vacant</div>' : ""}
            ${hasFlood ? '<div class="text-red-500 font-medium">⚠ Flood zone</div>' : ""}
            ${hasWetland ? '<div class="text-blue-500 font-medium">⚠ Wetland</div>' : ""}
          </div>`
        )
        .addTo(map);
    };

    const onMouseLeave = () => {
      popup.remove();
      map.getCanvas().style.cursor = "";
    };

    map.on("mousemove", PARCEL_FILL, onMouseMove);
    map.on("mousemove", PARCEL_DIM,  onMouseMove);
    map.on("mouseleave", PARCEL_FILL, onMouseLeave);
    map.on("mouseleave", PARCEL_DIM,  onMouseLeave);
    return () => {
      map.off("mousemove", PARCEL_FILL, onMouseMove);
      map.off("mousemove", PARCEL_DIM,  onMouseMove);
      map.off("mouseleave", PARCEL_FILL, onMouseLeave);
      map.off("mouseleave", PARCEL_DIM,  onMouseLeave);
    };
  }, []);

  // ── Highlight selected parcel ─────────────────────────────────────────────
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

  return <div ref={containerRef} className="h-full w-full" />;
}

// ─── Geometry helpers ─────────────────────────────────────────────────────────

function flattenCoords(geometry: GeoJSON.Geometry): [number, number][] {
  switch (geometry.type) {
    case "Point":       return [geometry.coordinates as [number, number]];
    case "MultiPoint":
    case "LineString":  return geometry.coordinates as [number, number][];
    case "MultiLineString":
    case "Polygon":     return (geometry.coordinates as [number, number][][]).flat();
    case "MultiPolygon": return (geometry.coordinates as [number, number][][][]).flat(2);
    case "GeometryCollection": return geometry.geometries.flatMap(flattenCoords);
    default:            return [];
  }
}
