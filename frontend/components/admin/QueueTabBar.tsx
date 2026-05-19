"use client";

export interface QueueTab {
  key: string;
  label: string;
  count?: number | null;
  hint?: string;
}

interface Props {
  tabs: QueueTab[];
  active: string;
  onSelect: (key: string) => void;
}

export function QueueTabBar({ tabs, active, onSelect }: Props) {
  return (
    <nav
      role="tablist"
      aria-label="Operator queues"
      className="flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-white p-1"
    >
      {tabs.map((t) => {
        const isActive = t.key === active;
        return (
          <button
            key={t.key}
            role="tab"
            aria-selected={isActive}
            type="button"
            onClick={() => onSelect(t.key)}
            title={t.hint}
            className={[
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              isActive
                ? "bg-slate-900 text-white"
                : "text-slate-600 hover:bg-slate-50",
            ].join(" ")}
          >
            <span>{t.label}</span>
            {t.count != null && (
              <span
                className={[
                  "rounded-full px-1.5 py-0.5 font-mono text-[10px]",
                  isActive
                    ? "bg-white/20 text-white"
                    : "bg-slate-100 text-slate-600",
                ].join(" ")}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
