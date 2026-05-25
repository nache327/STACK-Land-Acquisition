import { labelBlockingGap } from "@/lib/admin/tier";

interface Props {
  gaps: string[] | null | undefined;
}

export function BlockingGapsPanel({ gaps }: Props) {
  if (!gaps || gaps.length === 0) {
    return (
      <p className="text-[11px] italic text-emerald-700">
        No blocking gaps — jurisdiction passes the audit.
      </p>
    );
  }
  return (
    <ul className="flex flex-wrap gap-1.5">
      {gaps.map((g) => (
        <li
          key={g}
          title={g}
          className="inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-800"
        >
          {labelBlockingGap(g)}
        </li>
      ))}
    </ul>
  );
}
