import type { RescoreSummary } from "@/lib/schemas";

interface Props {
  summary: RescoreSummary;
  scanned: number;
  dryRun: boolean;
}

export function RescoreSummaryStrip({ summary, scanned, dryRun }: Props) {
  const queue70Net =
    summary.newly_above_threshold_70 - summary.newly_below_threshold_70;
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
          Rescore summary · scanned {scanned}
        </div>
        <span
          className={[
            "rounded-full px-2 py-0.5 text-[10px] font-medium",
            dryRun
              ? "bg-slate-100 text-slate-700"
              : "bg-emerald-100 text-emerald-800",
          ].join(" ")}
        >
          {dryRun ? "dry-run · no DB writes" : "applied · DB written"}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-4">
        <Stat
          label="Changed"
          value={summary.changed}
          tone={summary.changed > 0 ? "slate" : "muted"}
          sub={`${summary.no_change} unchanged`}
        />
        <Stat
          label="Score Δ"
          value={
            <>
              <span className="text-rose-700">{summary.score_decreased}↓</span>{" "}
              <span className="text-emerald-700">
                {summary.score_increased}↑
              </span>
            </>
          }
          tone="slate"
        />
        <Stat
          label="Queue ≥70 net"
          value={`${queue70Net >= 0 ? "+" : ""}${queue70Net}`}
          tone={
            queue70Net < 0 ? "rose" : queue70Net > 0 ? "emerald" : "muted"
          }
          sub={`${summary.newly_below_threshold_70}↓ · ${summary.newly_above_threshold_70}↑`}
          hint="Net change in the >=70 high-confidence triage queue. Negative = queue shrinks."
        />
        <Stat
          label="Newly disjoint"
          value={summary.live_verdict_disjoint}
          tone={summary.live_verdict_disjoint > 0 ? "rose" : "muted"}
          hint="Rows where the live probe now classifies the layer as bbox-disjoint."
        />
        <Stat
          label="Applied"
          value={summary.applied}
          tone={summary.applied > 0 ? "emerald" : "muted"}
        />
        <Stat
          label="Immutable skipped"
          value={summary.skipped_immutable}
          tone={summary.skipped_immutable > 0 ? "amber" : "muted"}
          hint="Verified or rejected rows that would have changed but were preserved — operator decisions are durable."
        />
        <div className="md:col-span-2">
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Delta distribution
          </div>
          <DeltaBuckets dist={summary.score_delta_distribution} />
        </div>
      </div>
    </section>
  );
}

function Stat({
  label,
  value,
  tone,
  sub,
  hint,
}: {
  label: string;
  value: React.ReactNode;
  tone: "rose" | "emerald" | "amber" | "slate" | "muted";
  sub?: string;
  hint?: string;
}) {
  const toneClass =
    tone === "rose"
      ? "text-rose-700"
      : tone === "emerald"
        ? "text-emerald-700"
        : tone === "amber"
          ? "text-amber-700"
          : tone === "muted"
            ? "text-slate-400"
            : "text-slate-900";
  return (
    <div title={hint}>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={["mt-0.5 font-mono text-lg font-semibold", toneClass].join(" ")}>
        {value}
      </div>
      {sub && <div className="text-[10px] text-slate-400">{sub}</div>}
    </div>
  );
}

const BUCKET_ORDER = [
  "≤-50",
  "-49..-20",
  "-19..-1",
  "0",
  "1..19",
  "20..49",
  "≥50",
];

function DeltaBuckets({ dist }: { dist: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(dist));
  return (
    <div className="mt-1 grid grid-cols-7 gap-1 text-[10px] font-mono">
      {BUCKET_ORDER.map((b) => {
        const v = dist[b] ?? 0;
        const h = Math.round((v / max) * 100);
        const isNeg = b.startsWith("-") || b.startsWith("≤-");
        return (
          <div key={b} className="text-center">
            <div className="flex h-8 items-end justify-center">
              <span
                style={{ height: `${Math.max(4, h)}%` }}
                className={[
                  "w-2 rounded-sm",
                  isNeg ? "bg-rose-500" : b === "0" ? "bg-slate-300" : "bg-emerald-500",
                ].join(" ")}
              />
            </div>
            <div className="text-slate-500">{b}</div>
            <div className="text-slate-400">{v}</div>
          </div>
        );
      })}
    </div>
  );
}
