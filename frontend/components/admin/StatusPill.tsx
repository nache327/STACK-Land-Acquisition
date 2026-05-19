import type { SpatialCheckVerdict } from "@/lib/schemas";

type Tone =
  | "neutral"
  | "amber"
  | "emerald"
  | "rose"
  | "indigo"
  | "slate"
  | "sky";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700 border-slate-200",
  amber: "bg-amber-50 text-amber-800 border-amber-200",
  emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
  rose: "bg-rose-50 text-rose-800 border-rose-200",
  indigo: "bg-indigo-50 text-indigo-800 border-indigo-200",
  slate: "bg-slate-50 text-slate-600 border-slate-200",
  sky: "bg-sky-50 text-sky-800 border-sky-200",
};

const VALIDATION_TONE: Record<string, Tone> = {
  pending: "amber",
  verified: "emerald",
  rejected: "rose",
  needs_review: "indigo",
  token_gated: "slate",
  empty: "slate",
};

const VERDICT_TONE: Record<SpatialCheckVerdict, Tone> = {
  good: "emerald",
  partial: "amber",
  tiny: "amber",
  disjoint: "rose",
  unknown: "slate",
};

export function ValidationStatusPill({ status }: { status: string }) {
  const tone = VALIDATION_TONE[status] ?? "neutral";
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
        TONE_CLASSES[tone],
      ].join(" ")}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function VerdictPill({ verdict }: { verdict: SpatialCheckVerdict }) {
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        TONE_CLASSES[VERDICT_TONE[verdict]],
      ].join(" ")}
    >
      {verdict}
    </span>
  );
}

export function ConfidencePill({ score }: { score: number | null }) {
  if (score == null) {
    return (
      <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px] text-slate-500">
        —
      </span>
    );
  }
  const tone: Tone =
    score >= 70 ? "emerald" : score >= 50 ? "sky" : score >= 30 ? "amber" : "rose";
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[11px]",
        TONE_CLASSES[tone],
      ].join(" ")}
    >
      {score}
    </span>
  );
}
