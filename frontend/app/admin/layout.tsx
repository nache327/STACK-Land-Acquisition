import Link from "next/link";
import { AdminNav } from "@/components/admin/AdminNav";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function apiHost(): { host: string; tone: "prod" | "preview" | "local" } {
  try {
    const url = new URL(API_BASE);
    const host = url.host;
    if (host.includes("localhost") || host.includes("127.0.0.1")) {
      return { host, tone: "local" };
    }
    if (host.includes("railway") || host.includes("production")) {
      return { host, tone: "prod" };
    }
    return { host, tone: "preview" };
  } catch {
    return { host: API_BASE, tone: "local" };
  }
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { host, tone } = apiHost();
  const toneClass =
    tone === "prod"
      ? "bg-rose-100 text-rose-800 border-rose-200"
      : tone === "preview"
        ? "bg-amber-100 text-amber-800 border-amber-200"
        : "bg-slate-100 text-slate-700 border-slate-200";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between px-5 py-3">
          <Link href="/admin/sources" className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">
              ParcelLogic
            </span>
            <span className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white">
              Ops
            </span>
          </Link>
          <span
            className={[
              "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-mono",
              toneClass,
            ].join(" ")}
            title="Backend API the admin UI is talking to"
          >
            <span className="font-medium uppercase">{tone}</span>
            <span className="opacity-80">{host}</span>
          </span>
        </div>
      </header>
      <div className="mx-auto flex max-w-[1400px] gap-6 px-5 py-6">
        <aside className="w-52 shrink-0 rounded-lg border border-slate-200 bg-white">
          <AdminNav />
        </aside>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
