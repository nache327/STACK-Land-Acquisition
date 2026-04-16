"use client";

/**
 * MapLibre GL JS map component.
 *
 * Phase 2:
 *  - Loads all parcel polygons as a GeoJSON source from the backend.
 *  - Fill layer colored by zoning_code.
 *  - Hover: tooltip with APN + acres.
 *  - Click: fires onParcelClick with parcel id.
 *  - Selected parcel highlighted in emerald.
 *
 * Must be dynamically imported (no SSR).
 * Usage:
 *   const ParcelMap = dynamic(() => import('@/components/Map'), { ssr: false })
 */

import { useEffect, useRef, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useParcelMapLayer } from "@/hooks/useParcels";

// ─── Zone color palette (MapLibre "match" expression) ───────────────────────
// Returns a compact MapLibre expression that maps known Draper zone codes to
// brand colors.  Unknown codes fall back to slate-400.

function buildZoneColorExpression(): maplibregl.ExpressionSpecification {
  return [
    "match",
    ["get", "zoning_code"],
    // Industrial / commercial-park
    ["M1", "ML"],                         "#3b82f6", // blue-500
    ["CBP", "CP"],                        "#8b5cf6", // violet-500
    // Commercial
    ["CG", "CC"],                         "#f59e0b", // amber-500
    ["CS", "CN", "CB"],                   "#f97316", // orange-500
    ["CO"],                               "#eab308", // yellow-500
    // Residential
    ["R-1-20", "R-1-12", "R-1-10", "R-1-8", "R-1-6", "R-1-4", "R1"],
                                          "#94a3b8", // slate-400
    ["R-2", "R-3", "RM-11", "RM-17", "RM-24", "RM", "RMH"],
                                          "#cbd5e1", // slate-300
    // Open / public
    ["OS", "OF", "PF", "IN"],             "#86efac", // green-300
    // Agriculture
    ["A-1", "A1"],                        "#d9f99d", // lime-200
    /* default */                         "#94a3b8",  // slate-400
  ] as unknown as maplibregl.ExpressionSpecification;
}

// ─── Component ───────────────────────────────────────────────────────────────

interface MapProps {
  jurisdictionId: string;
  selectedParcelId?: number | null;
  onParcelClick?: (parcelId: number) => void;
}

const PARCEL_SOURCE = "parcels";
const PARCEL_FILL = "parcels-fill";
const PARCEL_LINE = "parcels-line";
const PARCEL_SELECTED = "parcels-selected";

// pg_tileserv URL — when set, use vector tiles instead of GeoJSON for better performance
const TILESERV_URL = process.env.NEXT_PUBLIC_TILESERV_URL ?? null;

// Draper, UT center (fallback before parcels load)
const DEFAULT_CENTER: [number, number] = [-111.868, 40.524];

export default function Map({
  jurisdictionId,
  selectedParcelId,
  onParcelClick,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const tooltipRef = useRef<maplibregl.Popup | null>(null);

  const { data: geojson } = useParcelMapLayer(jurisdictionId);

  const style =
    process.env.NEXT_PUBLIC_MAPLIBRE_STYLE ??
    "https://tiles.openfreemap.org/styles/liberty";

  // ── Initialise map ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style,
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

  // Store jurisdictionId in a ref so the tile URL filter can access it
  const jurisdictionIdRef = useRef(jurisdictionId);
  jurisdictionIdRef.current = jurisdictionId;

  // ── Load parcel layer once map + data are ready ───────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    // Vector tile mode: add source immediately on style load (no geojson needed)
    // GeoJSON mode: wait for geojson data
    if (!map || (!TILESERV_URL && !geojson)) return;

    const addLayers = () => {
      // Clean up any stale layers/source from a prior load
      if (map.getLayer(PARCEL_SELECTED)) map.removeLayer(PARCEL_SELECTED);
      if (map.getLayer(PARCEL_LINE)) map.removeLayer(PARCEL_LINE);
      if (map.getLayer(PARCEL_FILL)) map.removeLayer(PARCEL_FILL);
      if (map.getSource(PARCEL_SOURCE)) map.removeSource(PARCEL_SOURCE);

      const sourceLayer = TILESERV_URL ? "parcels" : undefined;

      if (TILESERV_URL) {
        // ── Vector tile source from pg_tileserv ────────────────────────────
        map.addSource(PARCEL_SOURCE, {
          type: "vector",
          tiles: [`${TILESERV_URL}/public.parcels/{z}/{x}/{y}.pbf`],
          minzoom: 10,
          maxzoom: 22,
        });
      } else {
        // ── GeoJSON source (fallback) ──────────────────────────────────────
        map.addSource(PARCEL_SOURCE, {
          type: "geojson",
          data: geojson!,
          generateId: false,
        });
      }

      const jurisdictionFilter: maplibregl.FilterSpecification | null = TILESERV_URL
        ? ["==", ["get", "jurisdiction_id"], jurisdictionIdRef.current ?? ""]
        : null;

      // Fill layer — colored by zone
      map.addLayer({
        id: PARCEL_FILL,
        type: "fill",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        ...(jurisdictionFilter ? { filter: jurisdictionFilter } : {}),
        paint: {
          "fill-color": buildZoneColorExpression(),
          "fill-opacity": [
            "case",
            ["==", ["get", "has_structure"], false], 0.65,
            0.35,
          ],
        },
      } as maplibregl.LayerSpecification);

      // Outline
      map.addLayer({
        id: PARCEL_LINE,
        type: "line",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        ...(jurisdictionFilter ? { filter: jurisdictionFilter } : {}),
        paint: {
          "line-color": "#64748b",
          "line-width": 0.5,
          "line-opacity": 0.6,
        },
      } as maplibregl.LayerSpecification);

      // Selected highlight (rendered on top)
      map.addLayer({
        id: PARCEL_SELECTED,
        type: "fill",
        source: PARCEL_SOURCE,
        ...(sourceLayer ? { "source-layer": sourceLayer } : {}),
        paint: {
          "fill-color": "#059669",
          "fill-opacity": 0.5,
        },
        filter: ["==", ["id"], -1], // nothing selected initially
      } as maplibregl.LayerSpecification);

      // Fit bounds to parcels (GeoJSON mode only — vector tiles auto-pan)
      if (!TILESERV_URL && geojson && geojson.features.length > 0) {
        let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
        for (const f of geojson.features) {
          if (!f.geometry) continue;
          const coords = flattenCoords(f.geometry as GeoJSON.Geometry);
          for (const [lng, lat] of coords) {
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

  // ── Click handler ─────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const onClick = (e: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: [PARCEL_FILL],
      });
      if (features.length > 0) {
        const id = features[0].properties?.id as number | undefined;
        if (id !== undefined) onParcelClick?.(id);
      }
    };

    map.on("click", PARCEL_FILL, onClick);
    return () => { map.off("click", PARCEL_FILL, onClick); };
  }, [onParcelClick]);

  // ── Hover tooltip ─────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    const popup = tooltipRef.current;
    if (!map || !popup) return;

    const onMouseMove = (e: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: [PARCEL_FILL],
      });
      if (features.length === 0) {
        popup.remove();
        map.getCanvas().style.cursor = "";
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      const props = features[0].properties ?? {};
      popup
        .setLngLat(e.lngLat)
        .setHTML(
          `<div class="text-xs space-y-0.5">
            <div class="font-mono font-semibold">${props.apn ?? "—"}</div>
            <div>${props.zoning_code ?? "—"} &middot; ${
              props.acres != null ? Number(props.acres).toFixed(2) + " ac" : "—"
            }</div>
            ${props.has_structure === false ? '<div class="text-emerald-700 font-medium">Vacant</div>' : ""}
            ${props.in_flood_zone ? '<div class="text-red-600 font-medium">Flood zone</div>' : ""}
          </div>`
        )
        .addTo(map);
    };

    const onMouseLeave = () => {
      popup.remove();
      map.getCanvas().style.cursor = "";
    };

    map.on("mousemove", PARCEL_FILL, onMouseMove);
    map.on("mouseleave", PARCEL_FILL, onMouseLeave);
    return () => {
      map.off("mousemove", PARCEL_FILL, onMouseMove);
      map.off("mouseleave", PARCEL_FILL, onMouseLeave);
    };
  }, []);

  // ── Highlight selected parcel ─────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(PARCEL_SELECTED)) return;
    map.setFilter(
      PARCEL_SELECTED,
      selectedParcelId !== null && selectedParcelId !== undefined
        ? ["==", ["get", "id"], selectedParcelId]
        : ["==", ["id"], -1]
    );
  }, [selectedParcelId]);

  return <div ref={containerRef} className="h-full w-full" />;
}

// ─── Geometry helpers ────────────────────────────────────────────────────────

function flattenCoords(
  geometry: GeoJSON.Geometry
): [number, number][] {
  switch (geometry.type) {
    case "Point":
      return [geometry.coordinates as [number, number]];
    case "MultiPoint":
    case "LineString":
      return geometry.coordinates as [number, number][];
    case "MultiLineString":
    case "Polygon":
      return (geometry.coordinates as [number, number][][]).flat();
    case "MultiPolygon":
      return (geometry.coordinates as [number, number][][][]).flat(2);
    case "GeometryCollection":
      return geometry.geometries.flatMap(flattenCoords);
    default:
      return [];
  }
}
