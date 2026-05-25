const TONE_CLASSES: Record<string, string> = {
  operational: "bg-emerald-50 text-emerald-800 border-emerald-200",
  partial: "bg-sky-50 text-sky-800 border-sky-200",
  degraded: "bg-amber-50 text-amber-800 border-amber-200",
  broken: "bg-rose-50 text-rose-800 border-rose-200",
  empty: "bg-slate-100 text-slate-600 border-slate-200",
};

const LABEL: Record<string, string> = {
  operational: "Operational",
  partial: "Partial",
  degraded: "Degraded",
  broken: "Broken",
  empty: "Empty",
};

interface Props {
  band: string;
  size?: "sm" | "md";
}

export function TrustworthinessPill({ band, size = "sm" }: Props) {
  const tone = TONE_CLASSES[band] ?? TONE_CLASSES.empty;
  const sizeClass =
    size === "md" ? "text-xs px-2.5 py-1" : "text-[11px] px-2 py-0.5";
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border font-medium capitalize",
        sizeClass,
        tone,
      ].join(" ")}
    >
      {LABEL[band] ?? band}
    </span>
  );
}
