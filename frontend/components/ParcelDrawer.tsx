"use client";

import { useEffect, useMemo } from "react";
import type { ParcelDetail } from "@/lib/schemas";
import type { ServerParcelScore } from "@/lib/api";
import { useVerification } from "@/hooks/useVerification";
import { useParcelSaturation } from "@/hooks/useParcelSaturation";
import { useJurisdictionListings } from "@/hooks/useJurisdictionListings";
import type { JurisdictionListing } from "@/hooks/useJurisdictionListings";
import { VerificationPanel } from "./VerificationPanel";
import {
  computeScore,
  TIER_BADGE_CLASSES,
  TIER_LABELS,
  type ScoreTier,
} from "@/lib/compositeScore";
import type { BuyBoxFilter, DriveTime } from "@/lib/buy-box-filter";
import type { PrecomputedRingMetrics } from "@/lib/isochrone-precompute";

interface ParcelDrawerProps {
  parcel: ParcelDetail | null;
  jurisdictionId: string;
  onClose: () => void;
  isInShortlist?: boolean;
  onToggleShortlist?: () => void;
  onShowRing?: () => void;
  /** Server-side score for this parcel from `parcel_buybox_scores`.
   *  When present, overrides the placeholder client-side `computeScore`. */
  serverScore?: ServerParcelScore;
  /** Everything needed to render the unified Buy Box Match panel.
   *  `ring` is null when precompute hasn't reached this parcel yet. */
  buyBoxMatch?: {
    driveTimeMinutes: DriveTime;
    filter: BuyBoxFilter;
    ring: PrecomputedRingMetrics | null;
    parcelAadt: number | null;
    wealthDensityAvailable: boolean;
  } | null;
}

export function ParcelDrawer({
  parcel,
  jurisdictionId,
  onClose,
  isInShortlist = false,
  onToggleShortlist,
  onShowRing,
  serverScore,
  buyBoxMatch,
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

  // Pull listings for this jurisdiction once per drawer-open. Find the
  // current one matching this parcel (if any). One fetch, used by both
  // the ListingCard above and any future filter logic.
  const { data: listings } = useJurisdictionListings(
    parcel ? jurisdictionId : null,
  );
  const matchedListing: JurisdictionListing | undefined = parcel
    ? listings?.find(
        (l) => l.matched_parcel_id === parcel.id && l.is_current,
      )
    : undefined;

  const score = useMemo(() => {
    if (!parcel) return null;
    if (serverScore) {
      return {
        score: serverScore.score,
        tier: serverScore.tier as ScoreTier,
        factors: serverScore.factors.map((f) => ({
          label: f.label,
          delta: f.delta,
          reason: f.reason,
        })),
      };
    }
    return computeScore(parcel);
  }, [parcel, serverScore]);

  // Auto-run Layer 1 when drawer opens with a new parcel
  useEffect(() => {
    if (parcel?.zoning_code) {
      runLayer1();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parcel?.apn]);

  if (!parcel) return null;

  return (
    <aside className="fixed inset-y-0 right-[720px] z-50 w-[440px] overflow-y-auto border-x border-slate-200 bg-white shadow-2xl">
      <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 className="font-semibold text-slate-900">Parcel Detail</h2>
        <div className="flex items-center gap-2">
          {onShowRing && (
            <button
              onClick={onShowRing}
              title="Show 3-mile ring on map"
              className="rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
            >
              ◎ 3-mi Ring
            </button>
          )}
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
        {/* Composite score */}
        {score && (
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700">
                Site Score
              </h3>
              <span
                className={`inline-flex items-baseline gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-semibold tabular-nums ${TIER_BADGE_CLASSES[score.tier]}`}
              >
                {score.score}
                <span className="text-[10px] font-medium opacity-80">
                  {TIER_LABELS[score.tier]}
                </span>
              </span>
            </div>
            <table className="w-full text-xs">
              <tbody>
                {score.factors.map((f, i) => {
                  const positive = f.delta > 0;
                  const negative = f.delta < 0;
                  return (
                    <tr key={i} className="border-t border-slate-100 first:border-t-0">
                      <td className="py-1 pr-2 text-slate-500">{f.label}</td>
                      <td className="py-1 pr-2 text-slate-400">{f.reason}</td>
                      <td
                        className={[
                          "py-1 text-right font-mono tabular-nums",
                          positive ? "text-emerald-700" : "",
                          negative ? "text-red-600" : "",
                          !positive && !negative ? "text-slate-500" : "",
                        ].join(" ")}
                      >
                        {f.delta > 0 ? "+" : ""}
                        {f.delta}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-[10px] text-slate-400">
              {serverScore
                ? `Server-computed ${new Date(serverScore.computed_at).toLocaleDateString()}`
                : "Client-computed (no server score yet — backend will populate after next scoring run)"}
            </p>
          </div>
        )}

        {/* Listing card — surfaces when this parcel matches a current
            for-sale listing (any source, confidence >= 0.85). */}
        {matchedListing && <ListingCard listing={matchedListing} />}

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

        {/* Buy Box Match — all active filter dimensions vs this parcel */}
        {buyBoxMatch && <BuyBoxMatchPanel match={buyBoxMatch} />}

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

type RowFormat = "int" | "currency";

interface MatchRow {
  key: string;
  label: string;
  actual: number | null;
  threshold: number | null;
  format: RowFormat;
  /** Skip pass/fail evaluation (slider off and we're showing the row only
   *  for context, e.g. measured wealth-density value with no threshold). */
  inactive: boolean;
}

function fmtValue(n: number | null, format: RowFormat): string {
  if (n == null) return "—";
  if (format === "currency") {
    if (n >= 1000) return `$${(n / 1000).toFixed(0)}K`;
    return `$${n.toLocaleString()}`;
  }
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K`;
  return n.toLocaleString();
}

function BuyBoxMatchPanel({
  match,
}: {
  match: NonNullable<ParcelDrawerProps["buyBoxMatch"]>;
}) {
  const { driveTimeMinutes, filter, ring, parcelAadt, wealthDensityAvailable } = match;

  const rows: MatchRow[] = useMemo(() => {
    const out: MatchRow[] = [];
    if (ring) {
      out.push({
        key: "population",
        label: "Population",
        actual: ring.totalPopulation,
        threshold: filter.minPopulation,
        format: "int",
        inactive: filter.minPopulation == null,
      });
      out.push({
        key: "medianHHI",
        label: "Median HHI",
        actual: ring.weightedMedianHHI,
        threshold: filter.minMedianHHI,
        format: "currency",
        inactive: filter.minMedianHHI == null,
      });
      out.push({
        key: "homeValue",
        label: "Home Value",
        actual: ring.weightedMedianHomeValue,
        threshold: filter.minMedianHomeValue,
        format: "currency",
        inactive: filter.minMedianHomeValue == null,
      });
      out.push({
        key: "hnwHouseholds",
        label: "HNW Households",
        actual: ring.hnwHouseholds,
        threshold: filter.minHnwHouseholds,
        format: "int",
        inactive: filter.minHnwHouseholds == null,
      });
    }
    if (filter.minAADT != null) {
      out.push({
        key: "aadt",
        label: "AADT",
        actual: parcelAadt,
        threshold: filter.minAADT,
        format: "int",
        inactive: false,
      });
    }
    if (ring) {
      const wealthRow = (
        key: string,
        label: string,
        threshold: number | null,
        actual: number | null,
      ): void => {
        if (threshold == null && actual == null) return;
        out.push({
          key,
          label,
          actual,
          threshold,
          format: "int",
          inactive: threshold == null || !wealthDensityAvailable,
        });
      };
      wealthRow("homesOver1M", "Homes ≥ $1M", filter.minHomesOver1M, ring.homesOver1M);
      wealthRow("homesOver2M", "Homes ≥ $2M", filter.minHomesOver2M, ring.homesOver2M);
      wealthRow("homesOver5M", "Homes ≥ $5M", filter.minHomesOver5M, ring.homesOver5M);
    }
    return out;
  }, [filter, ring, parcelAadt, wealthDensityAvailable]);

  // Per-row verdict
  const rowStatus = (r: MatchRow): "pass" | "fail" | "borderline" | "none" => {
    if (r.inactive || r.threshold == null) return "none";
    if (r.actual == null) return "fail";
    if (r.actual >= r.threshold) return "pass";
    if (r.actual >= r.threshold * 0.9) return "borderline";
    return "fail";
  };

  // Overall verdict — match the rules in evaluateParcel
  const active = rows.filter((r) => !r.inactive && r.threshold != null);
  let verdict: "computing" | "match" | "borderline" | "fail";
  if (!ring) {
    verdict = "computing";
  } else if (active.length === 0) {
    verdict = "match";
  } else {
    const statuses = active.map(rowStatus);
    if (filter.matchLogic === "OR") {
      verdict = statuses.some((s) => s === "pass") ? "match" : "fail";
    } else {
      const hardFails = statuses.filter((s) => s === "fail").length;
      const borderline = statuses.filter((s) => s === "borderline").length;
      if (hardFails > 0) verdict = "fail";
      else if (borderline > 0) verdict = "borderline";
      else verdict = "match";
    }
  }

  const verdictStyle: Record<typeof verdict, { bg: string; fg: string; label: string }> = {
    computing: { bg: "#94a3b820", fg: "#475569", label: "Computing…" },
    match:     { bg: "#10b98120", fg: "#047857", label: filter.matchLogic === "OR" ? "Match (any)" : "Match (all)" },
    borderline:{ bg: "#f59e0b20", fg: "#b45309", label: "Borderline" },
    fail:      { bg: "#ef444420", fg: "#b91c1c", label: "Fail" },
  };

  return (
    <div className="rounded-lg border border-slate-200 p-3 text-sm">
      <h3 className="mb-2 font-semibold text-slate-700 text-xs uppercase tracking-wide">
        Buy Box Match · {driveTimeMinutes}-min drive
      </h3>

      {!ring ? (
        <div className="text-xs text-slate-400">
          Computing drive-time metrics — open the dashboard with the buy box active to populate.
        </div>
      ) : rows.length === 0 ? (
        <div className="text-xs text-slate-400">
          No active criteria. Set thresholds in the Buy Box panel to evaluate this parcel.
        </div>
      ) : (
        <>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-400 text-[10px]">
                <th className="text-left pb-1 font-medium">Criterion</th>
                <th className="text-right pb-1 font-medium">Parcel</th>
                <th className="text-right pb-1 font-medium">Need</th>
                <th className="text-right pb-1 font-medium w-6"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const s = rowStatus(r);
                const marker =
                  s === "pass" ? "✓" :
                  s === "fail" ? "✗" :
                  s === "borderline" ? "~" :
                  "";
                const markerClass =
                  s === "pass" ? "text-emerald-600" :
                  s === "fail" ? "text-red-600" :
                  s === "borderline" ? "text-amber-600" :
                  "text-slate-300";
                return (
                  <tr key={r.key} className="border-t border-slate-100 first:border-t-0">
                    <td className="py-1 text-slate-500">{r.label}</td>
                    <td className="py-1 text-right font-mono tabular-nums text-slate-900">
                      {fmtValue(r.actual, r.format)}
                    </td>
                    <td className="py-1 text-right font-mono tabular-nums text-slate-400">
                      {r.threshold == null ? "—" : fmtValue(r.threshold, r.format)}
                    </td>
                    <td className={`py-1 text-right font-semibold ${markerClass}`}>{marker}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div
            className="mt-3 rounded px-3 py-2 text-center text-xs font-semibold"
            style={{
              backgroundColor: verdictStyle[verdict].bg,
              color: verdictStyle[verdict].fg,
              border: `1px solid ${verdictStyle[verdict].fg}40`,
            }}
          >
            {verdictStyle[verdict].label}
          </div>
        </>
      )}
    </div>
  );
}

function ListingCard({ listing }: { listing: JurisdictionListing }) {
  const price =
    listing.sale_price != null
      ? `$${listing.sale_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
      : "Price n/a";
  const dom =
    listing.days_on_market != null ? `${listing.days_on_market} days on market` : null;
  const brokerLine = [listing.listing_broker_contact, listing.listing_broker_company]
    .filter(Boolean)
    .join(", ");
  const contactLine = [listing.listing_broker_phone, listing.listing_broker_email]
    .filter(Boolean)
    .join(" · ");
  const statusColor =
    listing.sale_status?.toLowerCase() === "active"
      ? "#059669"
      : listing.sale_status?.toLowerCase() === "under contract"
      ? "#d97706"
      : "#64748b";
  return (
    <div
      className="rounded-lg border p-3 text-sm"
      style={{
        backgroundColor: "#fef3c7",
        borderColor: "#fcd34d",
        color: "#92400e",
      }}
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide">
          🏷️ Listed for sale
        </h3>
        <span
          className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase"
          style={{ backgroundColor: statusColor, color: "#fff" }}
        >
          {listing.sale_status || "Active"}
        </span>
      </div>
      <div className="font-mono text-base font-semibold text-slate-900">
        {price}
      </div>
      <div className="mt-0.5 text-xs text-slate-700">
        via <strong>{listing.source}</strong>
        {dom ? <span> · {dom}</span> : null}
      </div>
      {brokerLine && (
        <div className="mt-2 text-xs text-slate-800">
          Broker: <strong>{brokerLine}</strong>
        </div>
      )}
      {contactLine && (
        <div className="mt-0.5 text-xs text-slate-800">
          Contact: <span className="font-mono">{contactLine}</span>
        </div>
      )}
      {listing.co_listed_parcels && listing.co_listed_parcels.length > 1 && (
        <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800">
          <div className="font-semibold">
            Same owner selling {listing.co_listed_parcels.length} adjacent parcels
          </div>
          <ul className="mt-1 list-disc pl-4">
            {listing.co_listed_parcels.map((p) => (
              <li key={p.id}>
                APN {p.apn}
                {p.acres != null ? ` · ${p.acres.toFixed(2)} ac` : ""}
                {p.is_primary ? " (primary)" : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {listing.match_confidence != null && listing.match_confidence < 1.0 && (
        <div className="mt-2 text-[10px] text-slate-500">
          Match confidence {(listing.match_confidence * 100).toFixed(0)}% · {listing.match_method}
        </div>
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
