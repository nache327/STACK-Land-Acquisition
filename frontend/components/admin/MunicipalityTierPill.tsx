import {
  MUNICIPALITY_TIERS,
  tierTone,
  type MunicipalityTier,
} from "@/lib/admin/municipalityOps";

const TONE_CLASSES: Record<ReturnType<typeof tierTone>, string> = {
  rose: "bg-rose-50 text-rose-800 border-rose-200",
  amber: "bg-amber-50 text-amber-800 border-amber-200",
  sky: "bg-sky-50 text-sky-800 border-sky-200",
  indigo: "bg-indigo-50 text-indigo-800 border-indigo-200",
  emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
  slate: "bg-slate-100 text-slate-700 border-slate-200",
};

interface Props {
  tier: MunicipalityTier;
  size?: "sm" | "md";
}

export function MunicipalityTierPill({ tier, size = "sm" }: Props) {
  const tone = tierTone(tier);
  const sizeClass =
    size === "md" ? "text-xs px-2.5 py-1" : "text-[11px] px-2 py-0.5";
  return (
    <span
      title={MUNICIPALITY_TIERS[tier].stage}
      className={[
        "inline-flex items-center gap-1 rounded-full border font-medium",
        sizeClass,
        TONE_CLASSES[tone],
      ].join(" ")}
    >
      <span className="font-mono">{tier}</span>
      <span>{MUNICIPALITY_TIERS[tier].label}</span>
    </span>
  );
}

/** Horizontal step-bar visualization of where the town is in the
 *  M0 → M6 onboarding journey. */
const STEPS: MunicipalityTier[] = ["M0", "M1", "M2", "M3", "M4", "M5", "M6"];

export function MunicipalityProgressionBar({ tier }: { tier: MunicipalityTier }) {
  const currentIdx = STEPS.indexOf(tier);
  return (
    <div
      role="img"
      aria-label={`Onboarding tier ${tier}`}
      className="flex items-center gap-1"
    >
      {STEPS.map((s, i) => {
        const isPast = i < currentIdx;
        const isCurrent = i === currentIdx;
        const tone = tierTone(s);
        const baseClass = isCurrent
          ? TONE_CLASSES[tone]
          : isPast
            ? "bg-emerald-100 text-emerald-700 border-emerald-200"
            : "bg-slate-50 text-slate-400 border-slate-200";
        return (
          <span
            key={s}
            title={`${s} · ${MUNICIPALITY_TIERS[s].label}`}
            className={[
              "inline-flex h-5 min-w-[1.5rem] items-center justify-center rounded-md border font-mono text-[10px]",
              baseClass,
              isCurrent ? "font-semibold" : "",
            ].join(" ")}
          >
            {s}
          </span>
        );
      })}
    </div>
  );
}
