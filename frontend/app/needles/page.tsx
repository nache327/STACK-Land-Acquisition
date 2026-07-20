"use client";

import { useEffect, useMemo, useState } from "react";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface NeedleRow {
  jurisdiction_id: string;
  jurisdiction_name: string;
  state: string | null;
  storage_needles: number;
  lgc_needles: number;
  lgc_incremental: number;
  storage_deals: number;
  lgc_deals: number;
  computed_at: string | null;
}
interface NeedleResponse {
  jurisdictions: NeedleRow[];
  totals: Omit<NeedleRow, "jurisdiction_id" | "jurisdiction_name" | "state" | "computed_at">;
  computed_at: string | null;
}

type SortKey =
  | "lgc_needles" | "storage_needles" | "lgc_incremental" | "lgc_deals" | "storage_deals" | "jurisdiction_name";

const fmt = (n: number) => n.toLocaleString();

function ago(iso: string | null): string {
  if (!iso) return "never";
  const h = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (h < 1) return "just now";
  if (h < 48) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export default function NeedlesPage() {
  const [data, setData] = useState<NeedleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("lgc_needles");

  useEffect(() => {
    fetch(`${BASE_URL}/api/needles`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const r = [...data.jurisdictions];
    r.sort((a, b) =>
      sort === "jurisdiction_name"
        ? a.jurisdiction_name.localeCompare(b.jurisdiction_name)
        : (b[sort] as number) - (a[sort] as number)
    );
    return r;
  }, [data, sort]);

  const th = (key: SortKey, label: string, right = false) => (
    <th
      onClick={() => setSort(key)}
      className={[
        "cursor-pointer select-none px-3 py-2 text-xs font-semibold uppercase tracking-wide",
        right ? "text-right" : "text-left",
        sort === key ? "text-white" : "text-slate-400 hover:text-slate-200",
      ].join(" ")}
      title="Sort"
    >
      {label}{sort === key ? " ↓" : ""}
    </th>
  );

  return (
    <main className="min-h-screen bg-[#070d1a] text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <div className="flex items-end justify-between gap-4">
          <div>
            <a href="/" className="text-sm text-slate-400 hover:text-slate-200">← ParcelLogic</a>
            <h1 className="mt-1 text-2xl font-bold tracking-tight">Needles by county</h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-400">
              Wealth-gated needles — grounded verdict, ≥1.5 ac, 10-min ring ≥ $475k home value &amp; ≥ $100k HHI.
              <span className="text-[#7ba0bf]"> Storage</span> vs the{" "}
              <span className="text-[#e0a94a]">luxury garage condo</span> lane (incremental = LGC-viable where storage isn&apos;t).
            </p>
          </div>
          {data && (
            <span className="whitespace-nowrap text-xs text-slate-500">
              snapshot {ago(data.computed_at)}
            </span>
          )}
        </div>

        {error && (
          <div className="mt-8 rounded-lg border border-amber-800/50 bg-amber-950/40 px-4 py-3 text-sm text-amber-300">
            Couldn&apos;t load needle snapshot: {error}
          </div>
        )}
        {!data && !error && <div className="mt-8 text-sm text-slate-500">Loading…</div>}
        {data && data.jurisdictions.length === 0 && (
          <div className="mt-8 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-6 text-sm text-slate-400">
            No snapshot yet. Run <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs">python scripts/precompute_needles.py</code> to populate.
          </div>
        )}

        {data && data.jurisdictions.length > 0 && (
          <>
            <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Storage needles", data.totals.storage_needles, "#7ba0bf"],
                ["LGC needles", data.totals.lgc_needles, "#e0a94a"],
                ["LGC incremental", data.totals.lgc_incremental, "#55b487"],
                ["On-needle deals (LGC)", data.totals.lgc_deals, "#e0a94a"],
              ].map(([label, val, color]) => (
                <div key={label as string} className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
                  <div className="text-xs font-medium text-slate-400">{label as string}</div>
                  <div className="mt-1 text-2xl font-bold tabular-nums" style={{ color: color as string }}>
                    {fmt(val as number)}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-800 bg-slate-900/60">
                  <tr>
                    {th("jurisdiction_name", "County / Jurisdiction")}
                    {th("storage_needles", "Storage", true)}
                    {th("lgc_needles", "LGC", true)}
                    {th("lgc_incremental", "+ Incremental", true)}
                    {th("storage_deals", "Storage deals", true)}
                    {th("lgc_deals", "LGC deals", true)}
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {rows.map((r) => (
                    <tr key={r.jurisdiction_id} className="border-b border-slate-800/60 hover:bg-slate-900/40">
                      <td className="px-3 py-2 text-slate-200">
                        {r.jurisdiction_name}
                        {r.state ? <span className="text-slate-500"> · {r.state}</span> : null}
                      </td>
                      <td className="px-3 py-2 text-right text-[#7ba0bf]">{fmt(r.storage_needles)}</td>
                      <td className="px-3 py-2 text-right font-semibold text-[#e0a94a]">{fmt(r.lgc_needles)}</td>
                      <td className="px-3 py-2 text-right text-[#55b487]">{r.lgc_incremental ? `+${fmt(r.lgc_incremental)}` : "—"}</td>
                      <td className="px-3 py-2 text-right text-slate-300">{r.storage_deals || "—"}</td>
                      <td className="px-3 py-2 text-right text-slate-300">{r.lgc_deals || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
