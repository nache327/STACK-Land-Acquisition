import { TIERS, tierTone, type CoverageTier } from "@/lib/admin/tier";

const TONE_CLASSES: Record<ReturnType<typeof tierTone>, string> = {
  rose: "bg-rose-50 text-rose-800 border-rose-200",
  amber: "bg-amber-50 text-amber-800 border-amber-200",
  sky: "bg-sky-50 text-sky-800 border-sky-200",
  indigo: "bg-indigo-50 text-indigo-800 border-indigo-200",
  emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
  slate: "bg-slate-100 text-slate-700 border-slate-200",
};

interface Props {
  tier: CoverageTier;
  size?: "sm" | "md";
}

export function CoverageTierPill({ tier, size = "sm" }: Props) {
  const tone = tierTone(tier);
  const sizeClass =
    size === "md" ? "text-xs px-2.5 py-1" : "text-[11px] px-2 py-0.5";
  return (
    <span
      title={TIERS[tier].stage}
      className={[
        "inline-flex items-center gap-1 rounded-full border font-medium",
        sizeClass,
        TONE_CLASSES[tone],
      ].join(" ")}
    >
      <span className="font-mono">{tier}</span>
      <span>{TIERS[tier].label}</span>
    </span>
  );
}
