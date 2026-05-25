import type { MunicipalityBlocker } from "@/lib/admin/municipalityOps";

const TONE_CLASSES = {
  block: "bg-rose-50 text-rose-800 border-rose-200",
  warn: "bg-amber-50 text-amber-800 border-amber-200",
  info: "bg-slate-100 text-slate-700 border-slate-200",
};

interface Props {
  blockers: MunicipalityBlocker[];
  /** When true the list reads as a single row of small chips. False
   *  renders one chip per line for the drilldown layout. */
  inline?: boolean;
}

export function MunicipalityBlockerList({ blockers, inline = false }: Props) {
  if (blockers.length === 0) {
    return (
      <span className="text-[10px] italic text-emerald-700">
        No blockers — town is healthy
      </span>
    );
  }
  return (
    <ul
      className={[
        inline ? "flex flex-wrap gap-1" : "flex flex-col gap-1",
      ].join(" ")}
    >
      {blockers.map((b) => (
        <li
          key={b.key}
          title={b.detail}
          className={[
            "inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
            TONE_CLASSES[b.severity],
          ].join(" ")}
        >
          {b.label}
        </li>
      ))}
    </ul>
  );
}
