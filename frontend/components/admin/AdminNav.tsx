"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS: { href: string; label: string; status?: "ready" | "soon" }[] = [
  { href: "/admin/ops", label: "Ops", status: "ready" },
  { href: "/admin/municipalities", label: "Municipalities", status: "ready" },
  { href: "/admin/sources", label: "Sources", status: "ready" },
  { href: "/admin/coverage", label: "Coverage", status: "ready" },
  { href: "/admin/queue", label: "Queue", status: "ready" },
  { href: "/admin/stale", label: "Stale", status: "ready" },
  { href: "/admin/jobs", label: "Jobs", status: "ready" },
  { href: "/admin/listings", label: "Listings", status: "ready" },
];

export function AdminNav() {
  const pathname = usePathname() ?? "";
  return (
    <nav className="flex flex-col gap-0.5 p-3 text-sm">
      <div className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Operator
      </div>
      {ITEMS.map((item) => {
        const active =
          pathname === item.href || pathname.startsWith(item.href + "/");
        const isSoon = item.status === "soon";
        return (
          <Link
            key={item.href}
            href={item.href}
            className={[
              "flex items-center justify-between rounded-md px-2 py-1.5",
              active
                ? "bg-slate-900 text-white"
                : "text-slate-700 hover:bg-slate-100",
            ].join(" ")}
          >
            <span>{item.label}</span>
            {isSoon && !active && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                soon
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
