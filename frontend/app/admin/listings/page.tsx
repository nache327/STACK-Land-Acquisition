"use client";

import { useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface UploadResponse {
  inserted: number;
  updated: number;
  dropped: number;
  match_pending: number;
  source: string;
  jurisdiction_id: string;
  parser_warnings: string[];
  message?: string;
}

export default function ListingsUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<string>("");
  const [jurisdictionId, setJurisdictionId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Pick a file first.");
      return;
    }
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (source) form.append("source", source);
      if (jurisdictionId) form.append("jurisdiction_id", jurisdictionId);

      const res = await fetch(`${API_BASE}/api/listings/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const detail = await res
          .json()
          .then((j) => j.detail ?? `HTTP ${res.status}`)
          .catch(() => `HTTP ${res.status}`);
        throw new Error(detail);
      }
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-xl font-semibold text-slate-900">Upload listings</h1>
      <p className="mt-1 text-sm text-slate-500">
        Upload a CoStar / LoopNet / Crexi export. The file is parsed,
        normalized, matched to parcels, and surfaced in the daily digest +
        any active "🔥 New listing match" filter within ~1 minute.
      </p>

      <form
        onSubmit={onSubmit}
        className="mt-6 space-y-4 rounded-lg border border-slate-200 bg-white p-5"
      >
        <div>
          <label className="block text-xs font-medium text-slate-700">
            File (.xlsx or .csv)
          </label>
          <input
            type="file"
            accept=".xlsx,.csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mt-1 block w-full text-sm"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-700">
              Source (optional)
            </label>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="mt-1 block w-full rounded-md border-slate-300 text-sm"
            >
              <option value="">Auto-detect</option>
              <option value="costar">CoStar</option>
              <option value="loopnet">LoopNet (stub)</option>
              <option value="crexi">Crexi (stub)</option>
              <option value="generic">Generic (canonical columns)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700">
              Jurisdiction ID (optional)
            </label>
            <input
              type="text"
              value={jurisdictionId}
              onChange={(e) => setJurisdictionId(e.target.value)}
              placeholder="auto-resolved if blank"
              className="mt-1 block w-full rounded-md border-slate-300 text-sm font-mono"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={busy || !file}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {busy ? "Uploading…" : "Upload"}
        </button>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm">
            <div className="font-semibold text-emerald-800">
              Upload accepted · source: {result.source}
            </div>
            <table className="mt-2 w-full text-xs">
              <tbody>
                <tr>
                  <td className="text-slate-600">Inserted</td>
                  <td className="text-right font-mono">{result.inserted}</td>
                </tr>
                <tr>
                  <td className="text-slate-600">Updated</td>
                  <td className="text-right font-mono">{result.updated}</td>
                </tr>
                <tr>
                  <td className="text-slate-600">Dropped (no longer in feed)</td>
                  <td className="text-right font-mono">{result.dropped}</td>
                </tr>
                <tr>
                  <td className="text-slate-600">Pending match</td>
                  <td className="text-right font-mono">{result.match_pending}</td>
                </tr>
                <tr>
                  <td className="text-slate-600">Jurisdiction</td>
                  <td className="text-right font-mono">{result.jurisdiction_id}</td>
                </tr>
              </tbody>
            </table>
            {result.parser_warnings.length > 0 && (
              <div className="mt-2">
                <div className="text-xs font-medium text-amber-700">
                  Parser warnings:
                </div>
                <ul className="ml-4 list-disc text-xs text-amber-700">
                  {result.parser_warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mt-2 text-[11px] text-slate-500">
              Matching runs in the background; refresh the jurisdiction
              dashboard in ~1 minute to see updated ListingCard banners.
            </div>
          </div>
        )}
      </form>
    </main>
  );
}
