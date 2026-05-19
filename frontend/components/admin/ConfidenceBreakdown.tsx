interface Props {
  breakdown: Record<string, number> | null;
  reasons?: string[] | null;
}

const HUMAN_LABELS: Record<string, string> = {
  name_match: "Name match",
  geometry_polygon: "Polygon geometry",
  geometry_point: "Point geometry",
  is_zoning_layer: "Looks like zoning",
  wrong_state: "Wrong state",
  proposed_layer: "Proposed/draft layer",
  feature_count: "Feature count",
  bbox_overlap: "Bbox overlap",
  source_authoritative: "Authoritative source",
  duplicate_of_verified: "Duplicate of verified",
  in_deny_list: "On reject list",
};

function labelFor(key: string): string {
  return HUMAN_LABELS[key] ?? key.replace(/_/g, " ");
}

export function ConfidenceBreakdown({ breakdown, reasons }: Props) {
  const entries = Object.entries(breakdown ?? {}).filter(
    ([, v]) => Number.isFinite(v) && v !== 0,
  );
  entries.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const max = entries.reduce((m, [, v]) => Math.max(m, Math.abs(v)), 1);

  return (
    <div className="space-y-3">
      <div data-testid="confidence-breakdown">
        {entries.length === 0 ? (
          <p className="text-xs italic text-slate-400">
            No breakdown captured for this row.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {entries.map(([key, delta]) => {
              const positive = delta > 0;
              const width = `${Math.min(100, (Math.abs(delta) / max) * 100)}%`;
              return (
                <li
                  key={key}
                  className="grid grid-cols-[160px_1fr_44px] items-center gap-2 text-xs"
                >
                  <span className="truncate text-slate-700" title={key}>
                    {labelFor(key)}
                  </span>
                  <span className="relative h-2 overflow-hidden rounded-full bg-slate-100">
                    <span
                      className={[
                        "absolute top-0 h-full rounded-full",
                        positive ? "bg-emerald-500 left-1/2" : "bg-rose-500 right-1/2",
                      ].join(" ")}
                      style={{ width }}
                    />
                    <span className="absolute left-1/2 top-0 h-full w-px bg-slate-300" />
                  </span>
                  <span
                    className={[
                      "text-right font-mono tabular-nums",
                      positive ? "text-emerald-700" : "text-rose-700",
                    ].join(" ")}
                  >
                    {positive ? "+" : ""}
                    {delta}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {reasons && reasons.length > 0 && (
        <div className="space-y-1">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Reasons
          </div>
          <ul className="space-y-0.5 text-xs text-slate-600">
            {reasons.map((r, i) => (
              <li key={i} className="leading-snug">
                • {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
