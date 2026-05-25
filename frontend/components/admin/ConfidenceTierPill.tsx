import {
  deriveConfidenceTier,
  type ConfidenceTier,
} from "@/lib/admin/confidenceTier";

const TIER_CLASSES: Record<ConfidenceTier, string> = {
  strong: "bg-emerald-50 text-emerald-800 border-emerald-200",
  decent: "bg-sky-50 text-sky-800 border-sky-200",
  weak: "bg-amber-50 text-amber-800 border-amber-200",
  junk: "bg-rose-50 text-rose-800 border-rose-200",
  unknown: "bg-slate-50 text-slate-500 border-slate-200",
};

interface Props {
  score: number | null | undefined;
  /** Show the raw number alongside the tier label. Off by default to
   *  compress the visual surface. */
  showNumber?: boolean;
}

export function ConfidenceTierPill({ score, showNumber = false }: Props) {
  const t = deriveConfidenceTier(score);
  return (
    <span
      title={
        t.score != null
          ? `${t.label} · confidence_score=${t.score}`
          : "no score recorded"
      }
      className={[
        "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
        TIER_CLASSES[t.tier],
      ].join(" ")}
    >
      <span>{t.label}</span>
      {showNumber && t.score != null && (
        <span className="font-mono opacity-70">{t.score}</span>
      )}
    </span>
  );
}
