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

interface UseVerificationOptions {
  apn: string;
  zoneCode: string | null;
  jurisdictionId: string;
}

export function useVerification({
  apn,
  zoneCode,
  jurisdictionId,
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

  // Run Layer 1 (our DB) — called when drawer opens with a new parcel
  const runLayer1 = useCallback(async () => {
    if (!zoneCode || !jurisdictionId) return;
    if (state?.layer1?.status === "complete") return; // already have it

    setLayer1Loading(true);
    setError(null);

    try {
      const res = await fetch("/api/verify-layer1", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jurisdictionId, zoneCode }),
      });

      if (!res.ok) throw new Error(`Layer 1 failed: ${res.status}`);
      const layer1: Layer1Result = await res.json();

      const layer3: Layer3Result = state?.layer3 ?? {
        status: "not-run",
        ordinanceUrl: null,
        ordinanceSource: null,
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
  }, [apn, zoneCode, jurisdictionId, state, buildState]);

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
