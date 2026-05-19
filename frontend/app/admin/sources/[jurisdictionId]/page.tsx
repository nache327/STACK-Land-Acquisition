"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { BulkActionBar } from "@/components/admin/BulkActionBar";
import { SourceDetailDrawer } from "@/components/admin/SourceDetailDrawer";
import {
  ConfidencePill,
  ValidationStatusPill,
} from "@/components/admin/StatusPill";
import {
  useAdminSources,
  useBulkReviewSources,
} from "@/hooks/useAdminSources";
import { useAdminCoverage } from "@/hooks/useAdminCoverage";
import type {
  BulkReviewAction,
  ZoningSource,
} from "@/lib/schemas";

const STATUS_OPTIONS = [
  { value: "", label: "all" },
  { value: "pending", label: "pending" },
  { value: "verified", label: "verified" },
  { value: "rejected", label: "rejected" },
  { value: "needs_review", label: "needs review" },
  { value: "token_gated", label: "token gated" },
  { value: "empty", label: "empty" },
];

const SORT_OPTIONS = [
  { value: "confidence", label: "confidence" },
  { value: "municipality", label: "municipality" },
  { value: "updated_at", label: "recent" },
];

export default function SourcesListPage() {
  const params = useParams<{ jurisdictionId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const jurisdictionId = params.jurisdictionId;

  const status = searchParams.get("status") ?? "pending";
  const confidenceMin = Number(searchParams.get("confidence_min") ?? "0");
  const municipality = searchParams.get("municipality") ?? "";
  const sortBy =
    (searchParams.get("sort_by") as
      | "confidence"
      | "municipality"
      | "updated_at"
      | null) ?? "confidence";

  const setParam = (k: string, v: string | null) => {
    const sp = new URLSearchParams(Array.from(searchParams.entries()));
    if (v == null || v === "") sp.delete(k);
    else sp.set(k, v);
    router.replace(`?${sp.toString()}`, { scroll: false });
  };

  const coverage = useAdminCoverage();
  const jurisdictionName = useMemo(() => {
    const hit = coverage.data?.jurisdictions.find(
      (j) => j.jurisdiction_id === jurisdictionId,
    );
    return hit?.jurisdiction_name ?? null;
  }, [coverage.data, jurisdictionId]);

  const filters = useMemo(
    () => ({
      status: status || undefined,
      confidence_min: Number.isFinite(confidenceMin) && confidenceMin > 0 ? confidenceMin : undefined,
      municipality: municipality || undefined,
      sort_by: sortBy,
      limit: 500,
    }),
    [status, confidenceMin, municipality, sortBy],
  );

  const sources = useAdminSources(jurisdictionId, filters);
  const bulk = useBulkReviewSources(jurisdictionId);

  const rows = sources.data?.sources ?? [];
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [drawerSource, setDrawerSource] = useState<ZoningSource | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Drop selections that disappear from the current result set.
  useEffect(() => {
    const ids = new Set(rows.map((r) => r.id));
    setSelected((prev) => {
      let changed = false;
      const next = new Set<string>();
      prev.forEach((id) => {
        if (ids.has(id)) next.add(id);
        else changed = true;
      });
      return changed ? next : prev;
    });
  }, [rows]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const toggleAll = () => {
    setSelected((prev) =>
      prev.size === rows.length
        ? new Set()
        : new Set(rows.map((r) => r.id)),
    );
  };

  const handleBulk = (action: BulkReviewAction, rejectedReason?: string) => {
    if (selected.size === 0) return;
    const ids = Array.from(selected);
    bulk.mutate(
      { ids, action, rejectedReason },
      {
        onSuccess: (res) => {
          setSelected(new Set());
          setToast(
            `${action}: ${res.updated} updated, ${res.skipped} skipped`,
          );
          setTimeout(() => setToast(null), 4000);
        },
      },
    );
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
            <Link href="/admin/sources" className="hover:underline">
              Sources
            </Link>{" "}
            ·{" "}
            <span className="font-mono text-slate-400">
              {jurisdictionId.slice(0, 8)}
            </span>
          </p>
          <h1 className="truncate text-lg font-semibold text-slate-900">
            {jurisdictionName ?? "Jurisdiction"}
          </h1>
          <p className="text-xs text-slate-500">
            {sources.data
              ? `${sources.data.total} matching · showing ${sources.data.count}`
              : "—"}
          </p>
        </div>
        <Link
          href="/admin/sources"
          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          ← All jurisdictions
        </Link>
      </header>

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-3">
        <label className="text-xs">
          <span className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Status
          </span>
          <select
            value={status}
            onChange={(e) => setParam("status", e.target.value || null)}
            className="mt-1 rounded-md border border-slate-200 px-2 py-1 text-sm"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs">
          <span className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Min confidence ({confidenceMin})
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={confidenceMin}
            onChange={(e) =>
              setParam("confidence_min", e.target.value === "0" ? null : e.target.value)
            }
            className="mt-2 w-48"
          />
        </label>
        <label className="text-xs">
          <span className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Municipality
          </span>
          <input
            type="text"
            value={municipality}
            onChange={(e) => setParam("municipality", e.target.value || null)}
            placeholder="exact match"
            className="mt-1 rounded-md border border-slate-200 px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs">
          <span className="block text-[11px] font-medium uppercase tracking-wide text-slate-500">
            Sort
          </span>
          <select
            value={sortBy}
            onChange={(e) => setParam("sort_by", e.target.value)}
            className="mt-1 rounded-md border border-slate-200 px-2 py-1 text-sm"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => sources.refetch()}
          className="ml-auto rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          {sources.isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <BulkActionBar
        selectedCount={selected.size}
        busy={bulk.isPending}
        onAction={handleBulk}
        onClear={() => setSelected(new Set())}
      />

      {toast && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          {toast}
        </div>
      )}
      {bulk.isError && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {(bulk.error as Error)?.message ?? "Bulk review failed."}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-8 px-3 py-2">
                <input
                  type="checkbox"
                  aria-label="Select all"
                  checked={rows.length > 0 && selected.size === rows.length}
                  onChange={toggleAll}
                />
              </th>
              <th className="px-3 py-2">Municipality</th>
              <th className="px-3 py-2">Layer</th>
              <th className="px-3 py-2 text-right">Conf</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Discovered</th>
              <th className="px-3 py-2">Verified at</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sources.isPending && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  Loading sources…
                </td>
              </tr>
            )}
            {sources.isError && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs text-rose-600">
                  {(sources.error as Error)?.message ?? "Failed to load."}
                </td>
              </tr>
            )}
            {!sources.isPending && !sources.isError && rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-xs italic text-slate-400">
                  No sources match these filters.
                </td>
              </tr>
            )}
            {rows.map((r) => {
              const isSelected = selected.has(r.id);
              return (
                <tr
                  key={r.id}
                  className={[
                    "cursor-pointer",
                    isSelected ? "bg-sky-50" : "hover:bg-slate-50",
                  ].join(" ")}
                  onClick={() => setDrawerSource(r)}
                >
                  <td
                    className="px-3 py-2"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      aria-label={`Select ${r.municipality_name ?? r.id}`}
                      checked={isSelected}
                      onChange={() => toggle(r.id)}
                    />
                  </td>
                  <td className="px-3 py-2 font-medium text-slate-800">
                    {r.municipality_name ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-slate-600">
                    <span className="block truncate" title={r.title ?? undefined}>
                      {r.title ?? r.zoning_endpoint ?? "—"}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {r.source_type ?? "—"} · {r.geometry_type ?? "—"} ·{" "}
                      features {r.feature_count ?? "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <ConfidencePill score={r.confidence_score} />
                  </td>
                  <td className="px-3 py-2">
                    <ValidationStatusPill status={r.validation_status} />
                  </td>
                  <td className="px-3 py-2 text-[11px] text-slate-500">
                    {r.discovered_by ?? "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-slate-500">
                    {r.last_verified_at
                      ? r.last_verified_at.slice(0, 10)
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {drawerSource && (
        <SourceDetailDrawer
          jurisdictionId={jurisdictionId}
          source={drawerSource}
          onClose={() => setDrawerSource(null)}
        />
      )}
    </div>
  );
}
