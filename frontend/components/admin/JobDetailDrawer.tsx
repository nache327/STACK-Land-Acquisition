"use client";

import { useAdminJob } from "@/hooks/useAdminJobs";
import { JobActionButtons } from "./JobActionButtons";
import { JobStatusPill } from "./JobStatusPill";

interface Props {
  jobId: string;
  onClose: () => void;
}

export function JobDetailDrawer({ jobId, onClose }: Props) {
  const query = useAdminJob(jobId);

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-[32rem] flex-col bg-white shadow-2xl"
        role="dialog"
        aria-label="Job detail"
      >
        <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
              Job
            </p>
            <h2 className="mt-0.5 truncate font-mono text-xs text-slate-700">
              {jobId}
            </h2>
            {query.data && (
              <div className="mt-1 flex items-center gap-2">
                <JobStatusPill status={query.data.job.status} />
                {query.data.job.jurisdiction_input && (
                  <span className="text-xs text-slate-600">
                    {query.data.job.jurisdiction_input}
                  </span>
                )}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close drawer"
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4.293 4.293a1 1 0 011.414 0L8 6.586l2.293-2.293a1 1 0 111.414 1.414L9.414 8l2.293 2.293a1 1 0 01-1.414 1.414L8 9.414l-2.293 2.293a1 1 0 01-1.414-1.414L6.586 8 4.293 5.707a1 1 0 010-1.414z" />
            </svg>
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5 text-sm">
          {query.isPending && (
            <p className="text-[11px] italic text-slate-400">Loading job…</p>
          )}
          {query.isError && (
            <p className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
              {(query.error as Error)?.message ?? "Failed to load job."}
            </p>
          )}
          {query.data && (
            <>
              <section>
                <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  Metadata
                </h3>
                <dl className="mt-2 grid grid-cols-[120px_1fr] gap-x-3 gap-y-1 text-[11px]">
                  <dt className="text-slate-400">jurisdiction_id</dt>
                  <dd className="break-all font-mono text-slate-700">
                    {query.data.job.jurisdiction_id ?? "—"}
                  </dd>
                  <dt className="text-slate-400">ordinance_url</dt>
                  <dd className="break-all text-slate-700">
                    {query.data.job.ordinance_url ?? "—"}
                  </dd>
                  <dt className="text-slate-400">target_uses</dt>
                  <dd className="text-slate-700">
                    {query.data.job.target_uses?.join(", ") ?? "—"}
                  </dd>
                  <dt className="text-slate-400">queued_at</dt>
                  <dd className="font-mono text-slate-700">
                    {fmtTs(query.data.job.queued_at)}
                  </dd>
                  <dt className="text-slate-400">started_at</dt>
                  <dd className="font-mono text-slate-700">
                    {fmtTs(query.data.job.started_at)}
                  </dd>
                  <dt className="text-slate-400">finished_at</dt>
                  <dd className="font-mono text-slate-700">
                    {fmtTs(query.data.job.finished_at)}
                  </dd>
                  <dt className="text-slate-400">cancel_requested_at</dt>
                  <dd className="font-mono text-slate-700">
                    {fmtTs(query.data.job.cancel_requested_at)}
                  </dd>
                  <dt className="text-slate-400">locked_by</dt>
                  <dd className="font-mono text-slate-700">
                    {query.data.job.locked_by ?? "—"}
                  </dd>
                  <dt className="text-slate-400">locked_at</dt>
                  <dd className="font-mono text-slate-700">
                    {fmtTs(query.data.job.locked_at)}
                  </dd>
                  <dt className="text-slate-400">attempts</dt>
                  <dd className="font-mono text-slate-700">
                    {query.data.job.attempts ?? "—"}
                  </dd>
                  <dt className="text-slate-400">dedupe_key</dt>
                  <dd className="break-all font-mono text-slate-500">
                    {query.data.job.dedupe_key ?? "—"}
                  </dd>
                </dl>
              </section>

              {query.data.job.error_message && (
                <section>
                  <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    Error
                  </h3>
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-md border border-rose-200 bg-rose-50 px-2 py-1 font-mono text-[11px] text-rose-800">
                    {query.data.job.error_message}
                  </pre>
                </section>
              )}

              <section>
                <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  Steps ({query.data.steps.length})
                </h3>
                {query.data.steps.length === 0 ? (
                  <p className="text-[11px] italic text-slate-400">
                    No steps recorded yet.
                  </p>
                ) : (
                  <ol className="space-y-1.5">
                    {query.data.steps.map((s) => (
                      <li
                        key={s.id}
                        className="rounded-md border border-slate-200 bg-white p-2 text-[11px]"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium text-slate-800">
                            {s.step}
                            <span className="ml-1 text-slate-400">
                              attempt {s.attempt}
                            </span>
                          </span>
                          <span
                            className={[
                              "rounded-full px-1.5 py-0.5 text-[10px] font-medium",
                              stepStatusTone(s.status),
                            ].join(" ")}
                          >
                            {s.status}
                          </span>
                        </div>
                        <div className="mt-0.5 grid grid-cols-3 gap-2 font-mono text-[10px] text-slate-500">
                          <span>start: {fmtTs(s.started_at, true)}</span>
                          <span>end: {fmtTs(s.finished_at, true)}</span>
                          <span>
                            {s.duration_ms != null
                              ? `${(s.duration_ms / 1000).toFixed(1)}s`
                              : "—"}
                          </span>
                        </div>
                        {s.error && (
                          <p className="mt-1 rounded-md border border-rose-200 bg-rose-50 px-1.5 py-1 font-mono text-[10px] text-rose-700">
                            {s.error}
                          </p>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              {query.data.artifacts.length > 0 && (
                <section>
                  <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    Artifacts ({query.data.artifacts.length})
                  </h3>
                  <ul className="space-y-1 text-[11px]">
                    {query.data.artifacts.map((a) => (
                      <li
                        key={a.id}
                        className="rounded-md border border-slate-200 bg-white p-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-slate-700">
                            {a.step} · {a.artifact_type}
                          </span>
                          <span className="font-mono text-[10px] text-slate-400">
                            {fmtTs(a.created_at, true)}
                          </span>
                        </div>
                        {a.storage_uri && (
                          <p className="mt-0.5 break-all font-mono text-[10px] text-sky-700">
                            {a.storage_uri}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>

        <div className="space-y-2 border-t border-slate-200 p-4">
          {query.data && <JobActionButtons job={query.data.job} />}
        </div>
      </aside>
    </>
  );
}

function fmtTs(value: string | null | undefined, short = false): string {
  if (!value) return "—";
  return short ? value.slice(11, 19) : value.slice(0, 19).replace("T", " ");
}

function stepStatusTone(status: string): string {
  switch (status) {
    case "completed":
    case "succeeded":
    case "ready":
      return "bg-emerald-50 text-emerald-800 border border-emerald-200";
    case "failed":
    case "errored":
      return "bg-rose-50 text-rose-800 border border-rose-200";
    case "running":
    case "in_progress":
      return "bg-sky-50 text-sky-800 border border-sky-200";
    case "cancelled":
      return "bg-slate-100 text-slate-600 border border-slate-200";
    default:
      return "bg-amber-50 text-amber-800 border border-amber-200";
  }
}
