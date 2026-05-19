"use client";

import Link from "next/link";
import { ConfidenceTierPill } from "./ConfidenceTierPill";
import { ValidationStatusPill } from "./StatusPill";
import { SuggestedActionPill } from "./SuggestedActionPill";
import {
  type MunicipalityBreakdownDict,
} from "@/lib/admin/municipality";
import { sourceIsSpatiallyBlocked } from "@/lib/admin/municipality";
import { roiTagFor } from "@/lib/admin/roiWeight";
import { suggestActionForSource } from "@/lib/admin/suggestAction";
import type { QueueSource } from "@/lib/schemas";

interface Props {
  rows: QueueSource[];
  selected: Set<string>;
  onToggle: (sourceId: string) => void;
  onToggleAll: () => void;
  /** When set, the row click navigates to the per-jurisdiction review screen
   *  with the source highlighted via query string (?source_id=). */
  rowHrefFor?: (row: QueueSource) => string;
  /** Optional click handler. If provided, clicking the layer cell calls
   *  this instead of navigating — used to open the drawer in place. */
  onOpenRow?: (row: QueueSource) => void;
  /** Index of `municipality_breakdown` JSONBs keyed by jurisdiction id.
   *  When provided, an "ROI: N unzoned" badge is shown per row. */
  municipalityIndex?: Map<string, MunicipalityBreakdownDict>;
  emptyMessage?: string;
}

export function CrossJurisdictionSourceTable({
  rows,
  selected,
  onToggle,
  onToggleAll,
  rowHrefFor,
  onOpenRow,
  municipalityIndex,
  emptyMessage,
}: Props) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="w-8 px-3 py-2">
              <input
                type="checkbox"
                aria-label="Select all"
                checked={rows.length > 0 && selected.size === rows.length}
                onChange={onToggleAll}
              />
            </th>
            <th className="px-3 py-2">Jurisdiction</th>
            <th className="px-3 py-2">Municipality</th>
            <th className="px-3 py-2">Layer</th>
            <th className="px-3 py-2 text-right">Conf</th>
            <th className="px-3 py-2">Suggest</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 && (
            <tr>
              <td colSpan={8} className="px-3 py-6 text-center text-xs italic text-slate-400">
                {emptyMessage ?? "Nothing in this queue right now."}
              </td>
            </tr>
          )}
          {rows.map((r) => {
            const isSelected = selected.has(r.id);
            const blocked = sourceIsSpatiallyBlocked(r);
            const href = rowHrefFor ? rowHrefFor(r) : null;
            const suggestion = suggestActionForSource(r);
            const roi = municipalityIndex
              ? roiTagFor(r, municipalityIndex)
              : null;
            return (
              <tr
                key={r.id}
                className={[
                  isSelected
                    ? "bg-sky-50"
                    : blocked
                      ? "bg-rose-50/40 hover:bg-rose-50"
                      : "hover:bg-slate-50",
                ].join(" ")}
              >
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label={`Select ${r.municipality_name ?? r.id}`}
                    checked={isSelected}
                    onChange={() => onToggle(r.id)}
                  />
                </td>
                <td className="px-3 py-2">
                  <Link
                    href={`/admin/coverage/${r.jurisdiction_id}`}
                    className="font-medium text-slate-800 hover:underline"
                  >
                    {r.jurisdiction_name}
                  </Link>
                  {r.state && (
                    <span className="ml-1 font-mono text-[10px] text-slate-400">
                      {r.state}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-700">
                  <div className="flex items-center gap-1">
                    <span>{r.municipality_name ?? "—"}</span>
                    {blocked && (
                      <span
                        className="text-[10px] font-medium text-rose-700"
                        title="Persisted confidence_breakdown carries wrong_state / wrong_county / bbox_overlap_disjoint."
                      >
                        ◆ CRS
                      </span>
                    )}
                  </div>
                  {roi && (
                    <span
                      title={`${roi.unzoned_parcels.toLocaleString()} parcels in ${r.municipality_name} have no zoning yet — verifying this row unlocks coverage.`}
                      className="mt-0.5 inline-flex items-center gap-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600"
                    >
                      ROI {roi.unzoned_parcels.toLocaleString()}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-600">
                  {onOpenRow ? (
                    <button
                      type="button"
                      onClick={() => onOpenRow(r)}
                      className="block max-w-[260px] truncate text-left hover:underline"
                      title={r.title ?? r.zoning_endpoint ?? undefined}
                    >
                      {r.title ?? r.zoning_endpoint ?? "—"}
                    </button>
                  ) : href ? (
                    <Link
                      href={href}
                      className="block max-w-[260px] truncate hover:underline"
                      title={r.title ?? r.zoning_endpoint ?? undefined}
                    >
                      {r.title ?? r.zoning_endpoint ?? "—"}
                    </Link>
                  ) : (
                    <span className="block max-w-[260px] truncate" title={r.title ?? undefined}>
                      {r.title ?? r.zoning_endpoint ?? "—"}
                    </span>
                  )}
                  <span className="text-[10px] text-slate-400">
                    {r.source_type ?? "—"} · {r.geometry_type ?? "—"} ·{" "}
                    features {r.feature_count ?? "—"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <ConfidenceTierPill score={r.confidence_score} showNumber />
                </td>
                <td className="px-3 py-2">
                  <SuggestedActionPill suggestion={suggestion} />
                </td>
                <td className="px-3 py-2">
                  <ValidationStatusPill status={r.validation_status} />
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-slate-500">
                  {r.updated_at ? r.updated_at.slice(0, 10) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
