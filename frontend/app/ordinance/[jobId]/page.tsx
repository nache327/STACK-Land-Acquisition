"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useJobPoller } from "@/hooks/useJobPoller";
import { ZoneMatrix } from "@/components/ZoneMatrix";
import { ZoneOverrideDrawer } from "@/components/ZoneOverrideDrawer";
import type { ZoneRow } from "@/lib/schemas";
import type { UseKey } from "@/components/ZoneOverrideDrawer";

interface Props {
  params: { jobId: string };
}

export default function OrdinancePage({ params }: Props) {
  const { jobId } = params;
  const { data: job } = useJobPoller(jobId);
  const jurisdictionId = job?.jurisdiction_id ?? null;

  const queryClient = useQueryClient();
  const [ordinanceUrl, setOrdinanceUrl] = useState("");
  const [parseMsg, setParseMsg] = useState<string | null>(null);

  // Override drawer state
  const [overrideTarget, setOverrideTarget] = useState<{
    zone: ZoneRow;
    useKey: UseKey;
  } | null>(null);

  // ── Fetch zone matrix ─────────────────────────────────────────────────────
  const { data: matrix, isLoading: matrixLoading } = useQuery({
    queryKey: ["zone-matrix", jurisdictionId],
    queryFn: () => api.getZoneMatrix(jurisdictionId!),
    enabled: !!jurisdictionId,
    staleTime: 30_000,
  });

  // ── Trigger ordinance parse ───────────────────────────────────────────────
  const parseMutation = useMutation({
    mutationFn: () =>
      api.triggerParse(jurisdictionId!, ordinanceUrl || undefined),
    onSuccess: (data) => {
      setParseMsg(data.message);
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["zone-matrix", jurisdictionId] });
        setParseMsg(null);
      }, 5000);
    },
    onError: (err: Error) => {
      setParseMsg(`Error: ${err.message}`);
    },
  });

  // ── Handlers ──────────────────────────────────────────────────────────────
  function handleCellClick(zone: ZoneRow, useKey: UseKey) {
    if (!jurisdictionId) return;
    setOverrideTarget({ zone, useKey });
  }

  function handleDrawerSaved() {
    setOverrideTarget(null);
  }

  // ── Stats ─────────────────────────────────────────────────────────────────
  const reviewedCount = matrix?.zones.filter((z) => z.human_reviewed).length ?? 0;
  const totalCount = matrix?.zones.length ?? 0;

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      {/* Top bar */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="text-sm font-semibold text-slate-900 hover:text-emerald-600"
          >
            Zoning Finder
          </Link>
          <span className="text-slate-300">/</span>
          <Link
            href={`/dashboard/${jobId}`}
            className="text-sm text-slate-500 hover:text-slate-900"
          >
            Dashboard
          </Link>
          <span className="text-slate-300">/</span>
          <span className="text-sm text-slate-500">Zone Matrix</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-400">
          {totalCount > 0 && (
            <>
              <span>{totalCount} zones</span>
              {reviewedCount > 0 && (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-medium text-emerald-700">
                  {reviewedCount} reviewed
                </span>
              )}
            </>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 space-y-6 p-6">
        {/* Page title */}
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Zone Use Matrix</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Which uses are permitted in each zoning district — parsed from the
            ordinance by Claude. Click any cell to review or override.
          </p>
        </div>

        {/* Parse trigger panel */}
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-700">
            Parse / Re-parse Ordinance
          </h2>
          <div className="flex gap-2">
            <input
              type="url"
              value={ordinanceUrl}
              onChange={(e) => setOrdinanceUrl(e.target.value)}
              placeholder="Municode / eCode360 / city website URL (optional — uses stored URL if blank)"
              className="flex-1 rounded-md border border-slate-200 px-3 py-2 text-sm placeholder-slate-400 focus:border-emerald-500 focus:outline-none"
            />
            <button
              onClick={() => parseMutation.mutate()}
              disabled={!jurisdictionId || parseMutation.isPending}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {parseMutation.isPending ? "Starting…" : "Parse"}
            </button>
          </div>

          {parseMsg && (
            <p
              className={[
                "mt-2 text-xs",
                parseMsg.startsWith("Error") ? "text-red-600" : "text-emerald-700",
              ].join(" ")}
            >
              {parseMsg}
            </p>
          )}

          <p className="mt-2 text-xs text-slate-400">
            Parsing runs in the background (~30 s). Requires{" "}
            <code className="rounded bg-slate-100 px-1 font-mono">
              ANTHROPIC_API_KEY
            </code>{" "}
            to be set in the backend.
          </p>
        </div>

        {/* Matrix table */}
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          {!jurisdictionId ? (
            <p className="text-sm text-slate-400">Waiting for job to load…</p>
          ) : matrixLoading ? (
            <p className="text-sm text-slate-400">Loading zone matrix…</p>
          ) : !matrix?.zones?.length ? (
            <div className="space-y-2">
              <p className="text-sm text-slate-600">
                No zone matrix yet for this jurisdiction.
              </p>
              <p className="text-xs text-slate-400">
                Paste the ordinance URL above and click Parse, or wait for the
                pipeline to finish if it was just submitted.
              </p>
            </div>
          ) : (
            <ZoneMatrix
              zones={matrix.zones}
              onCellClick={handleCellClick}
            />
          )}
        </div>

        {/* Parser warnings */}
        {matrix?.parser_warnings && matrix.parser_warnings.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
            <p className="text-xs font-semibold text-amber-800">
              Parser warnings
            </p>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              {matrix.parser_warnings.map((w, i) => (
                <li key={i} className="text-xs text-amber-700">
                  {w}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Unclassified zones */}
        {matrix?.unknown_zones && matrix.unknown_zones.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold text-slate-600">
              Zones not classified ({matrix.unknown_zones.length})
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {matrix.unknown_zones.join(", ")}
            </p>
          </div>
        )}
      </main>

      {/* Override drawer — rendered at the page level so it can overlay everything */}
      {overrideTarget && jurisdictionId && (
        <ZoneOverrideDrawer
          zone={overrideTarget.zone}
          useKey={overrideTarget.useKey}
          jurisdictionId={jurisdictionId}
          onClose={() => setOverrideTarget(null)}
          onSaved={handleDrawerSaved}
        />
      )}
    </div>
  );
}
