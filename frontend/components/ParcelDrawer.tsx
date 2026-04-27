"use client";

import { useEffect } from "react";
import type { ParcelDetail } from "@/lib/schemas";
import { useVerification } from "@/hooks/useVerification";
import { useParcelSaturation } from "@/hooks/useParcelSaturation";
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
    });

  const { data: saturation, isLoading: satLoading } = useParcelSaturation(
    parcel?.id ?? null
  );

  // Auto-run Layer 1 when drawer opens with a new parcel
  useEffect(() => {
    if (parcel?.zoning_code) {
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

        {/* Market Saturation */}
        <SaturationPanel saturation={saturation ?? null} isLoading={satLoading} />

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

const SAT_COLORS: Record<string, string> = {
  green:  "#10b981",
  yellow: "#f59e0b",
  red:    "#ef4444",
  gray:   "#94a3b8",
};

const SAT_LABELS: Record<string, string> = {
  green:  "Underserved",
  yellow: "Borderline",
  red:    "Oversupplied",
  gray:   "No Data",
};

function SaturationPanel({
  saturation,
  isLoading,
}: {
  saturation: import("@/lib/schemas").SaturationResponse | null;
  isLoading: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-3 text-sm">
      <h3 className="mb-2 font-semibold text-slate-700 text-xs uppercase tracking-wide">
        Market Saturation
      </h3>

      {isLoading && (
        <div className="text-xs text-slate-400 animate-pulse">Loading saturation data…</div>
      )}

      {!isLoading && !saturation && (
        <div className="text-xs text-slate-400">
          No saturation data — competitor sync may still be running.
        </div>
      )}

      {saturation && (
        <>
          <table className="w-full text-xs border-collapse mb-3">
            <thead>
              <tr className="text-slate-400 text-[10px]">
                <th className="text-left pb-1">Ring</th>
                <th className="text-right pb-1">Pop</th>
                <th className="text-right pb-1">Sites</th>
                <th className="text-right pb-1">Sq Ft</th>
                <th className="text-right pb-1">Sq Ft/P</th>
              </tr>
            </thead>
            <tbody>
              {saturation.rings.map((ring) => {
                const isPrimary = ring.radius_miles === 3;
                const spp = ring.sqft_per_person;
                let color = "gray";
                if (spp !== null) {
                  color = spp < 7 ? "green" : spp < 10 ? "yellow" : "red";
                }
                return (
                  <tr
                    key={ring.radius_miles}
                    className={isPrimary ? "font-semibold" : "text-slate-600"}
                  >
                    <td className="py-0.5">{ring.radius_miles} mi</td>
                    <td className="text-right">{ring.population.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                    <td className="text-right">{ring.facility_count}</td>
                    <td className="text-right">{ring.total_sqft.toLocaleString()}</td>
                    <td className="text-right" style={{ color: SAT_COLORS[color] }}>
                      {spp !== null ? spp.toFixed(1) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div
            className="rounded px-3 py-2 text-center text-xs font-semibold"
            style={{
              backgroundColor: `${SAT_COLORS[saturation.color]}20`,
              color: SAT_COLORS[saturation.color],
              border: `1px solid ${SAT_COLORS[saturation.color]}40`,
            }}
          >
            3-Mile:{" "}
            {saturation.primary_sqft_per_person !== null
              ? `${saturation.primary_sqft_per_person?.toFixed(1)} sq ft/person`
              : "No data"}{" "}
            — {SAT_LABELS[saturation.color]}
          </div>
        </>
      )}
    </div>
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
