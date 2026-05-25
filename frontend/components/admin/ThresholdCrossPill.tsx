interface Props {
  direction: "up" | "down" | null;
  threshold?: number;
}

export function ThresholdCrossPill({ direction, threshold = 70 }: Props) {
  if (direction === null) {
    return (
      <span className="text-[10px] text-slate-400" aria-label="no crossing">
        —
      </span>
    );
  }
  if (direction === "up") {
    return (
      <span
        title={`Crossed up over ${threshold} — gained high-confidence status`}
        className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800"
      >
        ↑ over {threshold}
      </span>
    );
  }
  return (
    <span
      title={`Crossed down under ${threshold} — dropped out of the high-confidence queue`}
      className="inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-800"
    >
      ↓ under {threshold}
    </span>
  );
}
