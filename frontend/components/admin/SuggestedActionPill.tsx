import {
  suggestionTone,
  type SuggestedAction,
} from "@/lib/admin/suggestAction";

const TONE_CLASSES = {
  emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
  rose: "bg-rose-50 text-rose-800 border-rose-200",
  indigo: "bg-indigo-50 text-indigo-800 border-indigo-200",
  slate: "bg-slate-50 text-slate-500 border-slate-200",
};

const LABEL: Record<SuggestedAction["action"], string> = {
  verify: "verify",
  reject: "reject",
  needs_review: "needs review",
  unverify: "unverify",
  review: "review",
};

interface Props {
  suggestion: SuggestedAction;
  /** When true the dot indicating confidence level is visible. */
  showConfidence?: boolean;
}

export function SuggestedActionPill({
  suggestion,
  showConfidence = true,
}: Props) {
  const tone = suggestionTone(suggestion);
  return (
    <span
      title={suggestion.reason}
      className={[
        "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
        TONE_CLASSES[tone],
      ].join(" ")}
    >
      {showConfidence && (
        <span
          aria-hidden="true"
          className={[
            "inline-block h-1.5 w-1.5 rounded-full",
            suggestion.confidence === "high"
              ? "bg-current opacity-100"
              : suggestion.confidence === "medium"
                ? "bg-current opacity-60"
                : "bg-current opacity-30",
          ].join(" ")}
        />
      )}
      {LABEL[suggestion.action]}
    </span>
  );
}
