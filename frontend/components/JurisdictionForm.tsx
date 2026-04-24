"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

const TARGET_USES = [
  { id: "self_storage", label: "Self-Storage" },
  { id: "mini_warehouse", label: "Mini-Warehouse" },
  { id: "light_industrial", label: "Light Industrial" },
  { id: "luxury_garage_condo", label: "Garage Condos" },
] as const;

type TargetUseId = (typeof TARGET_USES)[number]["id"];

export function JurisdictionForm() {
  const router = useRouter();
  const [jurisdiction, setJurisdiction] = useState("");
  const [ordinanceUrl, setOrdinanceUrl] = useState("");
  const [selectedUses, setSelectedUses] = useState<Set<TargetUseId>>(
    new Set(TARGET_USES.map((u) => u.id))
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleUse(id: TargetUseId) {
    setSelectedUses((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!jurisdiction.trim()) {
      setError("Enter a city, county, or ArcGIS map URL.");
      return;
    }
    if (selectedUses.size === 0) {
      setError("Select at least one target use.");
      return;
    }
    setLoading(true);
    try {
      const job = await api.createJob({
        jurisdiction: jurisdiction.trim(),
        ordinance_url: ordinanceUrl.trim() || undefined,
        target_uses: Array.from(selectedUses),
      });
      router.push(`/dashboard/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start — try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">

      {/* Jurisdiction */}
      <div className="space-y-1.5">
        <label htmlFor="jurisdiction" className="block text-sm font-medium text-slate-300">
          City or County
        </label>
        <input
          id="jurisdiction"
          type="text"
          value={jurisdiction}
          onChange={(e) => setJurisdiction(e.target.value)}
          placeholder='e.g. "Draper, UT" or paste an ArcGIS URL'
          autoFocus
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 transition focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {/* Ordinance URL */}
      <div className="space-y-1.5">
        <label htmlFor="ordinance-url" className="block text-sm font-medium text-slate-300">
          Zoning Ordinance URL{" "}
          <span className="font-normal text-slate-500">— optional</span>
        </label>
        <input
          id="ordinance-url"
          type="url"
          value={ordinanceUrl}
          onChange={(e) => setOrdinanceUrl(e.target.value)}
          placeholder="Municode / eCode360 / city site…"
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 transition focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {/* Target uses */}
      <div className="space-y-2">
        <span className="block text-sm font-medium text-slate-300">Target Uses</span>
        <div className="flex flex-wrap gap-2">
          {TARGET_USES.map((use) => (
            <button
              key={use.id}
              type="button"
              onClick={() => toggleUse(use.id)}
              className={[
                "rounded-lg border px-3 py-1.5 text-sm font-medium transition-all",
                selectedUses.has(use.id)
                  ? "border-blue-500 bg-blue-600/20 text-blue-300 shadow-sm shadow-blue-500/20"
                  : "border-slate-700 bg-slate-800/50 text-slate-400 hover:border-slate-600 hover:text-slate-300",
              ].join(" ")}
            >
              {use.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <p className="rounded-lg border border-red-800/50 bg-red-900/20 px-3 py-2 text-sm text-red-400">
          {error}
        </p>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={loading}
        className="relative w-full overflow-hidden rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-900/30 transition-all hover:bg-blue-500 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            Starting analysis…
          </span>
        ) : (
          "Find Candidate Parcels →"
        )}
      </button>

    </form>
  );
}
