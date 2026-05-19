import type { SessionStats } from "@/lib/admin/sessionVelocity";
import { formatLatency } from "@/lib/admin/sessionVelocity";

interface Props {
  stats: SessionStats;
}

export function SessionVelocityCounter({ stats }: Props) {
  return (
    <div
      role="status"
      aria-label="session velocity"
      className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px]"
    >
      <span className="font-semibold text-slate-700">This session</span>
      <Pair label="✓ verified" value={stats.verified} tone="emerald" />
      <Pair label="✗ rejected" value={stats.rejected} tone="rose" />
      <Pair label="? needs-review" value={stats.needs_review} tone="indigo" />
      <Pair label="↺ unverified" value={stats.unverified} tone="slate" />
      <span className="ml-auto flex items-center gap-3 text-slate-500">
        <span title="Median seconds between opening a row and committing the action.">
          median {formatLatency(stats.median_latency_ms)}
        </span>
        <span title="Decisions per minute, averaged over the elapsed session.">
          {stats.decisions_per_minute != null
            ? `${stats.decisions_per_minute.toFixed(1)}/min`
            : "—/min"}
        </span>
      </span>
    </div>
  );
}

function Pair({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "emerald" | "rose" | "indigo" | "slate";
}) {
  const toneClass =
    tone === "emerald"
      ? "text-emerald-700"
      : tone === "rose"
        ? "text-rose-700"
        : tone === "indigo"
          ? "text-indigo-700"
          : "text-slate-500";
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-slate-500">{label}</span>
      <span className={["font-mono font-semibold", toneClass].join(" ")}>
        {value}
      </span>
    </span>
  );
}
