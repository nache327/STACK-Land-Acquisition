"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { api } from "@/lib/api";

const TARGET_USES = [
  { id: "self_storage", label: "Self-Storage" },
  { id: "mini_warehouse", label: "Mini-Warehouse" },
  { id: "light_industrial", label: "Light Industrial" },
  { id: "luxury_garage_condo", label: "Luxury Garage Condos" },
] as const;

type TargetUseId = (typeof TARGET_USES)[number]["id"];

/**
 * Landing page search form.
 * Phase 2: wires up to POST /api/jobs and polls job status.
 */
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
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!jurisdiction.trim()) {
      setError("Please enter a city, county, or zoning map URL.");
      return;
    }
    if (selectedUses.size === 0) {
      setError("Please select at least one target use.");
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
      setError(err instanceof Error ? err.message : "Failed to start job. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Jurisdiction input */}
      <div className="space-y-1.5">
        <label
          htmlFor="jurisdiction"
          className="block text-sm font-medium text-slate-700"
        >
          Jurisdiction
        </label>
        <input
          id="jurisdiction"
          type="text"
          value={jurisdiction}
          onChange={(e) => setJurisdiction(e.target.value)}
          placeholder='e.g. "Draper, UT" or paste an ArcGIS map URL'
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          autoFocus
        />
      </div>

      {/* Ordinance URL */}
      <div className="space-y-1.5">
        <label
          htmlFor="ordinance-url"
          className="block text-sm font-medium text-slate-700"
        >
          Zoning Ordinance URL{" "}
          <span className="font-normal text-slate-400">(Municode / eCode360 / city site)</span>
        </label>
        <input
          id="ordinance-url"
          type="url"
          value={ordinanceUrl}
          onChange={(e) => setOrdinanceUrl(e.target.value)}
          placeholder="https://library.municode.com/..."
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        />
      </div>

      {/* Target uses */}
      <div className="space-y-2">
        <span className="block text-sm font-medium text-slate-700">Target Uses</span>
        <div className="flex flex-wrap gap-2">
          {TARGET_USES.map((use) => (
            <button
              key={use.id}
              type="button"
              onClick={() => toggleUse(use.id)}
              className={[
                "rounded-full px-3 py-1 text-sm font-medium transition-colors",
                selectedUses.has(use.id)
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200",
              ].join(" ")}
            >
              {use.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? "Starting search..." : "Find Candidate Parcels"}
      </button>
    </form>
  );
}
