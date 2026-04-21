"use client";

/**
 * Side panel that slides in when a parcel is clicked.
 * Includes Three-Layer Zoning Verification Engine.
 */

import { useEffect } from "react";
import type { ParcelDetail } from "@/lib/schemas";
import { useVerification } from "@/hooks/useVerification";
import { VerificationPanel } from "./VerificationPanel";

interface ParcelDrawerProps {
  parcel: ParcelDetail | null;
  jurisdictionId: string;
  onClose: () => void;
  isInShortlist?: boolean;
  onToggleShortlist?: () => void;
}

export function ParcelDrawer({
  parcel,
  jurisdictionId,
  onClose,
  isInShortlist = false,
  onToggleShortlist,
}: ParcelDrawerProps) {
  const { state, layer1Loading, layer3Loading, error, runLayer1, runLayer3, reset } =
    useVerification({
      apn: parcel?.apn ?? "",
      zoneCode: parcel?.zoning_code ?? null,
      jurisdictionId,
      centroid: parcel?.centroid ?? null,
    });

  // Auto-run Layer 1 when drawer opens with a new parcel
  useEffect(() => {
    if (parcel?.centroid && parcel.zoning_code) {
      runLayer1();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parcel?.apn]);

  if (!parcel) return null;

  return (
    <aside className="fixed inset-y-0 right-0 z-50 w-[440px] overflow-y-auto border-l border-slate-200 bg-white shadow-xl">
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 className="font-semibold text-slate-900">Parcel Detail</h2>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-400">ESC to close · ↑↓ navigate</span>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close panel"
          >
            ✕
          </button>
        </div>
      </header>

      <div className="space-y-4 p-4">
        {/* Parcel attributes */}
        <dl className="space-y-3 text-sm">
          <Row label="APN" value={parcel.apn} mono />
          <Row label="Address" value={parcel.address} />
          <Row label="Owner" value={parcel.owner_name} />
          <Row label="Zone" value={parcel.zoning_code} />
          <Row label="Acres" value={parcel.acres?.toFixed(3)} />
          <Row
            label="Flood Zone"
            value={parcel.in_flood_zone ? "Yes" : "No"}
            danger={parcel.in_flood_zone}
          />
          <Row
            label="Wetland"
            value={parcel.in_wetland ? "Yes" : "No"}
            danger={parcel.in_wetland}
          />
          <Row
            label="Slope"
            value={
              parcel.avg_slope_pct != null
                ? `${parcel.avg_slope_pct.toFixed(1)}%`
                : "Unknown"
            }
          />
          <Row
            label="Structure"
            value={
              parcel.has_structure === null
                ? "Unknown"
                : parcel.has_structure
                ? "Yes"
                : "No"
            }
          />
        </dl>

        {/* Three-Layer Verification */}
        <VerificationPanel
          state={state}
          layer1Loading={layer1Loading}
          layer3Loading={layer3Loading}
          error={error}
          onRunLayer3={runLayer3}
          onReset={reset}
        />

        {/* Actions */}
        <div className="space-y-2 pt-1">
          {onToggleShortlist && (
            <button
              onClick={onToggleShortlist}
              className={[
                "w-full rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                isInShortlist
                  ? "border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                  : "border-slate-200 text-slate-700 hover:bg-slate-50",
              ].join(" ")}
            >
              {isInShortlist ? "✓ In shortlist — click to remove" : "+ Add to shortlist"}
            </button>
          )}

          {parcel.county_link && (
            <a
              href={parcel.county_link}
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full rounded-lg border border-slate-200 px-4 py-2 text-center text-sm text-slate-700 hover:bg-slate-50"
            >
              View on County GIS ↗
            </a>
          )}

          <button
            onClick={() => {
              const csv = [
                parcel.apn,
                parcel.address ?? "",
                parcel.owner_name ?? "",
                parcel.acres ?? "",
                parcel.zoning_code ?? "",
              ].join(",");
              navigator.clipboard.writeText(csv);
            }}
            className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            Copy CSV Row
          </button>
        </div>
      </div>
    </aside>
  );
}

function Row({
  label,
  value,
  mono = false,
  danger = false,
}: {
  label: string;
  value: string | number | null | undefined;
  mono?: boolean;
  danger?: boolean;
}) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="shrink-0 text-slate-500">{label}</dt>
      <dd
        className={[
          "text-right",
          mono ? "font-mono text-xs" : "",
          danger ? "font-medium text-red-600" : "text-slate-900",
          value == null ? "text-slate-400" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {value ?? "—"}
      </dd>
    </div>
  );
}
