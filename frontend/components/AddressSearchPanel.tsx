"use client";

/**
 * What you get after typing a broker address: the parcel, an honest account of what
 * we actually know about it, and what else nearby qualifies.
 *
 * The readiness chips are the point. Before this, a parcel whose zoning had never been
 * human-reviewed and a parcel whose zoning genuinely PROHIBITS storage both rendered as
 * a blank — so a found parcel still read as broken. "Not verified" (amber) and
 * "Prohibited" (red) are different claims and must never look alike.
 */

import { useEffect, useState } from "react";

import {
  api,
  type LocateGeocoded,
  type LocateResult,
  type NearbyParcel,
  type NearbyResponse,
} from "@/lib/api";

type ChipTone = "good" | "warn" | "bad" | "muted";

const TONE: Record<ChipTone, string> = {
  // Amber (warn) is reserved for "we don't know", red (bad) for a determined negative.
  good: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  warn: "bg-amber-50 text-amber-900 ring-amber-600/30",
  bad: "bg-rose-50 text-rose-800 ring-rose-600/20",
  muted: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

function Chip({
  tone,
  label,
  title,
}: {
  tone: ChipTone;
  label: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE[tone]}`}
    >
      {label}
    </span>
  );
}

const money = (v: number | null) =>
  v == null ? null : `$${Math.round(v).toLocaleString()}`;

/** Verdict → chip tone. `null` means UNGROUNDED, which is not a verdict at all. */
function verdictTone(v: string | null, grounded: boolean): ChipTone {
  if (!grounded || v == null) return "warn";
  if (v === "permitted" || v === "conditional") return "good";
  if (v === "prohibited") return "bad";
  return "muted"; // 'unclear'
}

function ReadinessChips({ r }: { r: LocateResult }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {r.zoning_grounded ? (
        <Chip
          tone="good"
          label="Zoning verified"
          title="A human-reviewed zoning matrix row backs this parcel's zone."
        />
      ) : (
        <Chip
          tone="warn"
          label="Zoning NOT verified"
          title={
            r.has_zoning_code
              ? `Zone ${r.zoning_code ?? "?"} has no human-reviewed verdict yet. This is not the same as prohibited — we simply have not grounded it.`
              : "This parcel has no zoning code bound yet."
          }
        />
      )}

      {r.ring_measured ? (
        <Chip
          tone="good"
          label="Wealth measured"
          title="10-minute drive-time ring has real ACS home value and income."
        />
      ) : (
        <Chip
          tone="warn"
          label="Wealth unmeasured"
          title="No valid 10-minute ring yet. Unmeasured — not $0."
        />
      )}

      {r.scored ? (
        <Chip tone="good" label="Scored" />
      ) : (
        <Chip tone="muted" label="Not scored" />
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 py-0.5 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-900">{value}</span>
    </div>
  );
}

/** A missing value states WHY it is missing rather than rendering an empty cell. */
const unknown = (why: string) => (
  <span className="font-normal italic text-slate-400">{why}</span>
);

export function AddressSearchPanel({
  result,
  coverage,
  geocoded,
  onPickNearby,
  onQueueCounty,
}: {
  result: LocateResult | null;
  coverage: "in_coverage" | "out_of_coverage" | "unresolved";
  geocoded: LocateGeocoded | null;
  onPickNearby?: (p: NearbyParcel) => void;
  onQueueCounty?: (g: LocateGeocoded) => void;
}) {
  const [nearby, setNearby] = useState<NearbyResponse | null>(null);
  const [loadingNearby, setLoadingNearby] = useState(false);
  const [nearbyErr, setNearbyErr] = useState<string | null>(null);
  const [qualifyingOnly, setQualifyingOnly] = useState(true);

  const lat = result?.lat ?? geocoded?.lat ?? null;
  const lng = result?.lng ?? geocoded?.lng ?? null;

  useEffect(() => {
    if (lat == null || lng == null) {
      setNearby(null);
      return;
    }
    let cancelled = false;
    setLoadingNearby(true);
    setNearbyErr(null);
    api
      .nearbyParcels(lat, lng, { radiusMiles: 3, limit: 50, qualifyingOnly })
      .then((res) => {
        if (!cancelled) setNearby(res);
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setNearbyErr(e instanceof Error ? e.message : "Nearby lookup failed");
      })
      .finally(() => {
        if (!cancelled) setLoadingNearby(false);
      });
    return () => {
      cancelled = true;
    };
  }, [lat, lng, qualifyingOnly]);

  if (coverage === "unresolved") {
    return (
      <div className="rounded-md border border-slate-200 bg-white p-3">
        <p className="text-sm font-medium text-slate-900">
          Could not resolve that address
        </p>
        <p className="mt-1 text-sm text-slate-500">
          Check for a typo, or paste the APN instead.
        </p>
      </div>
    );
  }

  if (coverage === "out_of_coverage") {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
        <p className="text-sm font-medium text-amber-900">Not in coverage</p>
        <p className="mt-1 text-sm text-amber-800">
          We found{" "}
          <span className="font-medium">
            {geocoded?.matched_address ?? "this address"}
          </span>
          , but no parcels have been ingested there yet.
        </p>
        {geocoded && onQueueCounty && (
          <button
            type="button"
            onClick={() => onQueueCounty(geocoded)}
            className="mt-2 rounded bg-amber-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
          >
            Add this county
            {geocoded.county_fips
              ? ` (FIPS ${geocoded.state_fips}${geocoded.county_fips})`
              : ""}
          </button>
        )}
      </div>
    );
  }

  if (!result) return null;

  const ssTone = verdictTone(result.verdict_self_storage, result.zoning_grounded);
  const lgcTone = verdictTone(result.verdict_lgc, result.zoning_grounded);

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-slate-200 bg-white p-3">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-slate-900">
              {result.address ?? result.apn ?? `Parcel ${result.parcel_id}`}
            </p>
            <p className="text-xs text-slate-500">
              {[result.city, result.state, result.jurisdiction_name]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </div>
        </div>

        <ReadinessChips r={result} />

        <div className="mt-2 divide-y divide-slate-100">
          <Field label="APN" value={result.apn ?? unknown("not recorded")} />
          <Field
            label="Acres"
            value={
              result.acres != null
                ? result.acres.toFixed(2)
                : unknown("not recorded")
            }
          />
          <Field
            label="Owner"
            value={result.owner_name ?? unknown("not recorded")}
          />
          <Field
            label="Zoning"
            value={result.zoning_code ?? unknown("not bound")}
          />
          <Field
            label="Self-storage"
            value={
              result.zoning_grounded && result.verdict_self_storage ? (
                <Chip tone={ssTone} label={result.verdict_self_storage} />
              ) : (
                <Chip tone="warn" label="not verified" />
              )
            }
          />
          <Field
            label="Garage condo (LGC)"
            value={
              result.zoning_grounded && result.verdict_lgc ? (
                <Chip tone={lgcTone} label={result.verdict_lgc} />
              ) : (
                <Chip tone="warn" label="not verified" />
              )
            }
          />
          <Field
            label="Ring home value"
            value={
              result.ring_measured
                ? money(result.ring_median_home_value)
                : unknown("unmeasured")
            }
          />
          <Field
            label="Ring income"
            value={
              result.ring_measured
                ? money(result.ring_median_hhi)
                : unknown("unmeasured")
            }
          />
        </div>
      </div>

      <div className="rounded-md border border-slate-200 bg-white p-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-900">
            Nearby{" "}
            <span className="font-normal text-slate-500">
              (within {nearby?.radius_miles ?? 3} mi)
            </span>
          </p>
          <label className="flex items-center gap-1.5 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={qualifyingOnly}
              onChange={(e) => setQualifyingOnly(e.target.checked)}
            />
            Qualifying only
          </label>
        </div>

        {loadingNearby && <p className="text-sm text-slate-500">Searching…</p>}
        {nearbyErr && <p className="text-sm text-rose-700">{nearbyErr}</p>}

        {nearby && !loadingNearby && nearby.results.length === 0 && (
          <p className="text-sm text-slate-500">
            {qualifyingOnly
              ? "Nothing nearby clears the buy box."
              : "No parcels found nearby."}
          </p>
        )}

        {nearby && nearby.results.length > 0 && (
          <>
            <p className="mb-1.5 text-xs text-slate-500">
              {nearby.qualifying_count} qualifying
              {/* Never let a capped list read as exhaustive. */}
              {nearby.truncated
                ? ` · showing first ${nearby.results.length}`
                : ""}
            </p>
            <ul className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
              {nearby.results.map((p) => (
                <li key={p.parcel_id}>
                  <button
                    type="button"
                    onClick={() => onPickNearby?.(p)}
                    className="flex w-full items-center justify-between gap-2 px-1 py-1.5 text-left hover:bg-slate-50"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-slate-900">
                        {p.address ?? p.apn ?? `Parcel ${p.parcel_id}`}
                      </span>
                      <span className="block truncate text-xs text-slate-500">
                        {[
                          p.city,
                          p.zoning_code,
                          p.acres != null ? `${p.acres.toFixed(1)} ac` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {!p.zoning_grounded && (
                        <Chip tone="warn" label="unverified" />
                      )}
                      {p.qualifies && <Chip tone="good" label="qualifies" />}
                      <span className="w-12 text-right text-xs tabular-nums text-slate-500">
                        {p.distance_miles != null
                          ? `${p.distance_miles.toFixed(2)} mi`
                          : ""}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
