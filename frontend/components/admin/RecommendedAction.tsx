import Link from "next/link";
import type { RecommendedAction as RecAction } from "@/lib/admin/tier";

interface Props {
  action: RecAction;
}

export function RecommendedAction({ action }: Props) {
  const text = action.text;
  if (!action.actionable) {
    return <span className="text-[11px] text-slate-500">{text}</span>;
  }
  if (action.href) {
    return (
      <Link
        href={action.href}
        className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-slate-800"
      >
        {text} →
      </Link>
    );
  }
  return (
    <span className="rounded-md border border-slate-300 px-2 py-0.5 text-[11px] font-medium text-slate-700">
      {text}
    </span>
  );
}
