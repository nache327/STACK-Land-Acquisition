"use client";

import { useState, useCallback } from "react";
import {
  computeComposite,
  computeLayer2,
  readCache,
  writeCache,
  type Layer1Result,
  type Layer3Result,
  type VerificationState,
} from "@/lib/verification";

function extractLatLng(centroid: Record<string, unknown> | null | undefined): [number, number] | null {
  if (!centroid) return null;
  const coords = centroid.coordinates as [number, number] | undefined;
  if (!coords || coords.length < 2) return null;
  return [coords[1], coords[0]]; // GeoJSON is [lng, lat] → return [lat, lng]
}

interface UseVerificationOptions {
  apn: string;
  zoneCode: string | null;
  jurisdictionId: string;
  centroid?: Record<string, unknown> | null;
}

export function useVerification({
  apn,
  zoneCode,
  jurisdictionId,
  centroid,
}: UseVerificationOptions) {
  const [state, setState] = useState<VerificationState | null>(() =>
    zoneCode ? readCache(apn, zoneCode) : null
  );
  const [layer1Loading, setLayer1Loading] = useState(false);
  const [layer3Loading, setLayer3Loading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildState = useCallback(
    (
      layer1: Layer1Result | null,
      layer3: Layer3Result,
      currentZoneCode: string
    ): VerificationState => {
      const layer2 = computeLayer2(currentZoneCode, layer1?.zoneCode ?? null);
      const { compositeScore, overallStatus, conflictFlags } = computeComposite(
        layer1,
        layer2,
        layer3
      );
      return {
        layer1,
        layer2,
        layer3,
        compositeScore,
        overallStatus,
        conflictFlags,
        lastUpdated: Date.now(),
      };
    },
    []
  );

  // Run Layer 1 (Zoneomics) — called when drawer opens
  const runLayer1 = useCallback(async () => {
    if (!zoneCode) return;
    if (state?.layer1?.status === "complete") return; // already have it

    const latLng = extractLatLng(centroid);
    if (!latLng) return; // no centroid — can't call Zoneomics

    setLayer1Loading(true);
    setError(null);

    try {
      const res = await fetch("/api/verify-layer1", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat: latLng[0], lng: latLng[1] }),
      });

      if (!res.ok) throw new Error(`Layer 1 failed: ${res.status}`);
      const layer1: Layer1Result = await res.json();

      const layer3: Layer3Result = state?.layer3 ?? {
        status: "not-run",
        ordinanceUrl: null,
        selfStorageStatus: null,
        keepStatus: null,
        evidence: null,
        aiConfidence: null,
        notes: null,
        classificationSource: null,
        score: 0,
      };

      const next = buildState(layer1, layer3, zoneCode);
      setState(next);
      writeCache(apn, zoneCode, next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Layer 1 failed");
    } finally {
      setLayer1Loading(false);
    }
  }, [apn, zoneCode, centroid, state, buildState]);

  // Run Layer 3 (ordinance AI) — only on explicit user request
  const runLayer3 = useCallback(async () => {
    if (!zoneCode || !jurisdictionId) return;

    setLayer3Loading(true);
    setError(null);

    try {
      const res = await fetch("/api/verify-layer3", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jurisdictionId, zoneCode }),
      });

      if (!res.ok) throw new Error(`Layer 3 failed: ${res.status}`);
      const layer3: Layer3Result = await res.json();

      const next = buildState(state?.layer1 ?? null, layer3, zoneCode);
      setState(next);
      writeCache(apn, zoneCode, next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Layer 3 failed");
    } finally {
      setLayer3Loading(false);
    }
  }, [apn, zoneCode, jurisdictionId, state, buildState]);

  const reset = useCallback(() => {
    if (zoneCode) {
      const { clearCache } = require("@/lib/verification");
      clearCache(apn, zoneCode);
    }
    setState(null);
    setError(null);
  }, [apn, zoneCode]);

  return {
    state,
    layer1Loading,
    layer3Loading,
    error,
    runLayer1,
    runLayer3,
    reset,
  };
}
