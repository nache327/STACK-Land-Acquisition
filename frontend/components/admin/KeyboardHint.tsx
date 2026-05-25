interface Props {
  keys: string[];
  /** When true the kbd cluster is rendered inline (no leading gap). */
  inline?: boolean;
}

export function KeyboardHint({ keys, inline = false }: Props) {
  return (
    <span
      className={[
        "inline-flex items-center gap-0.5",
        inline ? "" : "ml-1",
      ].join(" ")}
      aria-hidden="true"
    >
      {keys.map((k) => (
        <kbd
          key={k}
          className="inline-flex h-4 min-w-[1rem] items-center justify-center rounded border border-slate-300 bg-slate-50 px-1 text-[10px] font-mono text-slate-600"
        >
          {k}
        </kbd>
      ))}
    </span>
  );
}
