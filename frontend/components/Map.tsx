"use client";

import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useJurisdictionBounds } from "@/hooks/useJurisdictionBounds";
import { LayerControl, type LayerVisibility } from "@/components/LayerControl";
import { LAYER_REGISTRY, SATURATION_COLORS, ZONE_CLASS_COLORS, type ColorMode } from "@/lib/layers";
import type { CandidateParcelRow, SaturationBatchResult } from "@/lib/schemas";

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

interface MapProps {
  jurisdictionId: string;
  parcels: CandidateParcelRow[];
  isLoading?: boolean;
  selectedParcelId?: number | null;
  selectedParcelCentroid?: [number, number] | null;
  onParcelClick?: (parcelId: number) => void;
  onBoundsChange?: (bbox: [number, number, number, number]) => void;
  visibility: LayerVisibility;
  onVisibilityChange: (next: LayerVisibility) => void;
  colorMode?: ColorMode;
  saturationData?: Map<number, SaturationBatchResult>;
}

const PARCEL_SOURCE = "parcels";
const PARCEL_FILL = "parcels-fill";
const PARCEL_LINE = "parcels-line";
const PARCEL_SELECTED = "parcels-selected";
const UNCLASSIFIED_PARCEL_COLOR = "#94a3b8";
const TILESERV_URL = process.env.NEXT_PUBLIC_TILESERV_URL ?? null;
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEFAULT_CENTER: [number, number] = [-98.5, 39.5];

const OVERLAY_LAYER_IDS = ["overlay-flood-fill", "overlay-wetland-fill"];
const RING_SOURCE = "saturation-rings";
const RING_LAYER = "saturation-rings-line";
const RING_RADII_MILES = [1, 3, 5, 10];

function bboxCenter(geom: GeoJSON.Geometry): [number, number] | null {
  const flat: number[][] = [];
  const collect = (coords: unknown): void => {
    if (!Array.isArray(coords)) return;
    if (typeof coords[0] === "number") {
      flat.push(coords as number[]);
    } else {
      (coords as unknown[]).forEach(collect);
    }
  };
  if ("coordinates" in geom) collect(geom.coordinates);
  if (!flat.length) return null;
  const lngs = flat.map((c) => c[0]);
  const lats = flat.map((c) => c[1]);
  return [
    (Math.min(...lngs) + Math.max(...lngs)) / 2,
    (Math.min(...lats) + Math.max(...lats)) / 2,
  ];
}

export default function Map({
  jurisdictionId,
  parcels,
  isLoading = false,
  selectedParcelId,
  selectedParcelCentroid,
  onParcelClick,
  onBoundsChange,
  visibility,
  onVisibilityChange,
  colorMode = "permission",
  saturationData,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const tooltipRef = useRef<maplibregl.Popup | null>(null);
  const hasFitRef = useRef<string | null>(null);

  const { data: bounds } = useJurisdictionBounds(jurisdictionId);

  const parcelCollection = useMemo<GeoJSON.FeatureCollection>(() => {
    return {
      type: "FeatureCollection",
      features: parcels
        .filter((parcel) => parcel.geom)
        .map((parcel) => {
          const sat = saturationData?.get(parcel.parcel_id);
          const satColor = sat?.color ?? "nodata";
          return {
            type: "Feature" as const,
            id: parcel.parcel_id,
            properties: {
              parcel_id: parcel.parcel_id,
              apn: parcel.apn,
              address: parcel.address,
              acres: parcel.acres,
              zoning_code: parcel.zoning_code,
              zone_class: parcel.zone_class ?? "unknown",
              storage_permission: parcel.storage_permission ?? "unclassified",
              storage_allowed: parcel.storage_allowed,
              storage_conditional: parcel.storage_conditional,
              in_flood_zone: parcel.in_flood_zone,
              in_wetland: parcel.in_wetland,
              has_structure: parcel.has_structure,
              is_viable: parcel.is_viable,
              saturation_color: satColor,
            },
            geometry: parcel.geom as unknown as GeoJSON.Geometry,
          };
        }),
    };
  }, [parcels, saturationData]);

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
  }, []);

  useEffect(() => {
    hasFitRef.current = null;
  }, [jurisdictionId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bounds || hasFitRef.current === jurisdictionId) return;

    map.fitBounds(
      [
        [bounds[0], bounds[1]],
        [bounds[2], bounds[3]],
      ],
      { padding: 40, maxZoom: 14, duration: 800 }
    );

    hasFitRef.current = jurisdictionId;
  }, [bounds, jurisdictionId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !jurisdictionId) return;

    const addRegistryLayers = () => {
      for (const layer of LAYER_REGISTRY) {
        if (layer.id === "parcels") continue;

        for (const mapLayerId of layer.mapLayerIds) {
          if (map.getLayer(mapLayerId)) {
            map.removeLayer(mapLayerId);
          }
        }

        const source = layer.source({
          jurisdictionId,
          tileservUrl: TILESERV_URL,
          apiBaseUrl: API_BASE_URL,
        });

        if (!source) continue;

        if (map.getSource(source.id)) {
          map.removeSource(source.id);
        }

        if (source.type === "vector") {
          map.addSource(source.id, {
            type: "vector",
            tiles: source.tiles,
            minzoom: source.minzoom,
            maxzoom: source.maxzoom,
          });
        } else {
          map.addSource(source.id, {
            type: "geojson",
            data: source.data,
          });
        }

        for (const spec of layer.layers({
          jurisdictionId,
          tileservUrl: TILESERV_URL,
          apiBaseUrl: API_BASE_URL,
        })) {
          const specWithVisibility = layer.defaultVisible
            ? spec
            : {
                ...spec,
                layout: {
                  ...(spec.layout ?? {}),
                  visibility: "none" as const,
                },
              };

          map.addLayer(specWithVisibility);
        }
      }
    };

    if (map.isStyleLoaded()) {
      addRegistryLayers();
    } else {
      map.once("load", addRegistryLayers);
    }
  }, [jurisdictionId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const upsertParcelLayers = () => {
      const existingSource = map.getSource(PARCEL_SOURCE) as
        | maplibregl.GeoJSONSource
        | undefined;

      if (existingSource) {
        existingSource.setData(parcelCollection);
      } else {
        map.addSource(PARCEL_SOURCE, {
          type: "geojson",
          data: parcelCollection,
          generateId: false,
        });
      }

      const beforeId = OVERLAY_LAYER_IDS.find((layerId) => map.getLayer(layerId));

      if (!map.getLayer(PARCEL_FILL)) {
        map.addLayer(
          {
            id: PARCEL_FILL,
            type: "fill",
            source: PARCEL_SOURCE,
            paint: {
              "fill-color": [
                "match",
                ["get", "storage_permission"],
                "permitted",
                "#10b981",
                "conditional",
                "#f59e0b",
                "unclear",
                "#a78bfa",
                "prohibited",
                "#6b7280",
                UNCLASSIFIED_PARCEL_COLOR,
              ],
              "fill-opacity": [
                "match",
                ["get", "storage_permission"],
                "permitted",
                0.65,
                "conditional",
                0.55,
                "unclear",
                0.6,
                "prohibited",
                0.45,
                0.15,
              ],
            },
          },
          beforeId
        );
      }

      if (!map.getLayer(PARCEL_LINE)) {
        map.addLayer(
          {
            id: PARCEL_LINE,
            type: "line",
            source: PARCEL_SOURCE,
            paint: {
              "line-color": "#ffffff",
              "line-width": 0.6,
              "line-opacity": 0.5,
            },
          },
          beforeId
        );
      }

      if (!map.getLayer(PARCEL_SELECTED)) {
        map.addLayer({
          id: PARCEL_SELECTED,
          type: "line",
          source: PARCEL_SOURCE,
          paint: {
            "line-color": "#fbbf24",
            "line-width": 2,
            "line-opacity": 1,
          },
          filter: ["==", ["get", "parcel_id"], -1],
        });
      }
    };

    if (map.isStyleLoaded()) {
      upsertParcelLayers();
    } else {
      map.once("load", upsertParcelLayers);
    }
  }, [parcelCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(PARCEL_SELECTED)) return;

    map.setFilter(
      PARCEL_SELECTED,
      selectedParcelId != null
        ? ["==", ["get", "parcel_id"], selectedParcelId]
        : ["==", ["get", "parcel_id"], -1]
    );
  }, [selectedParcelId]);

  // Switch parcel fill color between permission-based and saturation-based
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer(PARCEL_FILL)) return;

    if (colorMode === "saturation") {
      map.setPaintProperty(PARCEL_FILL, "fill-color", [
        "match",
        ["get", "saturation_color"],
        "green",   SATURATION_COLORS.underserved,
        "yellow",  SATURATION_COLORS.borderline,
        "red",     SATURATION_COLORS.oversupplied,
        SATURATION_COLORS.nodata,
      ]);
    } else {
      map.setPaintProperty(PARCEL_FILL, "fill-color", [
        "match",
        ["get", "storage_permission"],
        "permitted",   "#10b981",
        "conditional", "#f59e0b",
        "unclear",     "#a78bfa",
        "prohibited",  "#6b7280",
        UNCLASSIFIED_PARCEL_COLOR,
      ]);
    }
  }, [colorMode]);

  // Draw saturation ring circles around the selected parcel
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const centroid = selectedParcelCentroid;

    const addRings = () => {
      if (!centroid) {
        // Remove rings if no parcel selected
        if (map.getLayer(RING_LAYER)) map.removeLayer(RING_LAYER);
        if (map.getSource(RING_SOURCE)) map.removeSource(RING_SOURCE);
        return;
      }

      // Build ring circles using @turf/circle
      const circle = require("@turf/circle").default as (
        center: [number, number],
        radiusMiles: number,
        options: { units: "miles"; steps: number }
      ) => GeoJSON.Feature;

      const features: GeoJSON.Feature[] = RING_RADII_MILES.map((r) =>
        circle(centroid, r, { units: "miles", steps: 64 })
      );
      const ringCollection: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features,
      };

      const existing = map.getSource(RING_SOURCE) as maplibregl.GeoJSONSource | undefined;
      if (existing) {
        existing.setData(ringCollection);
      } else {
        map.addSource(RING_SOURCE, { type: "geojson", data: ringCollection });
        map.addLayer({
          id: RING_LAYER,
          type: "line",
          source: RING_SOURCE,
          paint: {
            "line-color": "#fbbf24",
            "line-width": 1.5,
            "line-opacity": 0.7,
            "line-dasharray": [3, 2],
          },
        });
      }
    };

    if (map.isStyleLoaded()) {
      addRings();
    } else {
      map.once("load", addRings);
    }
  }, [selectedParcelCentroid]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    for (const layer of LAYER_REGISTRY) {
      const state = visibility[layer.id];
      if (!state) continue;

      for (const mapLayerId of layer.mapLayerIds) {
        if (!map.getLayer(mapLayerId)) continue;

        map.setLayoutProperty(
          mapLayerId,
          "visibility",
          state.visible ? "visible" : "none"
        );

        try {
          const type = (map.getLayer(mapLayerId) as maplibregl.LayerSpecification)
            ?.type;

          if (type === "fill") {
            map.setPaintProperty(mapLayerId, "fill-opacity", state.opacity);
          } else if (type === "line") {
            map.setPaintProperty(mapLayerId, "line-opacity", state.opacity);
          }
        } catch {
          // Layer may not be mounted yet.
        }
      }
    }
  }, [visibility]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !onBoundsChange) return;

    const handleMoveEnd = () => {
      const nextBounds = map.getBounds();

      onBoundsChange([
        nextBounds.getWest(),
        nextBounds.getSouth(),
        nextBounds.getEast(),
        nextBounds.getNorth(),
      ]);
    };

    map.on("moveend", handleMoveEnd);

    return () => {
      map.off("moveend", handleMoveEnd);
    };
  }, [onBoundsChange]);

  useEffect(() => {
    const map = mapRef.current;
    const popup = tooltipRef.current;
    if (!map || !popup) return;

    const queryParcelFeatures = (point: maplibregl.Point) =>
      map.queryRenderedFeatures(point, {
        layers: [PARCEL_SELECTED, PARCEL_FILL, PARCEL_LINE],
      });

    const queryCompetitorFeatures = (point: maplibregl.Point) =>
      map.getLayer("competitors-circle")
        ? map.queryRenderedFeatures(point, { layers: ["competitors-circle"] })
        : [];

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      const feature = queryParcelFeatures(event.point)[0];
      if (!feature) return;

      const rawId = feature.properties?.parcel_id;
      const parcelId = typeof rawId === "number" ? rawId : Number(rawId);

      if (Number.isFinite(parcelId)) {
        onParcelClick?.(parcelId);
      }
    };

    const handleMouseMove = (event: maplibregl.MapMouseEvent) => {
      // Check competitors first (they're on top of parcels)
      const competitorFeature = queryCompetitorFeatures(event.point)[0];
      if (competitorFeature) {
        const cp = competitorFeature.properties ?? {};
        const sqft = cp.sq_ft ? Number(cp.sq_ft).toLocaleString() : null;
        const sqftLabel = sqft
          ? `${sqft} sq ft${cp.sqft_source === "default" ? " (est.)" : ""}`
          : "Size unknown";
        map.getCanvas().style.cursor = "pointer";
        popup
          .setLngLat(event.lngLat)
          .setHTML(
            `<div style="font-size:12px;line-height:1.5">
              <div style="font-weight:700;color:#ef4444">🏢 ${cp.name || "Self-Storage Facility"}</div>
              ${cp.address ? `<div>${cp.address}</div>` : ""}
              <div style="color:#64748b">${sqftLabel}</div>
              <div style="color:#94a3b8;font-size:10px">${cp.data_source === "kmz" ? "KMZ import" : "Google Places"}</div>
            </div>`
          )
          .addTo(map);
        return;
      }

      const feature = queryParcelFeatures(event.point)[0];

      if (!feature) {
        popup.remove();
        map.getCanvas().style.cursor = "";
        return;
      }

      const props = feature.properties ?? {};
      const zoneClass = String(props.zone_class ?? "unknown");
      const storagePermission = String(
        props.storage_permission ?? "unclassified"
      );

      const storageLabel =
        storagePermission === "permitted"
          ? "Storage permitted"
          : storagePermission === "conditional"
            ? "Storage conditional"
            : storagePermission === "unclear"
              ? "Storage unclear"
              : storagePermission === "prohibited"
                ? "Storage prohibited"
                : "Storage unclassified";

      map.getCanvas().style.cursor = "pointer";

      popup
        .setLngLat(event.lngLat)
        .setHTML(
          `<div style="font-size:12px;line-height:1.5">
            <div style="font-family:monospace;font-weight:700">${props.apn ?? "—"}</div>
            <div>${props.address ?? "No address"}</div>
            <div>${props.zoning_code ?? "—"} · ${
              props.acres != null ? Number(props.acres).toFixed(2) + " ac" : "—"
            }</div>
            <div style="color:${
              ZONE_CLASS_COLORS[zoneClass as keyof typeof ZONE_CLASS_COLORS] ??
              UNCLASSIFIED_PARCEL_COLOR
            };font-weight:500">${zoneClass}</div>
            <div>${storageLabel}</div>
            ${
              props.has_structure === false
                ? '<div style="color:#059669;font-weight:500">Vacant</div>'
                : ""
            }
            ${
              props.in_flood_zone === true
                ? '<div style="color:#dc2626;font-weight:500">Flood zone</div>'
                : ""
            }
            ${
              props.in_wetland === true
                ? '<div style="color:#0891b2;font-weight:500">Wetland</div>'
                : ""
            }
          </div>`
        )
        .addTo(map);
    };

    const handleMouseLeave = () => {
      popup.remove();
      map.getCanvas().style.cursor = "";
    };

    map.on("click", handleClick);
    map.on("mousemove", handleMouseMove);
    map.on("mouseout", handleMouseLeave);

    return () => {
      map.off("click", handleClick);
      map.off("mousemove", handleMouseMove);
      map.off("mouseout", handleMouseLeave);
    };
  }, [onParcelClick]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      <LayerControl visibility={visibility} onChange={onVisibilityChange} />

      {isLoading && (
        <div className="absolute bottom-3 left-3 rounded-md bg-white/90 px-3 py-1.5 text-xs text-slate-500 shadow">
          Updating parcels…
        </div>
      )}

      {!isLoading && parcels.length === 0 && (
        <div className="absolute bottom-3 left-3 rounded-md bg-white/90 px-3 py-1.5 text-xs text-slate-500 shadow">
          No parcels match the current filters.
        </div>
      )}
    </div>
  );
}