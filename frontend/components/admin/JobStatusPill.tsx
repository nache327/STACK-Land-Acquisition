/** Per-status tone for job-status pills. Job status enum mirrors the
 *  backend's `JobStatus` (schemas.ts JobStatusSchema). */

const TONE: Record<string, string> = {
  // terminal · success
  ready: "bg-emerald-50 text-emerald-800 border-emerald-200",
  // terminal · failure
  failed: "bg-rose-50 text-rose-800 border-rose-200",
  // terminal · operator stopped
  cancelled: "bg-slate-100 text-slate-600 border-slate-200",
  // pre-run
  pending: "bg-slate-50 text-slate-600 border-slate-200",
  queued: "bg-slate-50 text-slate-600 border-slate-200",
  // active phases
  running: "bg-sky-50 text-sky-800 border-sky-200",
  retrying: "bg-amber-50 text-amber-800 border-amber-200",
  discovering_layers: "bg-sky-50 text-sky-800 border-sky-200",
  downloading_parcels: "bg-sky-50 text-sky-800 border-sky-200",
  ingesting_parcels: "bg-sky-50 text-sky-800 border-sky-200",
  downloading_zoning: "bg-sky-50 text-sky-800 border-sky-200",
  pending_zoning: "bg-amber-50 text-amber-800 border-amber-200",
  parsing_ordinance: "bg-sky-50 text-sky-800 border-sky-200",
  running_overlays: "bg-sky-50 text-sky-800 border-sky-200",
};

interface Props {
  status: string;
}

export function JobStatusPill({ status }: Props) {
  const tone = TONE[status] ?? TONE.pending;
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
        tone,
      ].join(" ")}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
