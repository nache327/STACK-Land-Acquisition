"use client";

/**
 * /admin/op5-review — batch review queue for Op-5 matrix adjudications.
 *
 * The Op-5 factory build pushes ~1,500 zone-code decisions across 210
 * NJ municipalities into `zone_use_matrix` as pending rows
 * (human_reviewed=false). Per-row click-through to approve every one
 * would cap throughput. This page surfaces those rows with:
 *   - confidence/county/status filters,
 *   - per-row approve + reject buttons,
 *   - a "Bulk-approve all rows in current filter" toolbar action
 *     keyed off the min-confidence slider (default 0.90).
 *
 * No new auth surface — follows the same auth posture as
 * /admin/listings (the existing admin admin page).
 *
 * Backend contract: see `backend/app/api/admin_op5.py`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  type AdjudicationRow,
  type Op5UsePermission,
} from "@/lib/api";

const PERMISSION_STYLES: Record<Op5UsePermission, string> = {
  permitted: "bg-emerald-100 text-emerald-800 border-emerald-200",
  conditional: "bg-amber-100 text-amber-800 border-amber-200",
  prohibited: "bg-rose-100 text-rose-800 border-rose-200",
  unclear: "bg-slate-100 text-slate-600 border-slate-200",
};

function PermissionPill({ value }: { value: Op5UsePermission }) {
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-tight ${PERMISSION_STYLES[value]}`}
    >
      {value}
    </span>
  );
}

function ConfidenceBadge({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  const pct = Math.round(value * 100);
  const color =
    value >= 0.9
      ? "text-emerald-700"
      : value >= 0.7
        ? "text-amber-700"
        : "text-rose-700";
  return (
    <span className={`font-mono text-xs ${color}`}>
      {pct}%
    </span>
  );
}

function CitationsCell({ citations }: { citations: AdjudicationRow["citations"] }) {
  const [open, setOpen] = useState(false);
  if (!citations || citations.length === 0) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  return (
    <div className="text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-slate-600 underline-offset-2 hover:underline"
      >
        {citations.length} cite{citations.length === 1 ? "" : "s"}
        {open ? " ▴" : " ▾"}
      </button>
      {open && (
        <ul className="mt-1 space-y-1">
          {citations.map((c, i) => (
            <li
              key={i}
              className="rounded border border-slate-200 bg-slate-50 p-1.5"
            >
              <div className="font-mono text-[10px] text-slate-500">
                {c.section ?? "(no section)"}
              </div>
              <div className="text-[11px] text-slate-700">
                {c.quote ?? "(no quote)"}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Op5ReviewPage() {
  // Filters
  const [status, setStatus] = useState<"pending" | "approved">("pending");
  const [county, setCounty] = useState("");
  const [stateFilter, setStateFilter] = useState("NJ");
  const [minConf, setMinConf] = useState(0);
  const [bulkThreshold, setBulkThreshold] = useState(0.9);

  // Data
  const [rows, setRows] = useState<AdjudicationRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyRowIds, setBusyRowIds] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listOp5Adjudications({
        status,
        county: county || undefined,
        state: stateFilter || undefined,
        min_confidence: minConf,
        limit: 250,
      });
      setRows(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [status, county, stateFilter, minConf]);

  useEffect(() => {
    void fetchRows();
  }, [fetchRows]);

  const setBusy = useCallback((id: number, busy: boolean) => {
    setBusyRowIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const handleApprove = useCallback(
    async (row: AdjudicationRow) => {
      setBusy(row.id, true);
      // Optimistic remove from pending view; on error, refetch.
      const prev = rows;
      if (status === "pending") {
        setRows((rs) => rs.filter((r) => r.id !== row.id));
      }
      try {
        await api.approveOp5Adjudication(row.id);
        setToast(`Approved ${row.jurisdiction_name} · ${row.zone_code}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setRows(prev);
      } finally {
        setBusy(row.id, false);
      }
    },
    [rows, setBusy, status]
  );

  const handleReject = useCallback(
    async (row: AdjudicationRow) => {
      const reason = window.prompt(
        `Reject ${row.jurisdiction_name} · ${row.zone_code}? Enter reason:`
      );
      if (!reason) return;
      setBusy(row.id, true);
      const prev = rows;
      setRows((rs) => rs.filter((r) => r.id !== row.id));
      try {
        await api.rejectOp5Adjudication(row.id, { reason });
        setToast(`Rejected ${row.jurisdiction_name} · ${row.zone_code}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setRows(prev);
      } finally {
        setBusy(row.id, false);
      }
    },
    [rows, setBusy]
  );

  const handleBulkApprove = useCallback(async () => {
    const targets = rows.filter(
      (r) =>
        r.confidence !== null &&
        r.confidence >= bulkThreshold &&
        !r.human_reviewed
    );
    if (targets.length === 0) {
      setToast(
        `No pending rows at >= ${Math.round(bulkThreshold * 100)}% confidence in the current filter.`
      );
      return;
    }
    const ok = window.confirm(
      `Approve ${targets.length} rows at >= ${Math.round(bulkThreshold * 100)}% confidence? This sets human_reviewed=true; rejection is per-row only.`
    );
    if (!ok) return;
    setBulkBusy(true);
    setError(null);
    try {
      // Use by_filter so the server can apply identical logic + return the
      // authoritative count even if the page list is paginated. Pass
      // current filters so the bulk action == "what I see + threshold".
      const result = await api.bulkApproveOp5Adjudications({
        by_filter: {
          county: county || undefined,
          state: stateFilter || undefined,
          min_confidence: bulkThreshold,
          max_rows: 500,
        },
      });
      setToast(`Bulk-approved ${result.approved} rows.`);
      await fetchRows();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkBusy(false);
    }
  }, [rows, bulkThreshold, county, stateFilter, fetchRows]);

  const counts = useMemo(() => {
    const high = rows.filter(
      (r) => r.confidence !== null && r.confidence >= 0.9
    ).length;
    const low = rows.length - high;
    return { high, low, total: rows.length };
  }, [rows]);

  return (
    <main className="mx-auto max-w-7xl p-6">
      <header className="mb-4 flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">
            Op-5 matrix review queue
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Batch sign-off for zone_use_matrix rows produced by the Op-5
            factory pipeline. Bulk-approve high-confidence rows; eyeball
            the rest.
          </p>
        </div>
        <div className="text-xs text-slate-500">
          showing {counts.total} rows · {counts.high} high-conf ·{" "}
          {counts.low} low-conf
        </div>
      </header>

      {/* Filters */}
      <section className="mb-4 grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-5">
        <div>
          <label className="block text-xs font-medium text-slate-700">
            Status
          </label>
          <select
            value={status}
            onChange={(e) =>
              setStatus(e.target.value as "pending" | "approved")
            }
            className="mt-1 block w-full rounded-md border-slate-300 text-sm"
          >
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700">
            State
          </label>
          <input
            type="text"
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value.toUpperCase())}
            placeholder="NJ"
            className="mt-1 block w-full rounded-md border-slate-300 text-sm font-mono"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700">
            County
          </label>
          <input
            type="text"
            value={county}
            onChange={(e) => setCounty(e.target.value)}
            placeholder="Bergen"
            className="mt-1 block w-full rounded-md border-slate-300 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700">
            Min confidence ({Math.round(minConf * 100)}%)
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minConf}
            onChange={(e) => setMinConf(parseFloat(e.target.value))}
            className="mt-2 block w-full"
          />
        </div>
        <div className="flex items-end">
          <button
            type="button"
            onClick={fetchRows}
            disabled={loading}
            className="w-full rounded-md bg-slate-700 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:bg-slate-300"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </section>

      {/* Bulk toolbar */}
      <section className="mb-4 flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
        <div className="text-sm text-emerald-900">
          Bulk-approve all rows in current filter at &gt;=
        </div>
        <select
          value={bulkThreshold}
          onChange={(e) => setBulkThreshold(parseFloat(e.target.value))}
          className="rounded-md border-emerald-300 text-sm"
        >
          <option value={0.95}>95%</option>
          <option value={0.9}>90%</option>
          <option value={0.85}>85%</option>
          <option value={0.8}>80%</option>
        </select>
        <button
          type="button"
          onClick={handleBulkApprove}
          disabled={bulkBusy || status !== "pending"}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {bulkBusy ? "Approving…" : "Bulk approve"}
        </button>
        {status !== "pending" && (
          <span className="text-xs text-slate-500">
            (switch to status=pending to enable)
          </span>
        )}
      </section>

      {toast && (
        <div className="mb-3 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-sm text-emerald-800">
          {toast}{" "}
          <button
            type="button"
            onClick={() => setToast(null)}
            className="ml-2 text-xs text-emerald-700 underline"
          >
            dismiss
          </button>
        </div>
      )}
      {error && (
        <div className="mb-3 rounded-md border border-rose-200 bg-rose-50 p-2 text-sm text-rose-800">
          {error}{" "}
          <button
            type="button"
            onClick={() => setError(null)}
            className="ml-2 text-xs text-rose-700 underline"
          >
            dismiss
          </button>
        </div>
      )}

      {/* Table */}
      <section className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2 text-left">Muni</th>
              <th className="px-3 py-2 text-left">Zone</th>
              <th className="px-3 py-2 text-right">Parcels</th>
              <th className="px-3 py-2 text-left">SS</th>
              <th className="px-3 py-2 text-left">MW</th>
              <th className="px-3 py-2 text-left">LI</th>
              <th className="px-3 py-2 text-left">LGC</th>
              <th className="px-3 py-2 text-right">Conf</th>
              <th className="px-3 py-2 text-left">Citations</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={10} className="p-8 text-center text-sm text-slate-500">
                  No rows match the current filter.
                </td>
              </tr>
            )}
            {rows.map((r) => {
              const busy = busyRowIds.has(r.id);
              return (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2">
                    <div className="text-sm text-slate-900">
                      {r.municipality ?? r.jurisdiction_name}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {r.county ?? "—"} · {r.state}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-mono text-xs text-slate-900">
                      {r.zone_code}
                    </div>
                    {r.zone_name && (
                      <div className="text-[11px] text-slate-500">
                        {r.zone_name}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {r.parcel_count.toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <PermissionPill value={r.self_storage} />
                  </td>
                  <td className="px-3 py-2">
                    <PermissionPill value={r.mini_warehouse} />
                  </td>
                  <td className="px-3 py-2">
                    <PermissionPill value={r.light_industrial} />
                  </td>
                  <td className="px-3 py-2">
                    <PermissionPill value={r.luxury_garage_condo} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <ConfidenceBadge value={r.confidence} />
                  </td>
                  <td className="px-3 py-2">
                    <CitationsCell citations={r.citations} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    {status === "pending" ? (
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => handleApprove(r)}
                          disabled={busy}
                          className="rounded bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:bg-slate-300"
                        >
                          {busy ? "…" : "Approve"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleReject(r)}
                          disabled={busy}
                          className="rounded border border-rose-300 bg-white px-2 py-1 text-xs font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">approved</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </main>
  );
}
