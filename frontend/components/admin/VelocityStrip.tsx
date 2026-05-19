interface Stat {
  label: string;
  value: number | string;
  tone: "emerald" | "rose" | "amber" | "slate" | "sky";
  hint?: string;
}

const TONE_CLASSES: Record<Stat["tone"], string> = {
  emerald: "text-emerald-700",
  rose: "text-rose-700",
  amber: "text-amber-700",
  slate: "text-slate-700",
  sky: "text-sky-700",
};

interface Props {
  windowLabel: string;
  stats: Stat[];
}

export function VelocityStrip({ windowLabel, stats }: Props) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
        Review velocity · last {windowLabel}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-6 gap-y-2">
        {stats.map((s) => (
          <div key={s.label} title={s.hint} className="min-w-[80px]">
            <div className="text-[10px] uppercase tracking-wide text-slate-500">
              {s.label}
            </div>
            <div
              className={[
                "font-mono text-xl font-semibold",
                TONE_CLASSES[s.tone],
              ].join(" ")}
            >
              {s.value}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
