"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useJurisdictionBounds } from "@/hooks/useJurisdictionBounds";
import { LayerControl, type LayerVisibility } from "@/components/LayerControl";
import { LAYER_REGISTRY, SATURATION_COLORS, ZONE_CLASS_COLORS, type ColorMode } from "@/lib/layers";
import { api } from "@/lib/api";
import type { CandidateParcelRow, SaturationBatchResult } from "@/lib/schemas";
import type { IsochronePolygons, TractData } from "@/lib/isochrone";
import { scoreToColor, scoreToGrade, computeKeepScore } from "@/lib/keep-layer";

const SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
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

export type DriveTimeMode = "off" | "on" | "pinned";

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
  flyTrigger?: number;
  // Drive-time isochrone props
  driveTimeMode?: DriveTimeMode;
  isochronePolygons?: IsochronePolygons | null;
  isochroneWealth?: TractData[] | null;
  pinnedIsochronePolygons?: IsochronePolygons | null;
  pinnedIsochroneWealth?: TractData[] | null;
  onDriveTimeModeChange?: (mode: DriveTimeMode) => void;
  keepActive?: boolean;
  keepMinScore?: number;
  onKeepChange?: (active: boolean, minScore: number) => void;
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
const KEEP_LAYER = "keep-layer";
const RING_SOURCE = "saturation-rings";
const RING_LAYER = "saturation-rings-line";
const RING_RADII_MILES = [3];
const HEAT_SOURCE = "saturation-heat";
const HEAT_LAYER = "saturation-heat-layer";

// ── Isochrone constants ───────────────────────────────────────────────────────
const ISO_RING_SOURCE   = "isochrone-rings";
const ISO_LABEL_SOURCE  = "isochrone-labels";
const ISO_WEALTH_SOURCE = "isochrone-wealth";
const ISO_PIN_RING_SOURCE   = "isochrone-rings-pinned";
const ISO_PIN_LABEL_SOURCE  = "isochrone-labels-pinned";

const RING_SPECS = [
  { key: "min10" as const, label: "10 min", fill: "#9B6B9B", fillOpacity: 0.28, lineOpacity: 0.85, lineWidth: 2.5 },
  { key: "min5"  as const, label: "5 min",  fill: "#7B68EE", fillOpacity: 0.35, lineOpacity: 0.90, lineWidth: 2.5 },
  { key: "min2"  as const, label: "2 min",  fill: "#4A90D9", fillOpacity: 0.45, lineOpacity: 0.95, lineWidth: 3.0 },
] as const;

const PINNED_COLOR = "#E8934A";

// Get the northernmost [lng, lat] from a GeoJSON feature
function northernmostPoint(
  feature: IsochronePolygons[keyof IsochronePolygons]
): [number, number] {
  const coords: number[][] = [];
  const collect = (c: unknown): void => {
    if (!Array.isArray(c)) return;
    if (typeof c[0] === "number") { coords.push(c as number[]); return; }
    (c as unknown[]).forEach(collect);
  };
  collect(feature.geometry.coordinates);
  return coords.reduce((best, c) => (c[1] > best[1] ? c : best)) as [number, number];
}

function isoRingFC(polygons: IsochronePolygons): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: RING_SPECS.map((s) => ({
      ...(polygons[s.key] as GeoJSON.Feature),
      properties: { ring: s.key },
    })),
  };
}

function isoLabelFC(polygons: IsochronePolygons): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: RING_SPECS.map((s) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: northernmostPoint(polygons[s.key]) },
      properties: { label: s.label, ring: s.key },
    })),
  };
}

function isoWealthFC(tracts: TractData[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: tracts
      .filter((t) => t.clipped_geometry !== null)
      .map((t) => ({
        ...(t.clipped_geometry as GeoJSON.Feature),
        properties: { median_hhi: t.median_hhi ?? -1, household_count: t.household_count ?? 0 },
      })),
  };
}

function isoUpsertRingLayers(
  map: maplibregl.Map,
  ringSrc: string,
  labelSrc: string,
  polygons: IsochronePolygons | null | undefined,
  color?: string
): void {
  if (!polygons) {
    for (const s of RING_SPECS) {
      const fillId  = `iso-fill-${s.key}-${ringSrc}`;
      const lineId  = `iso-line-${s.key}-${ringSrc}`;
      const labelId = `iso-label-${s.key}-${labelSrc}`;
      if (map.getLayer(fillId))  map.removeLayer(fillId);
      if (map.getLayer(lineId))  map.removeLayer(lineId);
      if (map.getLayer(labelId)) map.removeLayer(labelId);
    }
    if (map.getSource(ringSrc))  map.removeSource(ringSrc);
    if (map.getSource(labelSrc)) map.removeSource(labelSrc);
    return;
  }

  const rFC = isoRingFC(polygons);
  const lFC = isoLabelFC(polygons);

  const existingRing = map.getSource(ringSrc) as maplibregl.GeoJSONSource | undefined;
  existingRing ? existingRing.setData(rFC) : map.addSource(ringSrc, { type: "geojson", data: rFC });

  const existingLabel = map.getSource(labelSrc) as maplibregl.GeoJSONSource | undefined;
  existingLabel ? existingLabel.setData(lFC) : map.addSource(labelSrc, { type: "geojson", data: lFC });

  for (const s of RING_SPECS) {
    const fillId  = `iso-fill-${s.key}-${ringSrc}`;
    const lineId  = `iso-line-${s.key}-${ringSrc}`;
    const labelId = `iso-label-${s.key}-${labelSrc}`;
    const c       = color ?? s.fill;
    const f: maplibregl.FilterSpecification = ["==", ["get", "ring"], s.key];

    if (!map.getLayer(fillId)) {
      map.addLayer({ id: fillId, type: "fill", source: ringSrc, filter: f,
        paint: { "fill-color": c, "fill-opacity": s.fillOpacity } });
    }
    if (!map.getLayer(lineId)) {
      map.addLayer({ id: lineId, type: "line", source: ringSrc, filter: f,
        paint: { "line-color": c, "line-width": s.lineWidth, "line-opacity": s.lineOpacity } });
    }
    if (!map.getLayer(labelId)) {
      map.addLayer({ id: labelId, type: "symbol", source: labelSrc, filter: f,
        layout: { "text-field": ["get", "label"], "text-size": 11,
                  "text-offset": [0, -0.8], "text-anchor": "bottom" },
        paint: { "text-color": c, "text-halo-color": "rgba(255,255,255,0.8)", "text-halo-width": 1.5 } });
    }
  }
}

function isoUpsertWealth(map: maplibregl.Map, tracts: TractData[]): void {
  const fc = isoWealthFC(tracts);
  const existing = map.getSource(ISO_WEALTH_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(fc);
    return;
  }
  if (!fc.features.length) return;
  map.addSource(ISO_WEALTH_SOURCE, { type: "geojson", data: fc });
  map.addLayer({
    id: "iso-wealth-fill",
    type: "fill",
    source: ISO_WEALTH_SOURCE,
    paint: {
      "fill-color": ["step", ["get", "median_hhi"],
        "rgba(0,0,0,0)", 100_000, "#E8D5A3", 150_000, "#C9A84C", 200_000, "#C9A84C"],
      "fill-opacity": ["step", ["get", "median_hhi"],
        0, 100_000, 0.30, 150_000, 0.35, 200_000, 0.55],
    },
  });
}

// Haversine circle — no external deps, returns a closed LineString
function geoCircle(center: [number, number], radiusMiles: number, steps = 96): GeoJSON.Feature {
  const [lng0, lat0] = center;
  const d = radiusMiles / 3958.8; // angular distance (Earth radius in miles)
  const latR = (lat0 * Math.PI) / 180;
  const lngR = (lng0 * Math.PI) / 180;
  const coords: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const bearing = (2 * Math.PI * i) / steps;
    const lat2 = Math.asin(
      Math.sin(latR) * Math.cos(d) + Math.cos(latR) * Math.sin(d) * Math.cos(bearing)
    );
    const lng2 =
      lngR +
      Math.atan2(
        Math.sin(bearing) * Math.sin(d) * Math.cos(latR),
        Math.cos(d) - Math.sin(latR) * Math.sin(lat2)
      );
    coords.push([(lng2 * 180) / Math.PI, (lat2 * 180) / Math.PI]);
  }
  return {
    type: "Feature",
    geometry: { type: "LineString", coordinates: coords },
    properties: { radius_miles: radiusMiles },
  };
}

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
  flyTrigger,
  driveTimeMode = "off",
  isochronePolygons,
  isochroneWealth,
  pinnedIsochronePolygons,
  onDriveTimeModeChange,
  keepActive = false,
  keepMinScore = 55,
  onKeepChange,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const tooltipRef = useRef<maplibregl.Popup | null>(null);
  const hasFitRef = useRef<string | null>(null);

  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number;
    type: "competitor" | "parcel";
    competitorId?: number;
    lngLat?: { lng: number; lat: number };
    parcelId?: number;
  } | null>(null);

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
              garage_permission: parcel.garage_permission ?? "unclassified",
              storage_allowed: parcel.storage_allowed,
              storage_conditional: parcel.storage_conditional,
              in_flood_zone: parcel.in_flood_zone,
              in_wetland: parcel.in_wetland,
              has_structure: parcel.has_structure,
              is_viable: parcel.is_viable,
              saturation_color: satColor,
              sqft_per_person: sat?.sqft_per_person ?? null,
            },
            geometry: parcel.geom as unknown as GeoJSON.Geometry,
          };
        }),
    };
  }, [parcels, saturationData]);

  const keepEffectiveScores = useMemo(
    () => ({
      permitted:   computeKeepScore("permitted",   isochroneWealth),
      conditional: computeKeepScore("conditional", isochroneWealth),
      unclear:     computeKeepScore("unclear",      isochroneWealth),
    }),
    [isochroneWealth],
  );

  // Point centroids used for the saturation heatmap overlay
  const heatCollection = useMemo<GeoJSON.FeatureCollection>(() => {
    if (!saturationData?.size) return { type: "FeatureCollection", features: [] };
    const features: GeoJSON.Feature[] = [];
    for (const parcel of parcels) {
      const sat = saturationData.get(parcel.parcel_id);
      if (!sat || sat.sqft_per_person == null || !parcel.geom) continue;
      const centroid = bboxCenter(parcel.geom as unknown as GeoJSON.Geometry);
      if (!centroid) continue;
      features.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: centroid },
        properties: { spp: Math.min(sat.sqft_per_person, 20) },
      });
    }
    return { type: "FeatureCollection", features };
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

  // Fly to parcel + guarantee ring is drawn when "◎ 3-mi Ring" button pressed
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !flyTrigger) return;
    const centroid = getBestCentroid();
    if (!centroid) return;
    map.flyTo({ center: centroid, zoom: Math.max(map.getZoom(), 15), duration: 800 });
    // Draw ring immediately (don't wait for moveend to recompute)
    if (map.isStyleLoaded()) drawRingOnMap(map, centroid);
    else map.once("load", () => drawRingOnMap(map, centroid));
  }, [flyTrigger]); // eslint-disable-line react-hooks/exhaustive-deps

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
                "permitted",   0.75,
                "conditional", 0.65,
                "unclear",     0.08,
                "prohibited",  0.05,
                0.05,
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

      // Ensure competitor dots are always rendered above the parcel fill
      for (const layerId of ["competitors-circle", "competitors-label"]) {
        try {
          if (map.getLayer(layerId)) map.moveLayer(layerId);
        } catch { /* ignore */ }
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
      // Combined zoning × saturation signal — each parcel gets a single "investment quality" color
      map.setPaintProperty(PARCEL_FILL, "fill-color", [
        "case",
        // Non-actionable → ghost grey
        ["match", ["get", "storage_permission"], ["prohibited", "unclassified"], true, false],
        "#94a3b8",
        // Oversupplied → red NO signal for all actionable
        ["==", ["get", "saturation_color"], "red"],
        "#ef4444",
        // Underserved — tier by zoning quality
        ["all", ["==", ["get", "saturation_color"], "green"], ["==", ["get", "storage_permission"], "permitted"]],
        "#fbbf24",   // Gold: best site in the city (permitted + underserved)
        ["all", ["==", ["get", "saturation_color"], "green"], ["==", ["get", "storage_permission"], "conditional"]],
        "#06b6d4",   // Teal: great market, needs CUP
        ["all", ["==", ["get", "saturation_color"], "green"], ["==", ["get", "storage_permission"], "unclear"]],
        "#818cf8",   // Indigo: great market, zoning unclear
        // Borderline — tier by zoning quality
        ["all", ["==", ["get", "saturation_color"], "yellow"], ["==", ["get", "storage_permission"], "permitted"]],
        "#06b6d4",   // Teal: permitted + borderline (still worth a look)
        ["all", ["==", ["get", "saturation_color"], "yellow"], ["==", ["get", "storage_permission"], "conditional"]],
        "#60a5fa",   // Blue: conditional + borderline
        // No saturation data yet → dim permission color as placeholder
        ["==", ["get", "storage_permission"], "permitted"],   "#10b981",
        ["==", ["get", "storage_permission"], "conditional"], "#f59e0b",
        "#94a3b8",
      ]);
      map.setPaintProperty(PARCEL_FILL, "fill-opacity", [
        "case",
        ["match", ["get", "storage_permission"], ["prohibited", "unclassified"], true, false],
        0.05,
        ["==", ["get", "saturation_color"], "red"],
        0.55,
        ["all", ["==", ["get", "saturation_color"], "green"], ["==", ["get", "storage_permission"], "permitted"]],
        0.95,   // Gold: brightest — your eyes go here first
        ["all", ["==", ["get", "saturation_color"], "green"], ["==", ["get", "storage_permission"], "conditional"]],
        0.85,
        ["all", ["==", ["get", "saturation_color"], "green"], ["==", ["get", "storage_permission"], "unclear"]],
        0.65,
        ["all", ["==", ["get", "saturation_color"], "yellow"], ["==", ["get", "storage_permission"], "permitted"]],
        0.75,
        ["all", ["==", ["get", "saturation_color"], "yellow"], ["==", ["get", "storage_permission"], "conditional"]],
        0.6,
        // no saturation data yet → show normal permission opacity so map looks correct while loading
        ["==", ["get", "storage_permission"], "permitted"],   0.75,
        ["==", ["get", "storage_permission"], "conditional"], 0.65,
        ["==", ["get", "storage_permission"], "unclear"],     0.08,
        0.05,
      ]);
    } else {
      // Default: only permitted + conditional clearly visible; everything else fades away
      map.setPaintProperty(PARCEL_FILL, "fill-color", [
        "match",
        ["get", "storage_permission"],
        "permitted",   "#10b981",
        "conditional", "#f59e0b",
        "unclear",     "#a78bfa",
        "prohibited",  "#6b7280",
        UNCLASSIFIED_PARCEL_COLOR,
      ]);
      map.setPaintProperty(PARCEL_FILL, "fill-opacity", [
        "match",
        ["get", "storage_permission"],
        "permitted",   0.75,
        "conditional", 0.65,
        "unclear",     0.08,
        "prohibited",  0.05,
        0.05,
      ]);
    }
  }, [colorMode]);

  // Heatmap source kept for compatibility but layer is always hidden —
  // the parcel fill-color/opacity already tells the complete saturation story.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const upsertHeat = () => {
      const existing = map.getSource(HEAT_SOURCE) as maplibregl.GeoJSONSource | undefined;
      if (existing) {
        existing.setData(heatCollection);
      } else {
        map.addSource(HEAT_SOURCE, { type: "geojson", data: heatCollection });
        map.addLayer({
          id: HEAT_LAYER,
          type: "heatmap",
          source: HEAT_SOURCE,
          paint: { "heatmap-opacity": 0 },
          layout: { visibility: "none" },
        });
      }
    };

    if (map.isStyleLoaded()) upsertHeat();
    else map.once("load", upsertHeat);
  }, [heatCollection]);

  // ── The Keep layer ────────────────────────────────────────────────────────
  // Full-coverage overlay: colors ALL parcels by garage_permission grade.
  // Prohibited/unclassified → slate gray so the full map remains readable.
  // Uses a separate layer at full opacity so it never blends with the storage fill.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const NEUTRAL = "#cbd5e1"; // slate-300 for prohibited / unclassified

    if (!keepActive) {
      if (map.getLayer(KEEP_LAYER)) {
        map.setPaintProperty(KEEP_LAYER, "fill-opacity", 0);
      }
      return;
    }

    const permittedScore   = keepEffectiveScores.permitted   ?? 90;
    const conditionalScore = keepEffectiveScores.conditional ?? 72;
    const unclearScore     = keepEffectiveScores.unclear      ?? 57;

    const fillColor: maplibregl.ExpressionSpecification = [
      "case",
      // Gate 1: only score parcels that passed the Layer-1 zoning screen
      ["in", ["get", "storage_permission"], ["literal", ["permitted", "conditional", "unclear"]]],
      [
        "match", ["get", "garage_permission"],
        "permitted",   keepMinScore <= permittedScore   ? scoreToColor(permittedScore)   : NEUTRAL,
        "conditional", keepMinScore <= conditionalScore ? scoreToColor(conditionalScore) : NEUTRAL,
        "unclear",     keepMinScore <= unclearScore     ? scoreToColor(unclearScore)     : NEUTRAL,
        NEUTRAL,
      ],
      NEUTRAL, // prohibited / unclassified stay gray
    ];

    // Non-qualifying parcels (prohibited / unclassified storage) are fully
    // transparent so Layer 1 zoning colors remain visible underneath.
    const fillOpacity: maplibregl.ExpressionSpecification = [
      "case",
      ["in", ["get", "storage_permission"], ["literal", ["permitted", "conditional", "unclear"]]],
      0.88,
      0,
    ];

    if (!map.getLayer(KEEP_LAYER)) {
      map.addLayer(
        {
          id: KEEP_LAYER,
          type: "fill",
          source: PARCEL_SOURCE,
          paint: {
            "fill-color": fillColor,
            "fill-opacity": fillOpacity,
          },
        },
        // Insert above parcel fill but below the outline + selection layers
        PARCEL_LINE,
      );
    } else {
      map.setPaintProperty(KEEP_LAYER, "fill-color", fillColor);
      map.setPaintProperty(KEEP_LAYER, "fill-opacity", fillOpacity);
    }
  }, [keepActive, keepMinScore, parcelCollection, keepEffectiveScores]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Ring helpers ──────────────────────────────────────────────────────────
  const drawRingOnMap = (map: maplibregl.Map, centroid: [number, number]) => {
    const ringCollection: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: RING_RADII_MILES.map((r) => geoCircle(centroid, r)),
    };
    const existing = map.getSource(RING_SOURCE) as maplibregl.GeoJSONSource | undefined;
    if (existing) {
      existing.setData(ringCollection);
      return;
    }
    map.addSource(RING_SOURCE, { type: "geojson", data: ringCollection });
    map.addLayer({
      id: RING_LAYER + "-glow",
      type: "line",
      source: RING_SOURCE,
      paint: { "line-color": "#ef4444", "line-width": 16, "line-opacity": 0.3, "line-blur": 8 },
    });
    map.addLayer({
      id: RING_LAYER,
      type: "line",
      source: RING_SOURCE,
      paint: { "line-color": "#ef4444", "line-width": 6, "line-opacity": 1 },
    });
  };

  const removeRingFromMap = (map: maplibregl.Map) => {
    if (map.getLayer(RING_LAYER)) map.removeLayer(RING_LAYER);
    if (map.getLayer(RING_LAYER + "-glow")) map.removeLayer(RING_LAYER + "-glow");
    if (map.getSource(RING_SOURCE)) map.removeSource(RING_SOURCE);
  };

  // Best-effort centroid: check parcelCollection first, fall back to prop
  const getBestCentroid = (): [number, number] | null => {
    if (selectedParcelId != null) {
      const feature = parcelCollection.features.find(
        (f) => Number(f.properties?.parcel_id) === selectedParcelId
      );
      if (feature?.geometry) {
        const c = bboxCenter(feature.geometry);
        if (c) return c;
      }
    }
    return selectedParcelCentroid ?? null;
  };

  // Draw ring whenever selected parcel changes (auto-ring on selection)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const centroid = getBestCentroid();
    const run = () => {
      if (!centroid) { removeRingFromMap(map); return; }
      drawRingOnMap(map, centroid);
    };
    if (map.isStyleLoaded()) run(); else map.once("load", run);
  }, [selectedParcelId, parcelCollection, selectedParcelCentroid]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Isochrone ring rendering ──────────────────────────────────────────────

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const run = (m: maplibregl.Map) => {
      isoUpsertRingLayers(m, ISO_RING_SOURCE, ISO_LABEL_SOURCE,
        driveTimeMode !== "off" ? isochronePolygons : null);

      isoUpsertRingLayers(m, ISO_PIN_RING_SOURCE, ISO_PIN_LABEL_SOURCE,
        driveTimeMode === "pinned" ? pinnedIsochronePolygons : null,
        PINNED_COLOR);

      isoUpsertWealth(m, isochroneWealth ?? []);
    };

    if (map.isStyleLoaded()) run(map); else map.once("load", () => run(map!));
  }, [driveTimeMode, isochronePolygons, isochroneWealth, pinnedIsochronePolygons]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─────────────────────────────────────────────────────────────────────────────

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

          // PARCEL_FILL opacity is managed by the colorMode effect (match expression)
          if (type === "fill" && mapLayerId !== PARCEL_FILL) {
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

      // Saturation section — only shown in saturation mode for actionable parcels
      const isActionable = ["permitted", "conditional", "unclear"].includes(storagePermission);
      const satColor = String(props.saturation_color ?? "nodata");
      const spp = props.sqft_per_person != null ? Number(props.sqft_per_person) : null;
      const satTierLabel =
        satColor === "green"  && storagePermission === "permitted"   ? "★ Best Site — Permitted + Underserved" :
        satColor === "green"  && storagePermission === "conditional" ? "Strong — Conditional + Underserved"   :
        satColor === "green"  ? "Underserved market"                                                         :
        satColor === "yellow" && storagePermission === "permitted"   ? "Strong — Permitted + Borderline"      :
        satColor === "yellow" ? "Borderline market"                                                          :
        satColor === "red"    ? "Oversupplied — Don't Build"                                                 : null;
      const satTierColor =
        satColor === "green"  && storagePermission === "permitted"   ? "#fbbf24" :
        satColor === "green"  ? "#06b6d4" :
        satColor === "yellow" ? "#60a5fa" :
        satColor === "red"    ? "#ef4444" : "#94a3b8";

      const saturationHTML =
        colorMode === "saturation" && isActionable
          ? `<div style="margin-top:5px;padding-top:5px;border-top:1px solid #334155">
              ${satTierLabel ? `<div style="font-weight:700;color:${satTierColor}">${satTierLabel}</div>` : ""}
              <div style="color:#94a3b8;font-size:11px">${
                spp != null ? `${spp.toFixed(1)} sq ft / person` : "No saturation data"
              }</div>
            </div>`
          : "";

      const garagePermission = String(props.garage_permission ?? "unclassified");
      const keepScore = keepActive ? computeKeepScore(garagePermission, isochroneWealth) : null;
      const keepHTML = keepScore !== null
        ? `<div style="margin-top:5px;padding-top:5px;border-top:1px solid #334155">
            <span style="color:${scoreToColor(keepScore)};font-weight:700">Keep ${keepScore} (${scoreToGrade(keepScore)})</span>
            ${isochroneWealth?.length ? `<div style="color:#94a3b8;font-size:10px">Wealth-adjusted</div>` : ""}
          </div>`
        : "";

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
            ${saturationHTML}
            ${keepHTML}
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
  }, [onParcelClick, colorMode, keepActive, isochroneWealth]); // eslint-disable-line react-hooks/exhaustive-deps

  // Right-click context menu
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const handleContextMenu = (e: maplibregl.MapMouseEvent) => {
      // Check if clicking on a competitor circle
      const compFeats = map.queryRenderedFeatures(e.point, { layers: ["competitors-circle"] });
      if (compFeats.length > 0) {
        const f = compFeats[0];
        setContextMenu({
          x: e.originalEvent.clientX,
          y: e.originalEvent.clientY,
          type: "competitor",
          competitorId: f.properties?.id as number,
        });
        return;
      }

      // Check if clicking on a parcel
      const parcelFeats = map.queryRenderedFeatures(e.point, { layers: [PARCEL_FILL] });
      if (parcelFeats.length > 0) {
        const f = parcelFeats[0];
        setContextMenu({
          x: e.originalEvent.clientX,
          y: e.originalEvent.clientY,
          type: "parcel",
          lngLat: { lng: e.lngLat.lng, lat: e.lngLat.lat },
          parcelId: f.properties?.parcel_id as number,
        });
        return;
      }

      setContextMenu(null);
    };

    const handleClickClose = () => setContextMenu(null);
    const handleDragClose = () => setContextMenu(null);

    map.on("contextmenu", handleContextMenu);
    map.on("click", handleClickClose);
    map.on("dragstart", handleDragClose);

    return () => {
      map.off("contextmenu", handleContextMenu);
      map.off("click", handleClickClose);
      map.off("dragstart", handleDragClose);
    };
  }, []);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />

      <LayerControl
        visibility={visibility}
        onChange={onVisibilityChange}
        driveTimeMode={driveTimeMode}
        onDriveTimeModeChange={onDriveTimeModeChange}
        keepActive={keepActive}
        keepMinScore={keepMinScore}
        onKeepChange={onKeepChange}
        keepEffectiveScores={isochroneWealth?.length ? keepEffectiveScores : undefined}
      />

      {colorMode === "saturation" && <SaturationLegend />}

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

      {contextMenu && (
        <div
          style={{
            position: "fixed",
            left: contextMenu.x,
            top: contextMenu.y,
            zIndex: 1000,
            background: "rgba(15,23,42,0.95)",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: "4px 0",
            minWidth: 180,
            boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
          }}
          onMouseLeave={() => setContextMenu(null)}
        >
          {contextMenu.type === "competitor" && (
            <button
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "8px 14px", background: "none", border: "none",
                color: "#f87171", fontSize: 13, cursor: "pointer",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "#1e293b")}
              onMouseLeave={e => (e.currentTarget.style.background = "none")}
              onClick={async () => {
                if (!contextMenu.competitorId) return;
                if (!window.confirm("Remove this competitor from the map?")) {
                  setContextMenu(null);
                  return;
                }
                try {
                  await api.deleteCompetitor(contextMenu.competitorId);
                  // Refresh the competitors source data
                  const map = mapRef.current;
                  if (map) {
                    const src = map.getSource("competitors") as maplibregl.GeoJSONSource | undefined;
                    if (src) {
                      const url = api.competitorsUrl(jurisdictionId);
                      src.setData(url);
                    }
                  }
                } catch {
                  alert("Failed to delete competitor.");
                }
                setContextMenu(null);
              }}
            >
              Remove competitor
            </button>
          )}
          {contextMenu.type === "parcel" && (
            <button
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "8px 14px", background: "none", border: "none",
                color: "#94a3b8", fontSize: 13, cursor: "pointer",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "#1e293b")}
              onMouseLeave={e => (e.currentTarget.style.background = "none")}
              onClick={async () => {
                if (!contextMenu.lngLat) return;
                const name = prompt("Competitor name (optional):");
                const sqftStr = prompt("Square footage (leave blank for default 60,000):");
                const sqFt = sqftStr ? parseInt(sqftStr) : undefined;
                try {
                  await api.createCompetitor({
                    lng: contextMenu.lngLat.lng,
                    lat: contextMenu.lngLat.lat,
                    name: name || undefined,
                    sq_ft: sqFt,
                    jurisdiction_id: jurisdictionId || undefined,
                  });
                  // Refresh the competitors source data
                  const map = mapRef.current;
                  if (map) {
                    const src = map.getSource("competitors") as maplibregl.GeoJSONSource | undefined;
                    if (src) {
                      const url = api.competitorsUrl(jurisdictionId);
                      src.setData(url);
                    }
                  }
                } catch {
                  alert("Failed to add competitor.");
                }
                setContextMenu(null);
              }}
            >
              Mark as competitor
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function SaturationLegend() {
  const rows = [
    { color: "#fbbf24", label: "Best Site",          sub: "Permitted + Underserved",           faded: false },
    { color: "#06b6d4", label: "Strong",              sub: "Conditional + Underserved or Permitted + Borderline", faded: false },
    { color: "#60a5fa", label: "Investigate",         sub: "Conditional + Borderline",         faded: false },
    { color: "#ef4444", label: "Oversupplied — NO",  sub: "Market saturated, don't build",    faded: false },
    { color: "#94a3b8", label: "Not Actionable",      sub: "Prohibited / Unclassified",        faded: true },
  ];

  return (
    <div style={{
      position: "absolute",
      bottom: "44px",
      right: "10px",
      background: "rgba(15,23,42,0.90)",
      backdropFilter: "blur(4px)",
      borderRadius: "8px",
      padding: "10px 14px",
      minWidth: "210px",
      boxShadow: "0 2px 12px rgba(0,0,0,0.5)",
      zIndex: 10,
      pointerEvents: "none",
    }}>
      <div style={{ fontSize: "11px", fontWeight: 700, color: "#cbd5e1", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "8px" }}>
        Market Saturation
      </div>
      {rows.map((row) => (
        <div key={row.label} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "5px", opacity: row.faded ? 0.45 : 1 }}>
          <span style={{ width: "10px", height: "10px", borderRadius: "50%", backgroundColor: row.color, flexShrink: 0, display: "block" }} />
          <div style={{ lineHeight: 1.3 }}>
            <div style={{ fontSize: "12px", color: "#f1f5f9", fontWeight: 500 }}>{row.label}</div>
            <div style={{ fontSize: "10px", color: "#94a3b8" }}>{row.sub}</div>
          </div>
        </div>
      ))}
      <div style={{ marginTop: "8px", paddingTop: "6px", borderTop: "1px solid rgba(148,163,184,0.2)", fontSize: "10px", color: "#64748b", lineHeight: 1.4 }}>
        Actionable parcels only · 3-mile ring
      </div>
    </div>
  );
}